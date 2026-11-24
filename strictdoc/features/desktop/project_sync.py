"""
The synchronization of a project of the desktop application: it receives the
changes of the others, combines them with the ones of the user, and leaves to
the user only what needs a choice.

One function does it, for the three ways to ask: when the project is opened,
every N minutes (project_servers.py), and on request (the route
"POST /actions/git/sync" of this module, for the button "Update").

The network and the files are apart. The fetch runs with no exclusion (the
network is slow and the user saves meanwhile). Then, with the exclusion of the
project (project_gate.py), the files change in this order: the fast-forward,
or the merge with the documents combined node by node (SyncService), the
commit of the merge, and the notice to the server of the project (the
revision, the watcher of the files and the index: ProjectRuntime.apply_update).
The commit of a merge is sent by the queue of the sending, never by the
synchronization itself.

What it never does:

- nothing while a merge waits for the user (the user decides first), and
  nothing while a page has an editor open (the update waits for its end);
- a document that a person must choose for is not decided by the application:
  the merge waits, and the window of the merge opens in the page;
- a file that is not a document (an image, a ".gitattributes") cannot be
  combined by nodes: the local file stays, the one of the colleague is saved
  next to it, and the user is told. Nothing is lost and nothing waits;
- a user who may not decide (a reader) never gets a window: when his own
  comments overlap with a change of a colleague on the same node, the merge is
  abandoned, the update waits for one of the two sides to move, and the user
  is told. His comments stay as they were.

The reader of a document may comment on it, and his comment is a commit that
the application never sends. The update of such a reader is then a merge, not
a fast-forward: the merge keeps the comment in the history that Git keeps for
him, the fast-forward would stop for good as soon as the first comment is
saved. Git does the preserving, and no file of the working copy waits in a
state that only this application knows. The merge commit stays on his computer
like the comment (the queue says that a reader sends nothing). The comments of
a reader will be shared by the synchronization of the comments, later.

@relation(SDOC-SRS-1245, scope=file)
@relation(SDOC-SRS-1247, scope=file)
@relation(SDOC-SRS-1248, scope=file)
@relation(SDOC-SRS-1250, scope=file)
"""

import json
import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse
from starlette.responses import HTMLResponse, Response

from strictdoc.features.desktop.commit_author import CommitAuthorError
from strictdoc.features.desktop.git_access import DesktopGitService, GitAccess
from strictdoc.features.desktop.permissions import (
    can_resolve,
    can_send,
    can_update,
)
from strictdoc.features.desktop.project_gate import ProjectGate
from strictdoc.features.desktop.project_runtime import (
    Inhibition,
    ProjectRuntime,
)
from strictdoc.features.desktop.project_status import SendState
from strictdoc.features.desktop.workspace import (
    PULL_TIMEOUT_SECONDS,
    UpdateDeferredError,
    WorkspaceError,
    fetch_project,
)
from strictdoc.features.git_config.config import GitConfig
from strictdoc.features.git_config.git_service import (
    Author,
    GitServiceError,
)
from strictdoc.features.git_sync.merge3 import assemble
from strictdoc.features.git_sync.sync_service import (
    CONFLICTS,
    SyncResult,
    SyncService,
)
from strictdoc.features.i18n.i18n import gettext
from strictdoc.features.roles.router import get_principal
from strictdoc.helpers.exception import StrictDocException
from strictdoc.server.project_context import ProjectContext

logger = logging.getLogger(__name__)

SYNC_PATH = "/actions/git/sync"
DIALOG_PATH = "/actions/git/sync_dialog"
RESOLVE_PATH = "/actions/git/sync/resolve"
ABORT_PATH = "/actions/git/sync/abort"
HTTP_PRECONDITION_FAILED = 412
HTTP_BAD_GATEWAY = 502


class SyncOutcome(Enum):
    """What a synchronization did to the files of the project."""

    # Nothing to bring, or nothing to do now.
    UP_TO_DATE = "up_to_date"
    # The files changed: an update, a merge that is done, a merge that waits.
    UPDATED = "updated"
    # A reader whose comments overlap with a change of a colleague: the
    # update is on hold, and the files are as they were.
    BLOCKED = "blocked"


@dataclass(frozen=True)
class KeptFile:
    """A file that is not a document, which two people changed."""

    path: str
    # The file next to it that holds the other version, "" when none.
    copy_path: str
    # "local": the file of the user stays. "server": the user had removed it
    # and the colleague had changed it, so the changed file is back.
    kept_side: str


