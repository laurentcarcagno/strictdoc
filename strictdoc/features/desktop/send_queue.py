"""
The sending of the commits to the server, and the queue of what waits.

The queue is the state of Git on the disk: the commits of the branch that the
server does not have. Nothing else is kept, so nothing is lost when the
application closes, offline or not: at the launch the queue reads again every
folder of the settings, whether or not the project is open, and it never asks
the catalog (GitLab may be out of reach).

A commit goes to the server by one command that sends the commit that the
branch had when the queue read it, to the branch of that name, without force:

    git push origin <commit>:refs/heads/<branch>

It fetches nothing, merges nothing and changes no file of the working copy. The
queue reads the state under the gate of the project (project_gate.py) and runs
the command outside of it: the user saves while the network works.

What waits is sent when all of these hold, and the state says which one does
not:

- somebody is signed in, and the role of that user in the project allows to
  send (a reader sends nothing). A role that is not known, for a project that
  is not open, lets the sending try: the server decides, and its refusal is
  shown;
- every commit that the server does not have is by the signed-in user (the
  address of the author, on the whole range). One commit by another user, and
  nothing is sent;
- the project is shared with the server of the session (or with a folder of
  the disk, for the tests and the simulated catalog);
- no merge, rebase or cherry-pick waits to be finished.

A refusal because others changed the project first ("non-fast-forward") is a
state of its own: the update comes first, and the merge is for the
synchronization. It is neither a network failure nor a refusal of the rights.
A refusal of the server, a protected branch for example, is a refusal.

The queue tries again after a growing wait, up to one minute, and at once
when the user saves or when a session comes back.

@relation(SDOC-SRS-1242, scope=file)
@relation(SDOC-SRS-1243, scope=file)
@relation(SDOC-SRS-1244, scope=file)
"""

import logging
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from strictdoc.features.desktop.bundled_tools import (
    get_hidden_window_flags,
    get_system_program_environment,
)
from strictdoc.features.desktop.commit_author import get_commit_email
from strictdoc.features.desktop.git_access import (
    GIT_TOKEN_VARIABLE,
    DesktopGitService,
    GitAccess,
    UnsafeRepositoryError,
    UnsentCommits,
    check_repository_for_network,
    get_credential_origin,
)
from strictdoc.features.desktop.permissions import can_send
from strictdoc.features.desktop.project_gate import get_project_gate
from strictdoc.features.desktop.project_status import ProjectStatus, SendState
from strictdoc.features.desktop.settings import load_settings
from strictdoc.features.desktop.token_store import TokenKeeper
from strictdoc.features.git_config.git_service import GitServiceError

logger = logging.getLogger(__name__)

RETRY_FIRST_SECONDS = 1.0
RETRY_MAXIMUM_SECONDS = 60.0
# The wait of a state that no retry changes (nobody is signed in): the queue
# looks again when the session changes or the user saves, and now and then.
LONG_WAIT_SECONDS = 60.0
# A project whose gate is taken for longer than this is left for the next
# round: the queue goes on with the others.
GATE_TIMEOUT_SECONDS = 2.0
# A command that sends is stopped after this time.
PUSH_TIMEOUT_SECONDS = 120.0
# The sending of the commits of a project repeats while commits come, but not
# for ever.
MAXIMUM_ROUNDS = 5

_STATES_THAT_RETRY = frozenset(
    {
        SendState.WAITING_NETWORK,
        SendState.REFUSED,
        SendState.UPDATE_NEEDED,
        SendState.ERROR,
    }
)


@dataclass
class _FolderState:
    status: ProjectStatus
    failure_count: int = 0
    # In the clock of the queue. Zero: at the next round.
    next_attempt_at: float = 0.0
    # The wake-up of the session that this state has seen.
    generation: int = 0


@dataclass(frozen=True)
class _Decision:
    """What the queue reads under the gate: what to send, or why not."""

    status: ProjectStatus
    unsent: Optional[UnsentCommits] = None
    # The user whose address the commits were checked against.
    email: str = ""


@dataclass(frozen=True)
class SendSession:
    """
    The user who is signed in and the access token of that same session, read
    together: the commits of the user go with the token of the user.
    """

    email: str
    access_token: Optional[str]


