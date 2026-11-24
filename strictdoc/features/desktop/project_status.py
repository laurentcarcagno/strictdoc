"""
What the user is told about the changes that are not sent: the states of the
sending, their texts, the answer of "GET /__desktop/status" in the server of a
project, and the indicator of the pages.

A state has a text for the user. The text has no word of the tool that shares
the changes and no message of that tool: the user reads what to do, not what
went wrong inside.

The route is not one of the routes of the project. A middleware answers it,
inside the one that gives the principal: a request without a principal is
refused there like any other, and the role of the user does not matter (a
reader sees the state too). No route is added to the table of the roles.

@relation(SDOC-SRS-1244, scope=file)
@relation(SDOC-SRS-1246, scope=file)
@relation(SDOC-SRS-1247, scope=file)
@relation(SDOC-SRS-1248, scope=file)
"""

import json
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional

import anyio.to_thread
from starlette.responses import JSONResponse

from strictdoc.features.desktop.project_runtime import ProjectRuntime
from strictdoc.features.i18n.i18n import gettext

STATUS_PATH = "/__desktop/status"
EDITING_PATH = "/__desktop/editing"
INDICATOR_TEMPLATE = "project_indicator.jinja.html"
# The variable of the Jinja environment that turns the indicator on. It is
# set for the servers of the application only.
INDICATOR_GLOBAL = "desktop_indicator"
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

# A signal is a few bytes: a page that sends more is not one of ours.
MAXIMUM_SIGNAL_BYTES = 2048
MAXIMUM_PAGE_ID_LENGTH = 64