class DesktopSyncService(SyncService):
    """
    The merge of the documents (SyncService), with what the application does
    in another way:

    - the commit of a merge goes to the queue of the sending, not to the
      server (_push);
    - a conflict on a file that is not a document keeps both versions
      (auto_resolve), where the web server abandons the merge;
    - a file that the user's choice writes is not seen by the watcher as a
      change of somebody else: the inhibition comes before the write, and it
      is taken back if the write fails.
    """

    def __init__(
        self,
        service: DesktopGitService,
        author: Author,
        *,
        on_commit: Callable[[], None],
        runtime: Optional[ProjectRuntime] = None,
    ) -> None:
        super().__init__(service, GitConfig(), author)
        self.desktop_service: DesktopGitService = service
        self._on_commit: Callable[[], None] = on_commit
        self._runtime: Optional[ProjectRuntime] = runtime
        # The files that this service told the watcher about.
        self.inhibition: Inhibition = Inhibition()
        self.kept_files: List[KeptFile] = []

    def auto_resolve(self) -> List[str]:
        """
        Merge again, node by node, the documents that Git stopped on. It
        returns the documents that still have conflicts. A file that is not a
        document keeps both versions: nothing is lost, nothing waits.
        """
        remaining: List[str] = []
        for relative_ in self.desktop_service.unmerged_paths(self.root):
            loaded = self._load(relative_)
            if loaded is None:
                self._keep_both_versions(relative_)
                continue
            if len(loaded.conflict_indexes) > 0:
                remaining.append(relative_)
                # The server of the project reads this file: it gets the local
                # text back until the conflicts are solved.
                self.desktop_service.write_working_file(
                    self.root, relative_, loaded.regions_local_text
                )
            else:
                self.desktop_service.write_resolved(
                    self.root, relative_, assemble(loaded.regions, {})
                )
        return remaining

    def resolve(self, relative: str, chosen: Dict[int, str]) -> None:
        inhibition = self._inhibit(os.path.join(self.root, relative))
        try:
            super().resolve(relative, chosen)
        except BaseException:
            if self._runtime is not None:
                self._runtime.release_inhibition(inhibition)
            raise

    def _push(self, result: SyncResult) -> None:
        # The queue sends it: the same way, the same checks, as every commit.
        del result
        self._on_commit()

    def _keep_both_versions(self, relative: str) -> None:
        copy_relative = self._get_copy_path(relative)
        # Both files change, and the copy is a new file: the watcher is told
        # before Git writes them.
        self._inhibit(os.path.join(self.root, relative))
        self._inhibit(os.path.join(self.root, copy_relative))
        kept_side = self.desktop_service.keep_both_versions(
            self.root, relative, copy_relative
        )
        has_copy = os.path.exists(os.path.join(self.root, copy_relative))
        self.kept_files.append(
            KeptFile(relative, copy_relative if has_copy else "", kept_side)
        )

    def _inhibit(self, path: str) -> Inhibition:
        if self._runtime is None:
            return Inhibition()
        inhibition = self._runtime.inhibit_paths([path])
        self.inhibition.add(inhibition)
        return inhibition

    def _get_copy_path(self, relative: str) -> str:
        directory, name = os.path.split(relative)
        stem, extension = os.path.splitext(name)
        number = 1
        while True:
            suffix = " (colleague)" if number == 1 else f" (colleague {number})"
            name = f"{stem}{suffix}{extension}"
            candidate = os.path.join(directory, name)
            if not os.path.exists(os.path.join(self.root, candidate)):
                return candidate
            number += 1


def synchronize_project(
    folder: str,
    *,
    git_access: GitAccess,
    gate: ProjectGate,
    runtime: ProjectRuntime,
    author_provider: Callable[[], Author],
    role: Optional[str],
    send_queue: Optional[Any] = None,
    timeout_seconds: float = PULL_TIMEOUT_SECONDS,
    is_forced: bool = False,
) -> SyncOutcome:
    """
    Synchronize the project in the folder. It returns UPDATED when the files
    of the working copy changed (an update, a merge that is done, a merge that
    waits), BLOCKED when the update is on hold because of the comments of a
    reader, and UP_TO_DATE when there was nothing to do.

    It raises UpdateDeferredError when a page has an editor open and there is
    something to bring (the caller tries again when the editor is closed), and
    WorkspaceError when it cannot be done: no network, no server, nobody to
    sign the merge. The files are then as they were.

    is_forced: the user asked (the button "Update"). A merge that the user put
    off with "later" is then proposed again.

    send_queue: gives notify(folder) and is called after each commit that the
    synchronization made.
    """
    service = DesktopGitService(folder, git_access)
    try:
        if service.is_operation_in_progress(folder):
            # The user decides first: nothing is fetched, nothing changes.
            return SyncOutcome.UP_TO_DATE
    except GitServiceError as error:
        raise WorkspaceError(str(error)) from error
    fetch_project(
        folder, timeout_seconds=timeout_seconds, git_access=git_access
    )
    on_commit = _create_on_commit(send_queue, folder, role)
    with gate.hold():
        try:
            return _apply_synchronization(
                service,
                folder,
                runtime=runtime,
                author_provider=author_provider,
                role=role,
                on_commit=on_commit,
                is_forced=is_forced,
            )
        except GitServiceError as error:
            raise WorkspaceError(str(error)) from error