def get_retry_delay(failure_count: int) -> float:
    """The wait before the next try: 1, 2, 4 seconds and so on, up to 60."""
    if failure_count <= 1:
        return RETRY_FIRST_SECONDS
    # A shift, and an exponent that stops growing: no huge number.
    steps = min(failure_count - 1, 16)
    return min(RETRY_FIRST_SECONDS * (1 << steps), RETRY_MAXIMUM_SECONDS)


def classify_push_failure(output: str) -> SendState:
    """
    The state that the output of a failed command tells. A refusal of the
    server comes before a refusal because others changed the project first,
    and anything else is a network that does not answer.
    """
    text = output.lower()
    if (
        "[remote rejected]" in text
        or "protected branch" in text
        or "not allowed to push" in text
        or "returned error: 403" in text
        or "returned error: 401" in text
        or "authentication failed" in text
        or "permission to" in text
        or "pre-receive hook declined" in text
    ):
        return SendState.REFUSED
    if (
        "non-fast-forward" in text
        or "fetch first" in text
        or "[rejected]" in text
        or "stale info" in text
    ):
        return SendState.UPDATE_NEEDED
    return SendState.WAITING_NETWORK


def is_destination_allowed(origin_url: str, gitlab_url: str) -> bool:
    """
    True when the changes may go to this address: a folder of the disk (the
    tests and the simulated catalog), or a server of the origin of the
    session. The scheme, the host and the port must be the ones of the session.
    """
    address = origin_url.strip()
    if address == "":
        return False
    if address.startswith("file://") or os.path.isabs(address):
        return True
    origin = get_credential_origin(address)
    return origin is not None and origin == get_credential_origin(gitlab_url)


