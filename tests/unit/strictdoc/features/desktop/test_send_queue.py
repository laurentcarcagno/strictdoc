"""
The queue that sends the commits to the server. The tests run the real Git on
bare repositories of the disk, and a server that does not answer for the
shutdown. Nothing reaches the network or reads a credential of the computer.

@relation(SDOC-SRS-1242, scope=file)
@relation(SDOC-SRS-1243, scope=file)
@relation(SDOC-SRS-1244, scope=file)
"""

import os
import socket
import stat
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pytest
from git import Actor, Repo

from strictdoc.features.desktop import send_queue as send_queue_module
from strictdoc.features.desktop.git_access import DesktopGitService, GitAccess
from strictdoc.features.desktop.oauth_gitlab import (
    GitLabSession,
    GitLabTokens,
    GitLabUser,
)
from strictdoc.features.desktop.project_gate import get_project_gate
from strictdoc.features.desktop.project_principals import ProjectPrincipals
from strictdoc.features.desktop.project_status import SendState
from strictdoc.features.desktop.secret_store import MemorySecretStore
from strictdoc.features.desktop.send_queue import (
    SendQueue,
    classify_push_failure,
    create_send_queue,
    get_retry_delay,
    is_destination_allowed,
)
from strictdoc.features.desktop.settings import (
    DesktopSettings,
    save_settings,
)
from strictdoc.features.desktop.token_store import TokenKeeper
from strictdoc.features.project_catalog.catalog import CatalogRole

SEED = Actor("Seed", "seed@example.org")
JEANNE = Actor("Jeanne Dupont", "jeanne@example.org")
OTHER = Actor("Paul Martin", "paul@example.org")
GITLAB_URL = "http://127.0.0.1:9"


class Clock:
    def __init__(self) -> None:
        self.now: float = 1000.0

    def __call__(self) -> float:
        return self.now


@dataclass
class Setup:
    bare: Path
    workspace: Path
    queue: SendQueue
    clock: Clock
    # What the queue reads about the user, and the user can change.
    user: Dict[str, Optional[str]]

    def commit(self, actor: Actor = JEANNE, text: str = "x") -> str:
        """A commit in the working copy, as a save would make it."""
        repo = Repo(self.workspace)
        (self.workspace / "doc.sdoc").write_text(f"[DOCUMENT]\nTITLE: {text}\n")
        repo.index.add(["doc.sdoc"])
        commit = repo.index.commit(text, author=actor, committer=actor)
        repo.close()
        return str(commit.hexsha)

    def get_bare_head(self) -> str:
        repo = Repo(self.bare)
        try:
            return str(repo.commit("main").hexsha)
        finally:
            repo.close()

    def get_state(self) -> SendState:
        return self.queue.get_status(str(self.workspace)).state

    def make_bare_unreachable(self) -> Path:
        moved = self.bare.with_name("remote-away.git")
        self.bare.rename(moved)
        return moved

    def make_bare_reachable(self, moved: Path) -> None:
        moved.rename(self.bare)