def get_merge_key(service: DesktopGitService, folder: str) -> str:
    """The identifier of the merge that waits, "" when none does."""
    try:
        return service.read_merge_key(folder)
    except (GitServiceError, OSError):
        return ""


def create_sync_routes(
    *,
    context: ProjectContext,
    folder: str,
    git_access: GitAccess,
    gate: ProjectGate,
    runtime: ProjectRuntime,
    send_queue: Optional[Any] = None,
) -> APIRouter:
    """
    The routes of the synchronization of the application, which take the place
    of the ones of the web server (the same paths, the same templates). They
    differ in what they do: the update is the one of this module, the commit
    of the merge goes to the queue of the sending, and the texts have no
    word of Git. The role that each one needs is in permissions.py.
    """
    router = APIRouter()

    def create_service(request: Request) -> DesktopSyncService:
        committer = context.git_committer
        if committer is None:
            raise GitServiceError(
                gettext("The project cannot be synchronized from here.")
            )
        return DesktopSyncService(
            DesktopGitService(folder, git_access),
            committer.author_provider(),
            on_commit=_create_on_commit(
                send_queue, folder, get_principal(request).role
            ),
            runtime=runtime,
        )

    @router.get(DIALOG_PATH, response_class=Response)
    def update_dialog(merged: bool = False) -> Response:
        """
        The window "Update the project": it asks for the update when it
        appears. After the choice in the window of the merge, it says that the
        two are combined.
        """
        output = context.env().render_template_as_markup(
            "stream_update.jinja.html",
            message=(
                gettext(
                    "Your changes and those of your colleagues are combined."
                )
                if merged
                else ""
            ),
        )
        return HTMLResponse(
            content=output,
            headers={"Content-Type": "text/vnd.turbo-stream.html"},
        )

    @router.post(SYNC_PATH, response_class=Response)
    def update(request: Request) -> Response:
        """The user asks for the update now."""
        committer = context.git_committer
        role = get_principal(request).role
        if committer is None or not can_update(role):
            return _answer(
                "failed", get_failure_text(), HTTP_PRECONDITION_FAILED
            )
        # Nobody signed in: the update is refused, as every commit is (409).
        committer.author_provider()
        try:
            outcome = synchronize_project(
                folder,
                git_access=git_access,
                gate=gate,
                runtime=runtime,
                author_provider=committer.author_provider,
                role=role,
                send_queue=send_queue,
                is_forced=True,
            )
        except UpdateDeferredError:
            return _answer(
                "deferred",
                gettext(
                    "An update of the project waits: it applies when you "
                    "close the editor."
                ),
            )
        except WorkspaceError as error:
            logger.warning("The update of the project failed: %s", error)
            return _answer("failed", get_failure_text(), HTTP_BAD_GATEWAY)
        service = DesktopGitService(folder, git_access)
        if get_merge_key(service, folder) != "":
            return _answer("merge_waiting", get_merge_waiting_text())
        if outcome is SyncOutcome.BLOCKED:
            return _answer("update_blocked", get_update_blocked_text())
        if outcome is SyncOutcome.UPDATED:
            return _answer("updated", "")
        return _answer("up_to_date", gettext("The project is up to date."))

    @router.post(RESOLVE_PATH)
    def resolve(
        request: Request, file: str = Form(""), texts: str = Form("{}")
    ) -> Response:
        """
        The text of each conflict of a document (JSON: region -> text). When
        the last document is done, the merge is committed, the queue sends it
        and the server of the project reads the files again.
        """
        try:
            service = create_service(request)
            chosen: Dict[int, str] = {
                int(key_): str(value_)
                for key_, value_ in json.loads(texts).items()
            }
            service.resolve(file, chosen)
            remaining = service.conflict_paths()
            if len(remaining) > 0:
                return JSONResponse(
                    {
                        "ok": True,
                        "next": "/actions/git/sync_conflicts"
                        f"?file={quote(remaining[0])}",
                    }
                )
            result = service.complete()
            if result.status == CONFLICTS:
                return JSONResponse({"error": get_merge_waiting_text()}, 422)
        except (StrictDocException, ValueError) as error:
            return JSONResponse({"error": str(error)}, status_code=422)
        except GitServiceError as error:
            logger.warning("The choice could not be saved: %s", error)
            return JSONResponse(
                {"error": _get_git_error_text(error)}, status_code=422
            )
        # The files that the merge wrote were inhibited when it wrote them, and
        # the choice inhibited the ones that it wrote: nothing changes now.
        runtime.apply_update([])
        return JSONResponse(
            {"ok": True, "next": "/actions/git/sync_dialog?merged=1&pushed=0"}
        )

    @router.post(ABORT_PATH, response_class=Response)
    def abort(request: Request) -> Response:
        """
        Abandon the merge: the project is as it was before the update, and
        the changes of the colleagues come back with the next update.
        """
        try:
            service = create_service(request)
            head = _read_head(service.desktop_service, folder)
            # What the merge changed, read before it is undone: the watcher
            # leaves these files alone when they come back.
            touched = service.desktop_service.list_touched_paths(folder, head)
            # Told before Git writes the files back, not after.
            inhibition = runtime.inhibit_paths(touched)
            try:
                service.abort()
            except BaseException:
                runtime.release_inhibition(inhibition)
                raise
        except GitServiceError as error:
            logger.warning("The merge could not be abandoned: %s", error)
            return HTMLResponse(
                _get_git_error_text(error),
                status_code=422,
                headers={"Content-Type": "text/plain; charset=utf-8"},
            )
        runtime.apply_update(touched, inhibition=inhibition)
        # Held back until one of the sides moves, or until the user asks.
        runtime.blocked_heads = _read_heads(service.desktop_service, folder)
        # The page reloads with the files as they are now: nothing to render.
        return HTMLResponse(
            "", headers={"Content-Type": "text/vnd.turbo-stream.html"}
        )

    return router