class SendQueue:
    def __init__(
        self,
        *,
        git_access: GitAccess,
        get_folders: Callable[[], Dict[str, str]],
        get_user_email: Callable[[], Optional[str]],
        get_gitlab_url: Callable[[], str],
        get_role: Callable[[str], Optional[str]],
        clock: Callable[[], float] = time.monotonic,
        push_timeout_seconds: float = PUSH_TIMEOUT_SECONDS,
        gate_timeout_seconds: float = GATE_TIMEOUT_SECONDS,
        get_session: Optional[Callable[[], Optional[SendSession]]] = None,
    ) -> None:
        """
        get_folders gives the folders of the projects, by identifier: the
        folders that the settings remember. get_role gives the role of the
        signed-in user in a project, None when it is not known. get_session
        gives the user and the token of one session, read together: without
        it, the token is read first and the user right after, and the queue
        checks that the user is the one whose commits it looked at.
        """
        self._git_access: GitAccess = git_access
        self._get_folders: Callable[[], Dict[str, str]] = get_folders
        self._get_user_email: Callable[[], Optional[str]] = get_user_email
        self._get_gitlab_url: Callable[[], str] = get_gitlab_url
        self._get_role: Callable[[str], Optional[str]] = get_role
        self._clock: Callable[[], float] = clock
        self._push_timeout_seconds: float = push_timeout_seconds
        self._gate_timeout_seconds: float = gate_timeout_seconds
        self._get_session_function: Optional[
            Callable[[], Optional[SendSession]]
        ] = get_session
        # The folders where a commit was made since the queue looked at them,
        # and the number of the wake-ups of every folder: a wake-up that comes
        # while a folder is being sent is never lost.
        self._dirty: Set[str] = set()
        self._wake_generation: int = 0
        self._lock: threading.Lock = threading.Lock()
        self._states: Dict[str, _FolderState] = {}
        self._extra_folders: Set[str] = set()
        self._wake_event: threading.Event = threading.Event()
        self._stop_event: threading.Event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen[str]] = None

    # ---- Life of the queue

    def start(self) -> None:
        """Start the thread. The folders are read at once, at the launch."""
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="strictdoc-send-queue", daemon=True
        )
        self._thread.start()

    def stop(self, timeout_seconds: float = 5.0) -> None:
        """
        Stop the thread, and the command that sends if one runs. The closing
        of the application does not wait for the network. Nothing is lost: what
        was not sent is in Git, and the next launch reads it.
        """
        self._stop_event.set()
        self._wake_event.set()
        with self._lock:
            process = self._process
        if process is not None:
            _stop_process(process)
        thread = self._thread
        if thread is not None:
            thread.join(timeout_seconds)
        self._thread = None

    # ---- What the application tells the queue

    def notify(self, folder: str) -> None:
        """A commit was made in the folder: send it now."""
        key = _get_key(folder)
        with self._lock:
            self._extra_folders.add(key)
            self._dirty.add(key)
            state = self._states.get(key)
            if state is not None:
                state.next_attempt_at = 0.0
                state.failure_count = 0
        self._wake_event.set()

    def wake(self) -> None:
        """Try again now, for every folder: a session came back or went."""
        with self._lock:
            self._wake_generation += 1
            for state_ in self._states.values():
                state_.next_attempt_at = 0.0
                state_.failure_count = 0
        self._wake_event.set()

    def get_status(self, folder: str) -> ProjectStatus:
        with self._lock:
            state = self._states.get(_get_key(folder))
        return (
            state.status if state is not None else ProjectStatus(SendState.IDLE)
        )

    # ---- The work

    def run_once(self, *, is_forced: bool = False) -> None:
        """
        Look at every folder whose time has come, or every folder when forced.
        The thread calls it in a loop.
        """
        folders = self._list_folders()
        # The wait of the thread is computed on the folders that are followed:
        # a folder that left the settings is forgotten, its due time with it.
        with self._lock:
            tracked = {_get_key(folder_) for folder_ in folders}
            for key_ in [key_ for key_ in self._states if key_ not in tracked]:
                del self._states[key_]
            self._dirty &= tracked
        for folder_ in folders:
            if self._stop_event.is_set():
                return
            key = _get_key(folder_)
            with self._lock:
                state = self._states.get(key)
                is_due = (
                    is_forced
                    or state is None
                    or state.next_attempt_at <= self._clock()
                    or key in self._dirty
                    or state.generation != self._wake_generation
                )
            if is_due:
                self._process_folder_safely(folder_)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception:
                logger.exception("The queue of the sending failed.")
            self._wake_event.wait(self._get_seconds_until_next_attempt())
            self._wake_event.clear()

    def _get_seconds_until_next_attempt(self) -> float:
        with self._lock:
            due = [
                0.0
                if state_.generation != self._wake_generation
                else state_.next_attempt_at - self._clock()
                for state_ in self._states.values()
            ]
            if len(self._dirty) > 0:
                due.append(0.0)
        if len(due) == 0:
            return LONG_WAIT_SECONDS
        return max(0.1, min(*due, LONG_WAIT_SECONDS))

    def _list_folders(self) -> List[str]:
        folders = {
            _get_key(folder_) for folder_ in self._get_folders().values()
        }
        with self._lock:
            folders |= self._extra_folders
        return sorted(folders)

    def _process_folder_safely(self, folder: str) -> None:
        """Look at a folder. An error of this folder is its own state."""
        try:
            self._process_folder(folder)
        except Exception:
            logger.exception("The sending of a project failed.")
            key = _get_key(folder)
            with self._lock:
                state = self._states.get(key)
                count = state.status.count if state is not None else 0
            self._record(key, ProjectStatus(SendState.ERROR, count))

    def _process_folder(self, folder: str) -> None:
        key = _get_key(folder)
        with self._lock:
            self._dirty.discard(key)
            generation = self._wake_generation
            state = self._states.get(key)
            if state is not None:
                state.generation = generation
        has_more = False
        for _ in range(MAXIMUM_ROUNDS):
            if self._stop_event.is_set():
                return
            has_more = self._process_round(folder)
            if not has_more:
                break
        with self._lock:
            state = self._states.get(key)
            if state is None:
                return
            state.generation = generation
            # What was asked for while the folder was sent, and what the
            # rounds did not reach, is for the next round: at once.
            if (
                has_more
                or key in self._dirty
                or generation != self._wake_generation
            ):
                state.next_attempt_at = 0.0
                state.failure_count = 0

    def _process_round(self, folder: str) -> bool:
        """One look at a folder. True when a commit was sent: look again."""
        key = _get_key(folder)
        if not os.path.isdir(folder):
            # A folder that is gone is not an error: it is forgotten.
            self._forget(key)
            return False
        service = DesktopGitService(folder, self._git_access)
        gate = get_project_gate(folder)
        if not gate.acquire(timeout=self._gate_timeout_seconds):
            # The project is busy: the next round, the others go first.
            self._postpone(key)
            return False
        try:
            decision = self._read_state(service, folder)
        except (GitServiceError, OSError):
            # Not a repository: nothing to send.
            self._forget(key)
            return False
        finally:
            gate.release()
        if decision.unsent is None:
            self._record(key, decision.status)
            return False
        unsent = decision.unsent
        self._record(key, ProjectStatus(SendState.SENDING, unsent.count))
        state, was_sent = self._send(folder, unsent, decision.email)
        self._record(key, ProjectStatus(state, unsent.count))
        return was_sent

    def _read_state(self, service: DesktopGitService, folder: str) -> _Decision:
        """What there is to send, or why nothing goes. Call it with the gate."""
        unsent = service.read_unsent_commits(folder)
        if unsent is None or unsent.count == 0:
            return _Decision(ProjectStatus(SendState.IDLE))
        count = unsent.count
        email = self._get_user_email()
        if email is None:
            return _Decision(ProjectStatus(SendState.SIGNED_OUT, count))
        if not can_send(self._get_role_of_folder(folder)):
            return _Decision(ProjectStatus(SendState.READ_ONLY, count))
        if any(
            author_.casefold() != email.casefold()
            for author_ in unsent.author_emails
        ):
            return _Decision(ProjectStatus(SendState.OTHER_USER, count))
        # Every address that the push writes to, not only the one that the
        # fetch reads: "pushurl" and "pushInsteadOf" change it.
        if not all(
            is_destination_allowed(destination_, self._get_gitlab_url())
            for destination_ in unsent.get_destinations()
        ):
            return _Decision(ProjectStatus(SendState.OTHER_SERVER, count))
        if service.is_operation_in_progress(folder):
            return _Decision(ProjectStatus(SendState.UPDATE_NEEDED, count))
        return _Decision(ProjectStatus(SendState.IDLE, count), unsent, email)

    def _get_role_of_folder(self, folder: str) -> Optional[str]:
        key = _get_key(folder)
        for identifier_, project_folder_ in self._get_folders().items():
            if _get_key(project_folder_) == key:
                return self._get_role(identifier_)
        return None

    def _read_session(self) -> Optional[SendSession]:
        if self._get_session_function is not None:
            return self._get_session_function()
        # The token first, the user right after: if the session changed in
        # between, the user is not the one that was checked.
        token = self._git_access.get_access_token()
        email = self._get_user_email()
        return SendSession(email, token) if email is not None else None

    def _send(
        self, folder: str, unsent: UnsentCommits, email: str
    ) -> "tuple[SendState, bool]":
        """
        Send the commit that was read, outside of the gate. It returns the new
        state, and whether the commit went. The commits were checked against
        the user of the moment; the session that gives the token is read now,
        and it must be the one of that user.
        """
        session = self._read_session()
        if session is None:
            return SendState.SIGNED_OUT, False
        if session.email.casefold() != email.casefold():
            return SendState.OTHER_USER, False
        environment = self._git_access.build_environment(
            credentials=(self._get_gitlab_url(), session.access_token)
        )
        if GIT_TOKEN_VARIABLE not in environment and not all(
            is_destination_local(destination_)
            for destination_ in unsent.get_destinations()
        ):
            # The access token has ended and could not be renewed: the
            # network is the cause, the renewal comes with it.
            return SendState.WAITING_NETWORK, False
        try:
            check_repository_for_network(folder, environment)
        except UnsafeRepositoryError:
            return SendState.OTHER_SERVER, False
        output = self._run_push(folder, unsent, environment)
        if output is None:
            return SendState.IDLE, True
        return classify_push_failure(output), False

    def _run_push(
        self,
        folder: str,
        unsent: UnsentCommits,
        environment: Dict[str, str],
    ) -> Optional[str]:
        """
        Run the command. It returns None when the commit went, else the text
        that the command wrote. There is no force, no fetch and no merge.
        """
        try:
            process = subprocess.Popen(
                [
                    "git",
                    "push",
                    "origin",
                    f"{unsent.head}:refs/heads/{unsent.branch}",
                ],
                cwd=folder,
                # The text of Git is read: it is not translated.
                env=get_system_program_environment(
                    {
                        **os.environ,
                        **environment,
                        "LC_ALL": "C",
                        "LANGUAGE": "",
                    }
                ),
                creationflags=get_hidden_window_flags(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf8",
                errors="replace",
                # Its own group: the program that talks to the server is a
                # child of the command, and stops with it.
                start_new_session=os.name != "nt",
            )
        except OSError as error:
            return str(error)
        with self._lock:
            self._process = process
        try:
            output, _ = process.communicate(timeout=self._push_timeout_seconds)
        except subprocess.TimeoutExpired:
            _stop_process(process)
            return "timed out"
        finally:
            with self._lock:
                self._process = None
        if process.returncode == 0:
            return None
        return output if output is not None else ""

    def _record(self, key: str, status: ProjectStatus) -> None:
        with self._lock:
            state = self._states.get(key)
            if state is None:
                state = _FolderState(status, generation=self._wake_generation)
                self._states[key] = state
            state.status = status
            now = self._clock()
            if status.state in _STATES_THAT_RETRY:
                state.failure_count += 1
                state.next_attempt_at = now + get_retry_delay(
                    state.failure_count
                )
            elif status.state is SendState.SENDING:
                pass
            elif status.state is SendState.IDLE:
                state.failure_count = 0
                state.next_attempt_at = now + LONG_WAIT_SECONDS
            else:
                state.next_attempt_at = now + LONG_WAIT_SECONDS

    def _postpone(self, key: str) -> None:
        """Leave a busy project for a short time, with no change of state."""
        with self._lock:
            state = self._states.get(key)
            if state is None:
                state = _FolderState(
                    ProjectStatus(SendState.IDLE),
                    generation=self._wake_generation,
                )
                self._states[key] = state
            state.next_attempt_at = self._clock() + RETRY_FIRST_SECONDS

    def _forget(self, key: str) -> None:
        with self._lock:
            self._states.pop(key, None)
            self._extra_folders.discard(key)


def is_destination_local(origin_url: str) -> bool:
    """True for a folder of the disk: no token is needed to reach it."""
    address = origin_url.strip()
    return address.startswith("file://") or os.path.isabs(address)


def create_send_queue(
    *,
    keeper: TokenKeeper,
    git_access: GitAccess,
    settings_path: Optional[Path],
    get_role: Callable[[str], Optional[str]],
) -> SendQueue:
    """
    The queue of the application: the folders of the settings, the user of the
    session, the roles that the catalog gave. A change of the session wakes it.
    """

    def get_user_email() -> Optional[str]:
        session = keeper.session
        if session is None:
            return None
        return get_commit_email(session.user, keeper.gitlab_url)

    def get_session() -> Optional[SendSession]:
        # The renewal may use the network: this is called outside of the gate.
        # The token and the user are read from the same session object.
        for _ in range(3):
            token = keeper.get_access_token()
            session = keeper.session
            if session is None:
                return None
            email = get_commit_email(session.user, keeper.gitlab_url)
            if token is None:
                return SendSession(email, None)
            if session.tokens.access_token == token:
                return SendSession(email, token)
        return None

    queue = SendQueue(
        git_access=git_access,
        get_folders=lambda: dict(load_settings(settings_path).project_folders),
        get_user_email=get_user_email,
        get_gitlab_url=lambda: keeper.gitlab_url,
        get_role=get_role,
        get_session=get_session,
    )
    keeper.add_session_listener(queue.wake)
    return queue


def _get_key(folder: str) -> str:
    return os.path.normcase(os.path.realpath(folder))


def _stop_process(process: subprocess.Popen[str]) -> None:
    """Stop the command and the programs that it started."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
                timeout=10,
                creationflags=get_hidden_window_flags(),
            )
        else:
            os.killpg(process.pid, signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        pass