def _create_setup(tmp_path: Path) -> Setup:
    work = tmp_path / "work"
    work.mkdir()
    (work / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: Seed\n")
    repo = Repo.init(work, initial_branch="main")
    repo.index.add(["doc.sdoc"])
    repo.index.commit("Seed", author=SEED, committer=SEED)
    repo.close()
    bare = tmp_path / "remote.git"
    Repo.clone_from(str(work), str(bare), bare=True).close()
    workspace = tmp_path / "workspace"
    Repo.clone_from(str(bare), str(workspace)).close()
    clock = Clock()
    user: Dict[str, Optional[str]] = {
        "email": JEANNE.email,
        "role": CatalogRole.AUTHOR.value,
    }
    queue = SendQueue(
        git_access=GitAccess(),
        get_folders=lambda: {"project": str(workspace)},
        get_user_email=lambda: user["email"],
        get_gitlab_url=lambda: GITLAB_URL,
        get_role=lambda _: user["role"],
        clock=clock,
        push_timeout_seconds=30,
    )
    return Setup(bare, workspace, queue, clock, user)


@pytest.fixture(name="setup")
def fixture_setup(tmp_path: Path) -> Iterator[Setup]:
    setup = _create_setup(tmp_path)
    yield setup
    setup.queue.stop()


def test_001_a_commit_is_sent_and_the_queue_is_empty(setup: Setup) -> None:
    sha = setup.commit()

    setup.queue.run_once()

    assert setup.get_bare_head() == sha
    status = setup.queue.get_status(str(setup.workspace))
    assert status.state is SendState.IDLE
    assert status.count == 0


def test_002_the_queue_is_what_git_has_on_the_disk(setup: Setup) -> None:
    setup.commit(text="one")
    setup.commit(text="two")
    setup.user["email"] = None

    setup.queue.run_once()

    # Nothing was sent, and the count is the one of the commits in advance.
    status = setup.queue.get_status(str(setup.workspace))
    assert status.state is SendState.SIGNED_OUT
    assert status.count == 2


def test_003_a_server_out_of_reach_keeps_the_commit_and_the_retry_comes(
    setup: Setup,
) -> None:
    sha = setup.commit()
    moved = setup.make_bare_unreachable()

    setup.queue.run_once()

    status = setup.queue.get_status(str(setup.workspace))
    assert status.state is SendState.WAITING_NETWORK
    assert status.count == 1
    setup.make_bare_reachable(moved)
    # The wait of the first retry is one second: not yet.
    setup.queue.run_once()
    assert setup.get_state() is SendState.WAITING_NETWORK
    setup.clock.now += 1.1
    setup.queue.run_once()
    assert setup.get_bare_head() == sha
    assert setup.get_state() is SendState.IDLE


def test_004_the_wait_grows_and_stops_at_one_minute() -> None:
    delays = [get_retry_delay(count_) for count_ in range(1, 12)]

    assert delays == [1, 2, 4, 8, 16, 32, 60, 60, 60, 60, 60]
    # The first failure waits one second, then it doubles.
    assert get_retry_delay(1) == 1
    assert get_retry_delay(2) == 2
    assert get_retry_delay(30) == 60


def test_005_a_save_or_a_new_session_tries_again_at_once(
    setup: Setup,
) -> None:
    sha = setup.commit()
    moved = setup.make_bare_unreachable()
    setup.queue.run_once()
    setup.clock.now += 1.1
    setup.queue.run_once()
    assert setup.get_state() is SendState.WAITING_NETWORK
    setup.make_bare_reachable(moved)

    # Far from the next try, and a session comes back: now.
    setup.queue.wake()
    setup.queue.run_once()

    assert setup.get_bare_head() == sha


def test_006_one_commit_of_another_user_stops_everything(
    setup: Setup,
) -> None:
    before = setup.get_bare_head()
    setup.commit(JEANNE, "mine")
    setup.commit(OTHER, "not mine")
    setup.commit(JEANNE, "mine again")

    setup.queue.run_once()

    assert setup.get_bare_head() == before
    status = setup.queue.get_status(str(setup.workspace))
    assert status.state is SendState.OTHER_USER
    assert status.count == 3


def test_007_the_same_user_sends_again_when_the_other_user_leaves(
    setup: Setup,
) -> None:
    sha = setup.commit(OTHER, "not mine")
    setup.queue.run_once()
    assert setup.get_state() is SendState.OTHER_USER

    # The user of these commits signs in.
    setup.user["email"] = OTHER.email
    setup.queue.wake()
    setup.queue.run_once()

    assert setup.get_bare_head() == sha


def test_008_the_commits_that_the_server_has_are_not_checked(
    setup: Setup, tmp_path: Path
) -> None:
    # A colleague puts a commit on the server, and this copy has it.
    colleague = tmp_path / "colleague"
    Repo.clone_from(str(setup.bare), str(colleague)).close()
    repo = Repo(colleague)
    (colleague / "other.sdoc").write_text("[DOCUMENT]\nTITLE: Other\n")
    repo.index.add(["other.sdoc"])
    repo.index.commit("Colleague", author=OTHER, committer=OTHER)
    repo.git.push("origin", "main")
    repo.close()
    workspace_repo = Repo(setup.workspace)
    workspace_repo.git.pull("--ff-only")
    workspace_repo.close()
    sha = setup.commit(JEANNE, "mine")

    setup.queue.run_once()

    assert setup.get_bare_head() == sha
    assert setup.get_state() is SendState.IDLE


def test_009_the_commit_that_was_read_is_the_one_that_goes(
    setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = setup.commit(text="first")
    original = setup.queue._run_push
    pushed: List[str] = []

    def run_push(
        folder: str, unsent: Any, environment: Dict[str, str]
    ) -> Optional[str]:
        if len(pushed) == 0:
            # A save comes while the network works.
            setup.commit(text="second")
        pushed.append(unsent.head)
        result = original(folder, unsent, environment)
        if len(pushed) == 1:
            assert setup.get_bare_head() == first
        return result

    monkeypatch.setattr(setup.queue, "_run_push", run_push)

    setup.queue.run_once()

    # The second save went in the next round of the same look.
    assert pushed[0] == first
    assert len(pushed) == 2
    assert setup.get_bare_head() == pushed[1]


def test_010_the_command_is_a_simple_push_of_the_commit(
    setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = setup.commit()
    arguments_list: List[List[str]] = []
    original = subprocess.Popen

    def popen(arguments: List[str], *args: Any, **kwargs: Any) -> Any:
        if arguments[1:2] == ["push"]:
            arguments_list.append(list(arguments))
        return original(arguments, *args, **kwargs)

    monkeypatch.setattr(send_queue_module.subprocess, "Popen", popen)

    setup.queue.run_once()

    assert arguments_list == [
        ["git", "push", "origin", f"{sha}:refs/heads/main"]
    ]


def test_011_a_commit_that_others_passed_is_an_update_to_make(
    setup: Setup, tmp_path: Path
) -> None:
    colleague = tmp_path / "colleague"
    Repo.clone_from(str(setup.bare), str(colleague)).close()
    repo = Repo(colleague)
    (colleague / "other.sdoc").write_text("[DOCUMENT]\nTITLE: Other\n")
    repo.index.add(["other.sdoc"])
    repo.index.commit("Colleague", author=OTHER, committer=OTHER)
    repo.git.push("origin", "main")
    repo.close()
    colleague_head = setup.get_bare_head()
    setup.commit()
    workspace_before = (setup.workspace / "doc.sdoc").read_text()

    setup.queue.run_once()

    status = setup.queue.get_status(str(setup.workspace))
    # Neither a network failure nor a refusal of the rights.
    assert status.state is SendState.UPDATE_NEEDED
    assert status.count == 1
    # No force: the server is as the colleague left it. No fetch, no merge:
    # the working copy is as it was.
    assert setup.get_bare_head() == colleague_head
    assert (setup.workspace / "doc.sdoc").read_text() == workspace_before
    workspace_repo = Repo(setup.workspace)
    assert workspace_repo.git.rev_parse("origin/main") != colleague_head
    workspace_repo.close()


def test_012_a_refusal_of_the_server_is_a_refusal(setup: Setup) -> None:
    hook = setup.bare / "hooks" / "pre-receive"
    hook.write_text(
        "#!/bin/sh\n"
        "echo 'remote: You are not allowed to push code to protected "
        "branches on this project.' >&2\n"
        "exit 1\n"
    )
    hook.chmod(hook.stat().st_mode | stat.S_IEXEC)
    before = setup.get_bare_head()
    setup.commit()

    setup.queue.run_once()

    status = setup.queue.get_status(str(setup.workspace))
    assert status.state is SendState.REFUSED
    assert status.count == 1
    assert setup.get_bare_head() == before


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (
            "! [rejected] a:refs/heads/main [rejected] (non-fast-forward)",
            SendState.UPDATE_NEEDED,
        ),
        ("hint: Updates were rejected (fetch first)", SendState.UPDATE_NEEDED),
        (
            "! [remote rejected] main -> main (pre-receive hook declined)",
            SendState.REFUSED,
        ),
        (
            (
                "remote: GitLab: You are not allowed to push code to "
                "protected branches on this project."
            ),
            SendState.REFUSED,
        ),
        (
            (
                "fatal: unable to access 'https://x/': The requested URL "
                "returned error: 403"
            ),
            SendState.REFUSED,
        ),
        ("fatal: Authentication failed for 'https://x/'", SendState.REFUSED),
        (
            "fatal: unable to access 'https://x/': Could not resolve host: x",
            SendState.WAITING_NETWORK,
        ),
        (
            (
                "fatal: unable to access 'http://127.0.0.1:1/': Failed to "
                "connect to 127.0.0.1 port 1"
            ),
            SendState.WAITING_NETWORK,
        ),
        (
            "fatal: '/gone/remote.git' does not appear to be a git repository",
            SendState.WAITING_NETWORK,
        ),
        ("timed out", SendState.WAITING_NETWORK),
    ],
)
def test_013_the_text_of_a_failed_command_tells_the_state(
    output: str, expected: SendState
) -> None:
    assert classify_push_failure(output) is expected


def test_014_nobody_signed_in_sends_nothing_and_loses_nothing(
    setup: Setup,
) -> None:
    before = setup.get_bare_head()
    sha = setup.commit()
    setup.user["email"] = None

    setup.queue.run_once()
    assert setup.get_state() is SendState.SIGNED_OUT
    assert setup.get_bare_head() == before

    # The same user comes back: it goes.
    setup.user["email"] = JEANNE.email
    setup.queue.wake()
    setup.queue.run_once()

    assert setup.get_bare_head() == sha


def test_015_a_reader_sends_nothing_and_an_unknown_role_tries(
    setup: Setup,
) -> None:
    before = setup.get_bare_head()
    sha = setup.commit()
    setup.user["role"] = CatalogRole.READER.value

    setup.queue.run_once()
    assert setup.get_state() is SendState.READ_ONLY
    assert setup.get_bare_head() == before

    # The project was not opened in this session: the role is not known, and
    # the server decides.
    setup.user["role"] = None
    setup.queue.wake()
    setup.queue.run_once()
    assert setup.get_bare_head() == sha


def test_016_the_changes_go_to_the_server_of_the_session_only(
    setup: Setup,
) -> None:
    setup.commit()
    repo = Repo(setup.workspace)
    repo.git.remote("set-url", "origin", "http://other.example.org/x.git")
    repo.close()

    setup.queue.run_once()

    assert setup.get_state() is SendState.OTHER_SERVER


@pytest.mark.parametrize(
    ("origin_url", "expected"),
    [
        ("http://127.0.0.1:9/team/project.git", True),
        ("http://127.0.0.1:10/team/project.git", False),
        ("https://127.0.0.1:9/team/project.git", False),
        ("http://localhost:9/team/project.git", False),
        ("ssh://git@127.0.0.1:9/team/project.git", False),
        ("git@127.0.0.1:team/project.git", False),
        ("file:///data/remote.git", True),
        ("/data/remote.git", True),
        ("", False),
    ],
)
def test_017_the_destination_is_the_origin_of_the_session_or_a_folder(
    origin_url: str, expected: bool
) -> None:
    assert is_destination_allowed(origin_url, GITLAB_URL) is expected


def test_018_a_merge_that_waits_blocks_the_sending(setup: Setup) -> None:
    before = setup.get_bare_head()
    setup.commit()
    repo = Repo(setup.workspace)
    (Path(repo.git_dir) / "MERGE_HEAD").write_text(
        f"{repo.head.commit.hexsha}\n"
    )
    repo.close()

    setup.queue.run_once()

    assert setup.get_state() is SendState.UPDATE_NEEDED
    assert setup.get_bare_head() == before


def test_019_a_folder_that_is_gone_is_ignored(tmp_path: Path) -> None:
    queue = SendQueue(
        git_access=GitAccess(),
        get_folders=lambda: {
            "gone": str(tmp_path / "nowhere"),
            "empty": str(tmp_path),
        },
        get_user_email=lambda: JEANNE.email,
        get_gitlab_url=lambda: GITLAB_URL,
        get_role=lambda _: None,
    )

    queue.run_once()

    assert queue.get_status(str(tmp_path / "nowhere")).state is SendState.IDLE


def test_020_a_branch_that_the_server_lacks_goes_with_all_its_commits(
    setup: Setup,
) -> None:
    repo = Repo(setup.workspace)
    repo.git.checkout("-b", "feature")
    repo.close()
    sha = setup.commit(text="on the feature")

    setup.queue.run_once()

    server = Repo(setup.bare)
    assert server.commit("feature").hexsha == sha
    server.close()
    assert setup.get_state() is SendState.IDLE


# The launch, the sign-out and the closing, with the real keeper.


def _create_session(user: GitLabUser) -> GitLabSession:
    return GitLabSession(
        tokens=GitLabTokens("access", "refresh", time.time() + 7200),
        user=user,
    )


def _create_user(email: str = JEANNE.email) -> GitLabUser:
    return GitLabUser(
        username="jdupont", display_name="Jeanne Dupont", email=email, user_id=7
    )


def _wait_for(condition: Any, seconds: float = 20.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture(name="keeper")
def fixture_keeper() -> Iterator[TokenKeeper]:
    keeper = TokenKeeper(MemorySecretStore(), use_timer=False)
    yield keeper
    keeper.close()


def test_021_the_launch_sends_what_waited_for_every_folder_of_the_settings(
    tmp_path: Path, keeper: TokenKeeper
) -> None:
    setup = _create_setup(tmp_path)
    sha = setup.commit()
    settings_path = tmp_path / "settings.json"
    save_settings(
        DesktopSettings(project_folders={"p": str(setup.workspace)}),
        settings_path,
    )
    keeper.adopt(
        gitlab_url=GITLAB_URL,
        client_id="client",
        session=_create_session(_create_user()),
    )
    # No server of a project, no catalog: the queue reads the settings.
    queue = create_send_queue(
        keeper=keeper,
        git_access=GitAccess(),
        settings_path=settings_path,
        get_role=lambda _: None,
    )
    try:
        queue.start()

        assert _wait_for(lambda: setup.get_bare_head() == sha)
    finally:
        queue.stop()


def test_022_the_sign_out_stops_the_sending_and_the_same_user_resumes_it(
    tmp_path: Path, keeper: TokenKeeper
) -> None:
    setup = _create_setup(tmp_path)
    before = setup.get_bare_head()
    settings_path = tmp_path / "settings.json"
    save_settings(
        DesktopSettings(project_folders={"p": str(setup.workspace)}),
        settings_path,
    )
    session = _create_session(_create_user())
    keeper.adopt(gitlab_url=GITLAB_URL, client_id="client", session=session)
    queue = create_send_queue(
        keeper=keeper,
        git_access=GitAccess(),
        settings_path=settings_path,
        get_role=lambda _: None,
    )
    sha = setup.commit()
    try:
        keeper.sign_out()
        queue.run_once(is_forced=True)

        assert queue.get_status(str(setup.workspace)).state is (
            SendState.SIGNED_OUT
        )
        assert setup.get_bare_head() == before
        # Nothing was erased: the commit is in the working copy.
        workspace_repo = Repo(setup.workspace)
        assert workspace_repo.head.commit.hexsha == sha
        workspace_repo.close()

        # Another user signs in: the commit is not theirs.
        keeper.adopt(
            gitlab_url=GITLAB_URL,
            client_id="client",
            session=_create_session(_create_user("someone@example.org")),
        )
        queue.run_once(is_forced=True)
        assert queue.get_status(str(setup.workspace)).state is (
            SendState.OTHER_USER
        )
        assert setup.get_bare_head() == before

        # The same user comes back.
        keeper.adopt(gitlab_url=GITLAB_URL, client_id="client", session=session)
        queue.run_once(is_forced=True)
        assert setup.get_bare_head() == sha
    finally:
        queue.stop()


def test_023_the_roles_of_the_catalog_come_from_the_principals(
    keeper: TokenKeeper,
) -> None:
    principals = ProjectPrincipals(keeper)
    assert principals.get_role("p") is None
    keeper.adopt(
        gitlab_url=GITLAB_URL,
        client_id="client",
        session=_create_session(_create_user()),
    )
    assert principals.get_role("p") is None

    principals.set_role("p", CatalogRole.READER)
    assert principals.get_role("p") == "reader"
    principals.set_role("p", CatalogRole.AUTHOR)
    assert principals.get_role("p") == "author"
    keeper.sign_out()
    assert principals.get_role("p") is None


def test_024_the_closing_does_not_wait_for_the_network_and_leaves_no_lock(
    tmp_path: Path,
) -> None:
    setup = _create_setup(tmp_path)
    # A server that takes the connection and never answers.
    silent_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    silent_socket.bind(("127.0.0.1", 0))
    silent_socket.listen(5)
    silent_url = f"http://127.0.0.1:{silent_socket.getsockname()[1]}"
    repo = Repo(setup.workspace)
    repo.git.remote("set-url", "origin", f"{silent_url}/team/project.git")
    repo.close()
    queue = SendQueue(
        git_access=GitAccess(
            get_gitlab_url=lambda: silent_url,
            get_access_token=lambda: "token-of-the-test",
        ),
        get_folders=lambda: {"p": str(setup.workspace)},
        get_user_email=lambda: JEANNE.email,
        get_gitlab_url=lambda: silent_url,
        get_role=lambda _: None,
    )
    sha = setup.commit()
    try:
        queue.start()
        assert _wait_for(lambda: queue._process is not None)
        # The command waits for the network, and the gate of the project is
        # free: the user saves meanwhile.
        gate = get_project_gate(str(setup.workspace))
        assert gate._lock.acquire(timeout=1)
        gate.release()

        started = time.monotonic()
        queue.stop()

        assert time.monotonic() - started < 5
        assert queue._thread is None
        assert not os.path.exists(setup.workspace / ".git" / "index.lock")
        # The commit is still there for the next launch.
        workspace_repo = Repo(setup.workspace)
        assert workspace_repo.head.commit.hexsha == sha
        workspace_repo.close()
    finally:
        queue.stop()
        silent_socket.close()


# What the queue does not lose, does not hold and does not mix up.


def _create_queue(setup: Setup, **options: Any) -> SendQueue:
    return SendQueue(
        git_access=options.pop("git_access", GitAccess()),
        get_folders=lambda: {"project": str(setup.workspace)},
        get_user_email=lambda: setup.user["email"],
        get_gitlab_url=lambda: GITLAB_URL,
        get_role=lambda _: setup.user["role"],
        clock=setup.clock,
        **options,
    )


def test_025_a_project_that_holds_its_gate_does_not_stop_the_others(
    tmp_path: Path,
) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = _create_setup(tmp_path / "a")
    second = _create_setup(tmp_path / "b")
    sha = second.commit()
    first.commit()
    clock = Clock()
    queue = SendQueue(
        git_access=GitAccess(),
        get_folders=lambda: {
            "first": str(first.workspace),
            "second": str(second.workspace),
        },
        get_user_email=lambda: JEANNE.email,
        get_gitlab_url=lambda: GITLAB_URL,
        get_role=lambda _: None,
        clock=clock,
        gate_timeout_seconds=0.2,
    )
    first_before = first.get_bare_head()
    gate = get_project_gate(str(first.workspace))
    gate.acquire()
    thread = threading.Thread(target=lambda: queue.run_once(is_forced=True))
    try:
        thread.start()
        thread.join(15)

        # The queue went on to the other project, and came back to this one
        # later: nothing was sent from it, nothing is wrong with it.
        assert not thread.is_alive()
        assert second.get_bare_head() == sha
        assert first.get_bare_head() == first_before
        assert queue.get_status(str(first.workspace)).state is not (
            SendState.REFUSED
        )
    finally:
        gate.release()
        thread.join(15)

    clock.now += 5
    queue.run_once()
    assert first.get_bare_head() != first_before


def _count_pushes(setup: Setup, monkeypatch: pytest.MonkeyPatch) -> List[str]:
    original = setup.queue._run_push
    heads: List[str] = []

    def run_push(
        folder: str, unsent: Any, environment: Dict[str, str]
    ) -> Optional[str]:
        heads.append(unsent.head)
        return original(folder, unsent, environment)

    monkeypatch.setattr(setup.queue, "_run_push", run_push)
    return heads


@pytest.mark.parametrize("wake_all", [False, True], ids=["notify", "wake"])
def test_026_a_wake_up_during_the_sending_is_not_lost(
    setup: Setup, monkeypatch: pytest.MonkeyPatch, wake_all: bool
) -> None:
    setup.commit()
    attempts: List[int] = []

    def run_push(
        folder: str, unsent: Any, environment: Dict[str, str]
    ) -> Optional[str]:
        del unsent, environment
        attempts.append(1)
        # A save, or a session that comes back, while the network works.
        if len(attempts) == 1:
            if wake_all:
                setup.queue.wake()
            else:
                setup.queue.notify(folder)
        return "fatal: unable to access 'http://x/': Could not resolve host"

    monkeypatch.setattr(setup.queue, "_run_push", run_push)

    setup.queue.run_once()
    assert len(attempts) == 1
    # No wait of the clock: the wake-up asked for the next try at once.
    setup.queue.run_once()

    assert len(attempts) == 2


def test_027_what_is_left_after_the_rounds_is_tried_at_once(
    setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup.commit(text="first")
    original = setup.queue._run_push
    pushes: List[int] = []

    def run_push(
        folder: str, unsent: Any, environment: Dict[str, str]
    ) -> Optional[str]:
        pushes.append(1)
        # Saves keep coming while the commits go.
        setup.commit(text=f"more {len(pushes)}")
        return original(folder, unsent, environment)

    monkeypatch.setattr(setup.queue, "_run_push", run_push)

    setup.queue.run_once()
    first_run = len(pushes)
    setup.queue.run_once()

    assert first_run == send_queue_module.MAXIMUM_ROUNDS
    assert len(pushes) > first_run


def test_028_an_error_in_one_folder_does_not_stop_the_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    broken = _create_setup(tmp_path / "a")
    working = _create_setup(tmp_path / "b")
    broken.commit()
    sha = working.commit()
    clock = Clock()
    queue = SendQueue(
        git_access=GitAccess(),
        get_folders=lambda: {
            "broken": str(broken.workspace),
            "working": str(working.workspace),
        },
        get_user_email=lambda: JEANNE.email,
        get_gitlab_url=lambda: GITLAB_URL,
        get_role=lambda _: None,
        clock=clock,
    )
    original = DesktopGitService.read_unsent_commits
    attempts: List[int] = []

    def read_unsent_commits(self: DesktopGitService, path: str) -> Any:
        if os.path.realpath(path) == os.path.realpath(broken.workspace):
            attempts.append(1)
            raise ValueError("a failure that nobody foresaw")
        return original(self, path)

    monkeypatch.setattr(
        DesktopGitService, "read_unsent_commits", read_unsent_commits
    )

    queue.run_once()

    # The other project was looked at, and the error is a state.
    assert working.get_bare_head() == sha
    assert queue.get_status(str(broken.workspace)).state is SendState.ERROR
    assert len(attempts) == 1
    # The queue does not spin: the next try is after a wait that grows.
    assert queue._get_seconds_until_next_attempt() >= 0.9
    queue.run_once()
    assert len(attempts) == 1
    clock.now += 1.1
    queue.run_once()
    assert len(attempts) == 2
    clock.now += 1.1
    queue.run_once()
    assert len(attempts) == 2
    clock.now += 1.0
    queue.run_once()
    assert len(attempts) == 3


def test_029_the_output_that_is_read_does_not_depend_on_the_language(
    setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LC_ALL", "fr_FR.UTF-8")
    monkeypatch.setenv("LANGUAGE", "fr")
    setup.commit()
    environments: List[Dict[str, str]] = []
    original = subprocess.Popen

    def popen(arguments: List[str], *args: Any, **kwargs: Any) -> Any:
        if arguments[1:2] == ["push"]:
            environments.append(dict(kwargs["env"]))
        return original(arguments, *args, **kwargs)

    monkeypatch.setattr(send_queue_module.subprocess, "Popen", popen)

    setup.queue.run_once()

    assert len(environments) == 1
    assert environments[0]["LC_ALL"] == "C"
    assert environments[0]["LANGUAGE"] == ""


def test_030_the_commits_of_a_user_never_go_with_the_token_of_another(
    setup: Setup,
) -> None:
    before = setup.get_bare_head()
    setup.commit(JEANNE, "mine")

    def get_token() -> str:
        # The session changes between the reading of the commits and the
        # reading of the token: another user signs in.
        setup.user["email"] = OTHER.email
        return "token-of-the-other-user"

    queue = _create_queue(
        setup,
        git_access=GitAccess(
            get_gitlab_url=lambda: GITLAB_URL, get_access_token=get_token
        ),
    )
    environments: List[Dict[str, str]] = []
    original = subprocess.Popen

    def popen(arguments: List[str], *args: Any, **kwargs: Any) -> Any:
        if arguments[1:2] == ["push"]:
            environments.append(dict(kwargs["env"]))
        return original(arguments, *args, **kwargs)

    send_queue_module.subprocess.Popen = popen  # type: ignore[misc]
    try:
        queue.run_once()
    finally:
        send_queue_module.subprocess.Popen = original  # type: ignore[misc]

    assert environments == []
    assert setup.get_bare_head() == before
    assert queue.get_status(str(setup.workspace)).state in (
        SendState.OTHER_USER,
        SendState.SIGNED_OUT,
    )


def test_031_a_folder_that_left_the_settings_is_forgotten_and_the_queue_rests(
    setup: Setup,
) -> None:
    folders: Dict[str, str] = {"project": str(setup.workspace)}
    queue = SendQueue(
        git_access=GitAccess(),
        get_folders=lambda: dict(folders),
        get_user_email=lambda: JEANNE.email,
        get_gitlab_url=lambda: GITLAB_URL,
        get_role=lambda _: None,
    )
    # The state of the folder is known, and its next look is far.
    queue.run_once(is_forced=True)
    assert queue._get_seconds_until_next_attempt() > 30

    # The project is removed from the settings, and a session changes.
    folders.clear()
    queue.wake()
    queue.run_once()

    # What the thread waits at rest: the long wait, not 0.1 second for ever
    # (30 passes in 3 seconds), and the state of the folder is forgotten.
    assert queue._get_seconds_until_next_attempt() > 30
    assert queue._states == {}


def test_032_a_thread_at_rest_makes_almost_no_pass(setup: Setup) -> None:
    folders: Dict[str, str] = {"project": str(setup.workspace)}
    reads: List[int] = []

    def get_folders() -> Dict[str, str]:
        reads.append(1)
        return dict(folders)

    queue = SendQueue(
        git_access=GitAccess(),
        get_folders=get_folders,
        get_user_email=lambda: JEANNE.email,
        get_gitlab_url=lambda: GITLAB_URL,
        get_role=lambda _: None,
    )
    queue.run_once(is_forced=True)
    folders.clear()
    queue.wake()
    reads.clear()
    try:
        queue.start()
        assert _wait_for(lambda: len(reads) >= 1)

        time.sleep(1.5)

        # The thread made its pass at the start and rests (the old code made
        # one every 0.1 second).
        assert len(reads) <= 3
    finally:
        queue.stop()


@pytest.mark.parametrize("setting", ["pushurl", "pushInsteadOf"])
def test_033_a_push_address_of_another_server_stops_the_sending(
    setup: Setup, monkeypatch: pytest.MonkeyPatch, setting: str
) -> None:
    setup.commit()
    head_before = setup.get_bare_head()
    pushes = _count_pushes(setup, monkeypatch)
    repo = Repo(setup.workspace)
    if setting == "pushurl":
        repo.git.config("remote.origin.pushurl", "http://other.example.org/x")
    else:
        # The address to read stays the one of the folder, the address to
        # write is another one.
        repo.git.config(
            "url.http://other.example.org/.pushInsteadOf",
            f"{setup.bare.parent}/",
        )
    repo.close()

    setup.queue.run_once()

    assert setup.get_state() is SendState.OTHER_SERVER
    assert pushes == []
    assert setup.get_bare_head() == head_before


def test_034_every_push_address_must_be_allowed(
    setup: Setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup.commit()
    pushes = _count_pushes(setup, monkeypatch)
    repo = Repo(setup.workspace)
    repo.git.config("--add", "remote.origin.pushurl", str(setup.bare))
    repo.git.config("--add", "remote.origin.pushurl", "ssh://x@elsewhere/y")
    repo.close()

    setup.queue.run_once()

    assert setup.get_state() is SendState.OTHER_SERVER
    assert pushes == []