def get_failure_text() -> str:
    return gettext(
        "The update could not be done for now. Your changes are kept, and "
        "the application tries again."
    )


def get_merge_waiting_text() -> str:
    return gettext(
        "You and a colleague changed the same items: choose which version to "
        "keep."
    )


def get_update_blocked_text() -> str:
    return gettext(
        "An update of your colleagues is on hold: it overlaps with changes "
        "that only you can keep."
    )


def get_kept_files_text(kept_files: List[KeptFile]) -> str:
    """The user reads which file kept which version, and where the other is."""
    sentences: List[str] = []
    for kept_ in kept_files:
        if kept_.kept_side == "local" and kept_.copy_path != "":
            sentences.append(
                gettext(
                    "%(file)s was changed by you and by a colleague. Your "
                    "version is kept, and theirs is saved as %(copy)s."
                )
                % {"file": kept_.path, "copy": kept_.copy_path}
            )
        elif kept_.kept_side == "local":
            sentences.append(
                gettext(
                    "%(file)s was changed by you and removed by a colleague. "
                    "Your version is kept."
                )
                % {"file": kept_.path}
            )
        else:
            sentences.append(
                gettext(
                    "%(file)s was changed by a colleague and removed by you. "
                    "The changed file is kept."
                )
                % {"file": kept_.path}
            )
    return " ".join(sentences)


def _answer(state: str, message: str, status_code: int = 200) -> Response:
    return JSONResponse(
        {"state": state, "message": message},
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )


def _create_on_commit(
    send_queue: Optional[Any], folder: str, role: Optional[str]
) -> Callable[[], None]:
    def on_commit() -> None:
        if send_queue is not None and can_send(role):
            send_queue.notify(folder)

    return on_commit


def _get_git_error_text(error: GitServiceError) -> str:
    """
    What the user reads of a failure of Git: the message of the author when it
    is one (nobody is signed in), else a text of ours, never the output of Git.
    """
    if isinstance(error, CommitAuthorError):
        return str(error)
    return gettext(
        "The choice could not be saved. Nothing was lost: try again."
    )


def _read_head(service: DesktopGitService, folder: str) -> Optional[str]:
    """The commit that the project is at, to tell what a merge changed."""
    try:
        return service.read_head(folder)
    except GitServiceError:
        return None


def _read_heads(
    service: DesktopGitService, folder: str
) -> Optional[tuple[str, str]]:
    try:
        branch = service.current_branch(folder)
        return service.read_heads(folder, branch)
    except GitServiceError:
        return None