Scope = Dict[str, Any]
Receive = Callable[[], Awaitable[Dict[str, Any]]]
Send = Callable[[Dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class SendState(str, Enum):
    # Nothing waits to be sent.
    IDLE = "idle"
    # The changes are on their way.
    SENDING = "sending"
    # The server cannot be reached.
    WAITING_NETWORK = "waiting_network"
    # The server refused the changes (the rights, a protected branch).
    REFUSED = "refused"
    # Others changed the project: the update comes first.
    UPDATE_NEEDED = "update_needed"
    # The last change could not be saved in the working copy.
    NOT_SAVED = "not_saved"
    # Some changes are by another user than the one who is signed in.
    OTHER_USER = "other_user"
    SIGNED_OUT = "signed_out"
    # The files of the project cannot be read after a change: nothing is saved
    # until they can.
    UNREADABLE = "unreadable"
    # The user and a colleague changed the same items: nothing is sent and
    # nothing is updated until the user chooses.
    MERGE_WAITING = "merge_waiting"
    # An update of the colleagues is on hold: it overlaps with changes that
    # this user may not decide about.
    UPDATE_BLOCKED = "update_blocked"
    # A file that two people changed was kept in two versions.
    FILES_KEPT = "files_kept"
    # The role of the user does not allow to send.
    READ_ONLY = "read_only"
    # The place that the project is shared with is not the one of the session.
    OTHER_SERVER = "other_server"
    # Something that nobody foresaw stopped the sending of this project. The
    # queue goes on with the others and tries again after a wait.
    ERROR = "error"


@dataclass(frozen=True)
class ProjectStatus:
    state: SendState
    # The number of changes that wait.
    count: int = 0
    # The text of this state when it is not the standard one of the state.
    message: str = ""
    # What the page needs to tell one case from another: for the merge that
    # waits, the identifier of that merge.
    detail: str = ""

    @property
    def is_attention_needed(self) -> bool:
        return self.state is not SendState.IDLE


def get_state_text(state: SendState) -> str:
    """The text of a state, in the language of the application."""
    if state is SendState.SENDING:
        return gettext("Sharing your changes.")
    if state is SendState.WAITING_NETWORK:
        return gettext("Waiting for the network to share your changes.")
    if state is SendState.REFUSED:
        return gettext("The server refused your changes.")
    if state is SendState.UPDATE_NEEDED:
        return gettext("An update is needed before your changes can be shared.")
    if state is SendState.NOT_SAVED:
        return gettext("Your last change was not saved.")
    if state is SendState.OTHER_USER:
        return gettext(
            "These changes are by another user: sign in as that user to "
            "share them."
        )
    if state is SendState.SIGNED_OUT:
        return gettext("Sign in to share your changes.")
    if state is SendState.UNREADABLE:
        return gettext(
            "The project files cannot be read: nothing is saved until they "
            "are repaired."
        )
    if state is SendState.MERGE_WAITING:
        return gettext(
            "You and a colleague changed the same items: choose which "
            "version to keep."
        )
    if state is SendState.UPDATE_BLOCKED:
        return gettext(
            "An update of your colleagues is on hold: it overlaps with "
            "changes that only you can keep."
        )
    if state is SendState.FILES_KEPT:
        return gettext(
            "A file was changed by you and by a colleague: your version is "
            "kept, and theirs is saved next to it."
        )
    if state is SendState.READ_ONLY:
        return gettext("You can read this project, not share changes to it.")
    if state is SendState.OTHER_SERVER:
        return gettext(
            "The changes of this project cannot be shared from here."
        )
    if state is SendState.ERROR:
        return gettext(
            "Your changes could not be shared for now: the application will "
            "try again."
        )
    return ""


def get_indicator_title() -> str:
    return gettext("Changes not sent")


def get_status_answer(
    status: ProjectStatus, runtime: Optional[ProjectRuntime] = None
) -> Dict[str, Any]:
    """What "GET /__desktop/status" answers."""
    answer: Dict[str, Any] = {
        "state": status.state.value,
        "count": status.count,
        "message": (
            status.message
            if status.message != ""
            else get_state_text(status.state)
        ),
        "title": get_indicator_title(),
    }
    if status.detail != "":
        answer["detail"] = status.detail
    if runtime is not None:
        answer["editing"] = runtime.leases.is_editing()
        answer["revision"] = runtime.revision
        answer["update_waiting"] = runtime.is_update_waiting
    return answer


class ProjectStatusMiddleware:
    """
    Answers "GET /__desktop/status" with the status of the project, and
    "POST /__desktop/editing" with the lease of a page that has an editor open.

    The signal of the editing takes no gate and commits nothing: a page that
    types must never wait for a save, and a signal changes no file. It is
    behind the session token and the middleware of the principal, like every
    request of the project.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        get_status: Callable[[], ProjectStatus],
        runtime: Optional[ProjectRuntime] = None,
    ) -> None:
        self.app = app
        self._get_status = get_status
        self._runtime = runtime

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] == "http" and scope["path"] == STATUS_PATH:
            if scope["method"] == "GET":
                status = await anyio.to_thread.run_sync(self._get_status)
                response = JSONResponse(
                    get_status_answer(status, self._runtime),
                    headers={"Cache-Control": "no-store"},
                )
                await response(scope, receive, send)
                return
        if (
            scope["type"] == "http"
            and scope["path"] == EDITING_PATH
            and scope["method"] == "POST"
            and self._runtime is not None
        ):
            await self._answer_editing(scope, receive, send, self._runtime)
            return
        await self.app(scope, receive, send)

    async def _answer_editing(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        runtime: ProjectRuntime,
    ) -> None:
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break
            if len(body) > MAXIMUM_SIGNAL_BYTES:
                break
        page_id, is_editing = _parse_editing_signal(body)
        if page_id is None:
            response = JSONResponse({"error": "bad signal"}, status_code=400)
        else:
            if is_editing:
                runtime.leases.renew(page_id)
            else:
                runtime.leases.release(page_id)
            response = JSONResponse(
                {
                    "revision": runtime.revision,
                    "update_waiting": runtime.is_update_waiting,
                },
                headers={"Cache-Control": "no-store"},
            )
        await response(scope, receive, send)


def get_project_status(
    last_error: str,
    send_status: Optional[ProjectStatus],
    *,
    is_index_outdated: bool = False,
    merge_key: str = "",
    notice: Optional[ProjectStatus] = None,
) -> ProjectStatus:
    """
    The status of a project: a change that was not saved comes first, the
    user must see it. Then the files that cannot be read, which refuse every
    save, and the merge that waits for the user (merge_key is its
    identifier), which suspends the update and the sending. Then what the
    sending says, then the notice of the last synchronization. Without a queue,
    nothing is sent and nothing waits.
    """
    send_status = (
        send_status
        if send_status is not None
        else ProjectStatus(SendState.IDLE)
    )
    if last_error != "":
        return ProjectStatus(SendState.NOT_SAVED, send_status.count)
    if is_index_outdated:
        return ProjectStatus(SendState.UNREADABLE, send_status.count)
    if merge_key != "":
        return ProjectStatus(
            SendState.MERGE_WAITING, send_status.count, detail=merge_key
        )
    if notice is not None and notice.state is SendState.UPDATE_BLOCKED:
        return notice
    if send_status.state is not SendState.IDLE or notice is None:
        return send_status
    return notice


def _parse_editing_signal(body: bytes) -> "tuple[Optional[str], bool]":
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, False
    if not isinstance(data, dict):
        return None, False
    page_id = data.get("page")
    is_editing = data.get("editing")
    if (
        not isinstance(page_id, str)
        or not 0 < len(page_id) <= MAXIMUM_PAGE_ID_LENGTH
        or not isinstance(is_editing, bool)
    ):
        return None, False
    return page_id, is_editing
