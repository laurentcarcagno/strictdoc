"""
The exclusion of a project, and the commit of what a write request changed.

For one project, these never run at the same time: a save with its commit, and
a change of the files by Git (the update of the project from the server, later
the merge). Both hold the gate of the project. A command that reaches the
network never holds it: the network is slow, and the user saves meanwhile.

The server of a project writes in the files in many routes, and only the save
of a document commits what it wrote (GitCommitter.on_document_written). The
middleware of this module commits the rest at the end of a write request that
succeeded: the deletion of a node, the move of a document, a folder, the
grammar, the title. It commits nothing else:

- a request that reads, or a write that was refused or failed, changes nothing
  that the user decided: no commit;
- while a merge, a rebase or a cherry-pick waits to be finished, nothing is
  committed: the commit would finish it with the files of the moment;
- what ".gitignore" ignores stays out, and so do the uploads that wait for
  their document (GitCommitter.pending_paths): the next save of a document
  commits them with it;
- only the changes of a user who may commit them are committed: the route must
  be one that needs the role of an author at least (the table of the roles),
  and permissions.py must say that the role of the user commits. A reader
  whose request succeeded (the assistant, an export) changes nothing that is
  committed in his name.

While a merge waits for the user, the writes of the project are refused with
a text for the user (the web server answers 423), except the routes of Git and
of the merge. The routes of the merge are not refused when the index is late
either: a conflict that makes a document unreadable could not be solved
otherwise.

The gate is taken without blocking a thread of the server (a request that
waits polls), so that a request that is cancelled never leaves the gate taken
and the requests that wait never use the threads that the holder needs to end.
A request that does not write, and may last (the assistant, the exports, the
network), does not take the gate: see UNGATED_ROUTES. A function that holds
the gate and calls another one that asks for it, in the same request, is not
blocked: the gate is known as held in the context of the request.

@relation(SDOC-SRS-1242, scope=file)
@relation(SDOC-SRS-1243, scope=file)
@relation(SDOC-SRS-1246, scope=file)
@relation(SDOC-SRS-1247, scope=file)
"""

import logging
import os
import threading
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    FrozenSet,
    Iterator,
    List,
    Optional,
    Pattern,
)

import anyio
from starlette.responses import JSONResponse
from starlette.routing import compile_path

from strictdoc.features.desktop.git_access import DesktopGitService
from strictdoc.features.desktop.permissions import can_commit
from strictdoc.features.desktop.project_runtime import ProjectRuntime
from strictdoc.features.git_config.committer import GitCommitter
from strictdoc.features.git_config.git_service import GitServiceError
from strictdoc.features.i18n.i18n import gettext
from strictdoc.features.roles.principal import Principal
from strictdoc.features.roles.roles import ROLE_AUTHOR, role_allows
from strictdoc.features.roles.route_roles import ROUTE_ROLES, match_route_key

logger = logging.getLogger(__name__)

# The methods of a request that may change the project.
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# The requests that write nothing in the project, with a method that may
# write. They may last (a model that answers, a Word document that is built,
# the network), so they never wait for the gate and never hold it. Each one was
# read in its route: the assistant and the drafts ask a model and write only
# the log of the audit, in the cache folder of the application; the jobs of
# the assistant compute proposals, and only "apply" and "create", which are not
# here, write them; the two previews and the export build a report or a file to
# send back, and write nothing; the push sends the commits (it moves the files
# forward when the server is ahead, and that move takes the gate itself, see
# DesktopGitService.push). A route that is not in the list holds the gate.
UNGATED_ROUTES = (
    ("POST", "/actions/llm/assist"),
    ("POST", "/actions/llm/draft"),
    ("DELETE", "/actions/llm/jobs/{job_id}"),
    ("POST", "/docx/export"),
    ("POST", "/actions/project_index/export_docx_preview"),
    ("POST", "/actions/project_index/import_docx_preview"),
    ("POST", "/actions/git/push"),
    # The signal of a page that has an editor open: it changes no file.
    ("POST", "/__desktop/editing"),
    # The update on request: the network is slow, so it takes the gate for
    # the change of the files only (project_sync.py).
    ("POST", "/actions/git/sync"),
    # The publication of a version reads the server, and sends one tag: it
    # takes the gate for its checks only (project_publish.py).
    ("POST", "/actions/git/version_document"),
)