def _apply_synchronization(
    service: DesktopGitService,
    folder: str,
    *,
    runtime: ProjectRuntime,
    author_provider: Callable[[], Author],
    role: Optional[str],
    on_commit: Callable[[], None],
    is_forced: bool,
) -> SyncOutcome:
    """The part of the synchronization that changes the files. Hold the gate."""
    if service.is_operation_in_progress(folder):
        return SyncOutcome.UP_TO_DATE
    branch = service.current_branch(folder)
    if not service.remote_branch_exists(folder, branch):
        return SyncOutcome.UP_TO_DATE
    behind, ahead = service.ahead_behind(folder, branch)
    if behind == 0:
        runtime.blocked_heads = None
        return SyncOutcome.UP_TO_DATE
    heads = service.read_heads(folder, branch)
    if not is_forced and runtime.blocked_heads == heads:
        # What could not be combined, or what the user put off: the same
        # files, the same answer. One of the sides must move first.
        return SyncOutcome.UP_TO_DATE
    if runtime.leases.is_editing():
        raise UpdateDeferredError("The update waits for the end of the typing.")
    head_before = heads[0]
    runtime.blocked_heads = None
    if ahead == 0:
        # The watcher is told before Git writes the files: it looks at a
        # change 0.3 seconds after it, and a slow Git must not be seen first.
        incoming = service.list_incoming_paths(folder, branch)
        inhibition = runtime.inhibit_paths(incoming)
        try:
            service.fast_forward(folder, branch)
        except BaseException:
            runtime.release_inhibition(inhibition)
            raise
        runtime.sync_notice_state = ""
        runtime.sync_notice_text = ""
        runtime.apply_update(
            service.list_touched_paths(folder, head_before),
            inhibition=inhibition,
        )
        return SyncOutcome.UPDATED
    return _merge_and_apply(
        service,
        folder,
        branch=branch,
        head_before=head_before,
        runtime=runtime,
        author_provider=author_provider,
        role=role,
        on_commit=on_commit,
        heads=heads,
    )


def _merge_and_apply(
    service: DesktopGitService,
    folder: str,
    *,
    branch: str,
    head_before: str,
    runtime: ProjectRuntime,
    author_provider: Callable[[], Author],
    role: Optional[str],
    on_commit: Callable[[], None],
    heads: tuple[str, str],
) -> SyncOutcome:
    author = author_provider()
    sync = DesktopSyncService(
        service,
        author,
        on_commit=on_commit,
        runtime=runtime,
    )
    is_waiting = False
    # The files that the merge can write, told to the watcher before Git
    # writes them. The ones that stay as they are get their inhibition back.
    incoming = service.list_incoming_paths(folder, branch)
    inhibition = runtime.inhibit_paths(incoming)
    sync.inhibition.add(inhibition)
    try:
        is_clean = service.start_merge(folder, branch, author)
        if not is_clean:
            remaining = sync.auto_resolve()
            if len(remaining) > 0:
                if not can_resolve(role):
                    # A reader never decides: his comments stay, the update
                    # waits for one of the two sides to move.
                    service.abort_merge(folder)
                    runtime.blocked_heads = heads
                    runtime.sync_notice_state = SendState.UPDATE_BLOCKED.value
                    runtime.sync_notice_text = get_update_blocked_text()
                    runtime.release_inhibition(sync.inhibition)
                    return SyncOutcome.BLOCKED
                is_waiting = True
        if not is_waiting:
            service.commit_merge(folder, f"Merge origin/{branch}", author)
            on_commit()
    except BaseException:
        runtime.release_inhibition(sync.inhibition)
        # A merge that nobody can finish must not wait for a user who has
        # nothing to decide.
        if not is_waiting and service.is_operation_in_progress(folder):
            try:
                service.abort_merge(folder)
            except GitServiceError:
                logger.exception("The merge could not be abandoned.")
        raise
    _set_kept_notice(runtime, sync.kept_files)
    runtime.apply_update(
        service.list_touched_paths(folder, head_before),
        inhibition=sync.inhibition,
    )
    return SyncOutcome.UPDATED


def _set_kept_notice(
    runtime: ProjectRuntime, kept_files: List[KeptFile]
) -> None:
    if len(kept_files) == 0:
        runtime.sync_notice_state = ""
        runtime.sync_notice_text = ""
        return
    runtime.sync_notice_state = SendState.FILES_KEPT.value
    runtime.sync_notice_text = get_kept_files_text(kept_files)