# The routes of the merge that waits. They are not refused when the index is
# late: a conflict that makes a document unreadable could not be solved if
# they were. They hold the gate, and the other writes wait or are refused.
MERGE_ROUTES = (
    ("POST", "/actions/git/sync/resolve"),
    ("POST", "/actions/git/sync/abort"),
)

# The routes that the merge that waits does not stop: the ones of Git. The
# web server lets them pass too (git_sync/guard.py).
MERGE_FREE_PREFIX = "/actions/git/"

# The header that a page sends with a write: the revision of the files that
# the oldest of its editors was opened on. The server answers every request
# with the revision that it started with, in the same header and in
# "Server-Timing" (a page that was loaded reads it there).
REVISION_HEADER = "x-desktop-revision"
CONFLICT_HEADER = "x-desktop-conflict"

# How long a request that waits for the gate sleeps between two looks.
GATE_POLL_SECONDS = 0.005

Scope = Dict[str, Any]
Receive = Callable[[], Awaitable[Dict[str, Any]]]
Send = Callable[[Dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


# The gates that the current request or task holds. A thread that a request
# starts has a copy of it, so it knows that the gate is held.
_held_gates: ContextVar[FrozenSet[int]] = ContextVar(
    "desktop_held_gates", default=frozenset()
)


class ProjectGate:
    """One exclusion per project, shared by all that change its files."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()

    def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        Take the gate. Without a timeout it waits as long as needed. It returns
        False when the time ran out. Call it from a thread, not from the loop.
        """
        if timeout is None:
            return self._lock.acquire()
        return self._lock.acquire(timeout=max(timeout, 0.0))

    def try_acquire(self) -> bool:
        """Take the gate if it is free, and never wait."""
        return self._lock.acquire(blocking=False)

    def release(self) -> None:
        self._lock.release()

    def mark_held(self) -> "Token[FrozenSet[int]]":
        """Tell the code of this context that it runs with the gate held."""
        return _held_gates.set(_held_gates.get() | {id(self)})

    @staticmethod
    def unmark_held(token: "Token[FrozenSet[int]]") -> None:
        _held_gates.reset(token)

    @contextmanager
    def hold(self) -> Iterator[None]:
        """
        Hold the gate. In a context that holds it already (a function that
        runs in the request that took it), it does nothing: no one waits for
        oneself.
        """
        if id(self) in _held_gates.get():
            yield
            return
        self.acquire()
        token = self.mark_held()
        try:
            yield
        finally:
            self.unmark_held(token)
            self.release()


_gates: Dict[str, ProjectGate] = {}
_gates_lock: threading.Lock = threading.Lock()


def get_project_gate(folder: str) -> ProjectGate:
    """The gate of the project in the folder, the same for every caller."""
    key = os.path.normcase(os.path.realpath(folder))
    with _gates_lock:
        gate = _gates.get(key)
        if gate is None:
            gate = ProjectGate()
            _gates[key] = gate
        return gate


def get_route_role(method: str, path: str) -> Optional[str]:
    """The role that the table of the roles gives to a request, or None."""
    key = match_route_key(method.upper(), path)
    return ROUTE_ROLES.get(key) if key is not None else None


def is_ungated(method: str, path: str) -> bool:
    """True for a request that never takes the gate (UNGATED_ROUTES)."""
    return any(
        method == route_method_ and expression_.match(path) is not None
        for route_method_, expression_ in _UNGATED_MATCHERS
    )


def commit_pending_changes(committer: GitCommitter) -> bool:
    """
    Commit what differs from the last commit, except what waits for a document
    (see the top of the module). It returns True when a commit was made. A
    failure is kept in the last_error of the committer, where the indicator
    shows it. Call it with the gate.
    """
    service = committer.service
    if not isinstance(service, DesktopGitService):
        return False
    root = service.project_root
    try:
        if service.is_operation_in_progress(root):
            return False
        waiting = [os.path.realpath(path_) for path_ in committer.pending_paths]
        paths = [
            path_
            for path_ in service.list_changed_paths(root)
            if not _is_waiting(path_, waiting)
        ]
        if len(paths) == 0:
            return False
        committed = service.commit_paths(
            paths, _get_message(root, paths), committer.author_provider()
        )
    except (GitServiceError, OSError) as error:
        committer.last_error = str(error)
        logger.warning("git: %s", error)
        return False
    if committed:
        committer.last_error = ""
        if committer.after_commit is not None:
            try:
                committer.after_commit()
            except Exception:
                logger.exception("git: the function after a commit failed.")
    return committed


class ProjectGateMiddleware:
    """
    The gate around a write request, and the commit at its end. It is the
    outermost middleware of the project: it sees the final answer, also the
    refusal of a role.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        gate: ProjectGate,
        get_committer: Callable[[], Optional[GitCommitter]],
        get_required_role: Callable[[str, str], Optional[str]] = get_route_role,
        runtime: Optional[ProjectRuntime] = None,
        is_merge_waiting: Optional[Callable[[], bool]] = None,
    ) -> None:
        """
        get_required_role gives the role that a route needs, as the table of
        the roles does: the commit of a request is made for a route of an
        author, and not for a route that anybody may call.

        With the runtime of the project, every answer tells the revision of
        the files, and a write that comes from a form opened on another
        revision is refused (409) before it runs: the form was made from files
        that are not the ones of the disk, and saving it would replace what is
        there with what was there.

        is_merge_waiting: tells that a merge waits for the user. The writes of
        the project are then refused with a text for the user, as the web
        server does with a 423 (git_sync/guard.py); the routes of Git and of
        the merge pass.
        """
        self.app = app
        self._gate = gate
        self._get_committer = get_committer
        self._get_required_role = get_required_role
        self._runtime = runtime
        self._is_merge_waiting = is_merge_waiting

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # The revision of the files at the start: a page that is built while
        # an update applies is stamped with the older revision, and a form
        # that it opens is then refused, never saved over the new files.
        if self._runtime is not None:
            send = _add_revision_headers(send, self._runtime.revision)
        if scope["method"] not in WRITE_METHODS or is_ungated(
            scope["method"], scope["path"]
        ):
            await self.app(scope, receive, send)
            return
        # The wait does not use a thread and ends with a cancellation at once.
        while not self._gate.try_acquire():
            await anyio.sleep(GATE_POLL_SECONDS)
        # Nothing awaits between the gate taken and the "try": a cancellation
        # cannot come in between.
        token = self._gate.mark_held()
        is_gate_handed_over = False
        try:
            is_merge_route = _is_merge_route(scope["method"], scope["path"])
            if not is_merge_route and self._is_index_outdated():
                await _refuse_save(scope, receive, send, _get_unreadable_text())
                return
            if (
                not is_merge_route
                and not scope["path"].startswith(MERGE_FREE_PREFIX)
                and self._is_merge_waiting is not None
                and self._is_merge_waiting()
            ):
                await _refuse_save(
                    scope, receive, send, _get_merge_waiting_text()
                )
                return
            if not is_merge_route and self._is_form_out_of_date(scope):
                await _refuse_save(
                    scope, receive, send, _get_out_of_date_text()
                )
                return
            status_codes: List[int] = []

            async def send_wrapper(message: Dict[str, Any]) -> None:
                if message["type"] == "http.response.start":
                    status_codes.append(int(message["status"]))
                await send(message)

            await self.app(scope, receive, send_wrapper)
            if (
                len(status_codes) > 0
                and 200 <= status_codes[0] < 400
                and self._may_commit(scope)
            ):
                # The commit runs in a thread of its own, and that thread
                # gives the gate back when the commit ends: a request that is
                # cancelled meanwhile gives up waiting, never the gate.
                thread = threading.Thread(
                    target=self._commit_and_release, daemon=True
                )
                thread.start()
                is_gate_handed_over = True
                while thread.is_alive():
                    await anyio.sleep(GATE_POLL_SECONDS)
        finally:
            self._gate.unmark_held(token)
            if not is_gate_handed_over:
                self._gate.release()

    def _is_index_outdated(self) -> bool:
        """
        True while the index is not the one of the files: a change of the
        files could not be built. Every write is refused, with or without a
        revision: a save writes a document from the index, and would put the
        old text over the new files. Call it with the gate.
        """
        return self._runtime is not None and self._runtime.is_index_outdated

    def _is_form_out_of_date(self, scope: Scope) -> bool:
        """
        True when the write comes from a form opened on a revision that is not
        the one of the disk. Call it with the gate: no update applies between
        the check and the write.
        """
        if self._runtime is None:
            return False
        for name_, value_ in scope.get("headers", []):
            if name_.decode("latin-1").lower() == REVISION_HEADER:
                try:
                    opened = int(value_.decode("latin-1"))
                except ValueError:
                    return False
                return opened != self._runtime.revision
        return False

    def _may_commit(self, scope: Scope) -> bool:
        required = self._get_required_role(scope["method"], scope["path"])
        if required is None or not role_allows(required, ROLE_AUTHOR):
            return False
        principal = scope.get("state", {}).get("principal")
        role = principal.role if isinstance(principal, Principal) else None
        return can_commit(role)

    def _commit_and_release(self) -> None:
        try:
            committer = self._get_committer()
            if committer is not None:
                commit_pending_changes(committer)
        except Exception:
            # The answer is sent: a failure here is for the log.
            logger.exception("git: the commit of the request failed.")
        finally:
            self._gate.release()


def _is_waiting(path: str, waiting: List[str]) -> bool:
    real_path = os.path.realpath(path)
    return any(
        real_path == waiting_ or real_path.startswith(waiting_ + os.sep)
        for waiting_ in waiting
    )


def _get_message(root: str, paths: List[str]) -> str:
    if len(paths) == 1:
        return f"chore: save {os.path.relpath(paths[0], root)}"
    return f"chore: save {len(paths)} files"


_UNGATED_MATCHERS: List["tuple[str, Pattern[str]]"] = [
    (method_, compile_path(path_)[0]) for method_, path_ in UNGATED_ROUTES
]


def _add_revision_headers(send: Send, revision: int) -> Send:
    async def send_with_revision(message: Dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            headers = list(message.get("headers", []))
            headers.append((REVISION_HEADER.encode(), str(revision).encode()))
            headers.append(
                (
                    b"server-timing",
                    f'desktop_revision;desc="{revision}"'.encode(),
                )
            )
            message = {**message, "headers": headers}
        await send(message)

    return send_with_revision


def _is_merge_route(method: str, path: str) -> bool:
    return (method, path) in MERGE_ROUTES


def _get_merge_waiting_text() -> str:
    return gettext(
        "You and a colleague changed the same items. Choose which version to "
        "keep before you change the project: your text is still on the "
        "screen, copy it."
    )


def _get_out_of_date_text() -> str:
    return gettext(
        "The project changed while you were typing, so your change "
        "was not saved. Your text is still on the screen: copy it, "
        "then reload the page."
    )


def _get_unreadable_text() -> str:
    return gettext(
        "The project files cannot be read since their last change, so "
        "nothing can be saved for now. Your text is still on the screen: "
        "copy it. Saving works again when the files are repaired."
    )


async def _refuse_save(
    scope: Scope, receive: Receive, send: Send, message: str
) -> None:
    """
    The answer to a save that is refused: 409 with a text for the user. The
    page keeps what was typed, and tells the user to copy it.
    """
    response = JSONResponse(
        {"message": message},
        status_code=409,
        headers={CONFLICT_HEADER: "1", "Cache-Control": "no-store"},
    )
    await response(scope, receive, send)
