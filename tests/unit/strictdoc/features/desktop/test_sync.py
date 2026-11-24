"""
The synchronization of a project of the desktop application: the update, the
merge that is made alone, the merge that waits for the user, the files that
are not documents, the roles, and the timers.

@relation(SDOC-SRS-1245, scope=file)
@relation(SDOC-SRS-1247, scope=file)
@relation(SDOC-SRS-1250, scope=file)
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

import pytest
from git import Actor, GitCommandError, Repo
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from strictdoc.features.desktop import workspace
from strictdoc.features.desktop.git_access import (
    EXCLUDE_BLOCK_BEGIN,
    EXCLUDE_BLOCK_END,
    DesktopGitService,
    GitAccess,
)
from strictdoc.features.desktop.local_server import (
    create_desktop_project_config,
    create_project_application,
)
from strictdoc.features.desktop.permissions import (
    can_abandon,
    can_publish,
    can_resolve,
    can_update,
    get_route_role_overrides,
)
from strictdoc.features.desktop.project_gate import (
    CONFLICT_HEADER,
    ProjectGate,
    ProjectGateMiddleware,
    get_project_gate,
)
from strictdoc.features.desktop.project_runtime import (
    ProjectRuntime,
    get_project_runtime,
)
from strictdoc.features.desktop.project_servers import ProjectServerManager
from strictdoc.features.desktop.project_status import (
    STATUS_PATH,
    ProjectStatus,
    SendState,
    get_project_status,
)
from strictdoc.features.desktop.project_sync import (
    SyncOutcome,
    get_merge_key,
    get_update_blocked_text,
    synchronize_project,
)
from strictdoc.features.desktop.settings import (
    DesktopSettings,
    load_settings,
    save_settings,
)
from strictdoc.features.desktop.workspace import (
    UpdateDeferredError,
    WorkspaceError,
    pull_project,
)
from strictdoc.features.git_config.git_service import Author
from strictdoc.features.i18n import i18n
from strictdoc.features.roles.enforcement import RoleMiddleware
from strictdoc.features.roles.principal import Principal
from strictdoc.features.roles.route_roles import ROUTE_ROLES

SEED = Actor("Seed", "seed@example.org")
COLLEAGUE = Actor("Colleague", "colleague@example.org")
AUTHOR = Author("Jeanne Dupont", "jeanne@example.org")
AUTHOR_ACTOR = Actor("Jeanne Dupont", "jeanne@example.org")
DOCUMENT_MID = "1d6c2b5f8a9e4e1fb7c3a0d4e5f60a11"
DOCUMENT = (
    f"[DOCUMENT]\nMID: {DOCUMENT_MID}\nTITLE: Doc\n"
    "OPTIONS:\n  ENABLE_MID: True\n\n"
    "[REQUIREMENT]\nMID: 2e7d3c6a9b0f4f2ac8d4b1e5f6a70b22\nUID: REQ-1\n"
    "STATEMENT: The system shall brake.\n\n"
    "[REQUIREMENT]\nMID: 3f8e4d7bac104a3bd9e5c2f6a7b81c33\nUID: REQ-2\n"
    "STATEMENT: The system shall steer.\n"
)
FORBIDDEN_WORDS = (
    "git",
    "gitlab",
    "commit",
    "push",
    "pull",
    "branch",
    "merge",
    "rebase",
    "fatal",
    "origin",
    "repository",
    "fetch",
)


@pytest.fixture(name="restore_language", autouse=True)
def fixture_restore_language() -> Any:
    yield
    i18n.set_language(i18n.DEFAULT_LANGUAGE)


def _wait_for(condition: Callable[[], Any], seconds: float = 20.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


class FakeQueue:
    def __init__(self) -> None:
        self.notified: List[str] = []

    def get_status(self, folder: str) -> ProjectStatus:
        del folder
        return ProjectStatus(SendState.IDLE)

    def notify(self, folder: str) -> None:
        self.notified.append(folder)


class Project:
    """A server, a clone that is the project, and the clone of a colleague."""

    def __init__(self, root: Path) -> None:
        work = root / "work"
        work.mkdir()
        (work / "doc.sdoc").write_text(DOCUMENT, encoding="utf-8")
        repo = Repo.init(work, initial_branch="main")
        repo.index.add(["doc.sdoc"])
        repo.index.commit("Seed", author=SEED, committer=SEED)
        repo.close()
        self.bare = root / "remote.git"
        Repo.clone_from(str(work), str(self.bare), bare=True).close()
        self.folder = root / "project"
        Repo.clone_from(str(self.bare), str(self.folder)).close()
        self.root = root
        self.runtime = ProjectRuntime()
        self.gate = ProjectGate()
        self.queue = FakeQueue()
        self.rebuilt: List[str] = []
        self.runtime.rebuild_and_notify = lambda: self.rebuilt.append("rebuilt")
        self.inhibited: List[str] = []
        self.runtime.inhibit_change = self.inhibited.append

    def colleague_sends(self, files: Dict[str, Any]) -> None:
        """The colleague writes these files (text or bytes) and sends them."""
        path = self.root / f"colleague-{time.monotonic_ns()}"
        repo = Repo.clone_from(str(self.bare), str(path))
        for name_, content_ in files.items():
            target = path / name_
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content_, bytes):
                target.write_bytes(content_)
            else:
                target.write_text(content_, encoding="utf-8")
        repo.index.add(list(files))
        repo.index.commit("Change", author=COLLEAGUE, committer=COLLEAGUE)
        repo.git.push("origin", "main")
        repo.close()

    def change_statement(self, old: str, new: str, who: Actor) -> None:
        """The user changes a sentence and commits it here (not sent)."""
        document = self.folder / "doc.sdoc"
        document.write_text(
            document.read_text(encoding="utf-8").replace(old, new),
            encoding="utf-8",
        )
        repo = Repo(self.folder)
        repo.index.add(["doc.sdoc"])
        repo.index.commit("Save", author=who, committer=who)
        repo.close()

    def colleague_changes(self, old: str, new: str) -> None:
        """The colleague changes a sentence of the document and sends it."""
        path = self.root / f"colleague-{time.monotonic_ns()}"
        repo = Repo.clone_from(str(self.bare), str(path))
        document = path / "doc.sdoc"
        document.write_text(
            document.read_text(encoding="utf-8").replace(old, new),
            encoding="utf-8",
        )
        repo.index.add(["doc.sdoc"])
        repo.index.commit("Change", author=COLLEAGUE, committer=COLLEAGUE)
        repo.git.push("origin", "main")
        repo.close()

    def read(self, name: str = "doc.sdoc") -> str:
        return (self.folder / name).read_text(encoding="utf-8")

    def synchronize(
        self,
        role: Optional[str] = None,
        *,
        is_forced: bool = False,
        git_access: Optional[GitAccess] = None,
    ) -> bool:
        return (
            synchronize_project(
                str(self.folder),
                git_access=git_access
                if git_access is not None
                else GitAccess(),
                gate=self.gate,
                runtime=self.runtime,
                author_provider=lambda: AUTHOR,
                role=role,
                send_queue=self.queue,
                is_forced=is_forced,
            )
            is SyncOutcome.UPDATED
        )

    def get_parents(self) -> int:
        repo = Repo(self.folder)
        try:
            return len(repo.head.commit.parents)
        finally:
            repo.close()


@pytest.fixture(name="project")
def fixture_project(tmp_path: Path) -> Project:
    return Project(tmp_path)


# The settings, the permissions, the interval.


def test_001_the_interval_is_five_minutes_and_is_read_without_failing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    assert load_settings(path).sync_interval_minutes == 5
    for stored, expected in (
        (10, 10),
        (1, 1),
        (120, 120),
        (0, 1),
        (-4, 1),
        (500, 120),
        ("ten", 5),
        (2.5, 5),
        (True, 5),
        (None, 5),
    ):
        path.write_text(json.dumps({"sync_interval_minutes": stored}))
        assert load_settings(path).sync_interval_minutes == expected, stored
    save_settings(DesktopSettings(sync_interval_minutes=7), path)
    assert load_settings(path).sync_interval_minutes == 7


def test_002_the_roles_that_update_resolve_abandon_and_publish() -> None:
    for role_ in (None, "reader", "reviewer", "author", "administrator"):
        assert can_update(role_) is True
    assert [
        can_resolve(role_)
        for role_ in (None, "reader", "reviewer", "author", "administrator")
    ] == [True, False, False, True, True]
    assert can_abandon("author") is True
    assert can_abandon("reader") is False
    assert [
        can_publish(role_) for role_ in (None, "author", "administrator")
    ] == [
        True,
        False,
        True,
    ]


def test_003_the_table_of_the_web_server_is_not_changed_by_the_desktop() -> (
    None
):
    overrides = get_route_role_overrides()

    assert overrides[("POST", "/actions/git/sync/resolve")] == "author"
    assert overrides[("POST", "/actions/git/sync")] == "reader"
    # The table of the web server keeps its rules: an administrator only.
    for key_ in overrides:
        assert ROUTE_ROLES[key_] == "administrator"


def _create_role_client(
    role: str, overrides: Optional[Dict[Any, str]]
) -> TestClient:
    def answer(_: Request) -> Response:
        return PlainTextResponse("done")

    application = Starlette(
        routes=[Route("/actions/git/sync/resolve", answer, methods=["POST"])]
    )
    kwargs: Dict[str, Any] = {"auth_mode": "desktop"}
    if overrides is not None:
        kwargs["role_overrides"] = overrides
    wrapped = RoleMiddleware(application, **kwargs)

    async def with_principal(scope: Any, receive: Any, send: Any) -> None:
        scope.setdefault("state", {})["principal"] = Principal(
            user="jdupont", role=role
        )
        await wrapped(scope, receive, send)

    return TestClient(with_principal)


def test_004_an_author_resolves_in_the_application_and_not_on_the_web() -> None:
    web = _create_role_client("author", None)
    application = _create_role_client("author", get_route_role_overrides())
    reader = _create_role_client("reader", get_route_role_overrides())

    assert web.post("/actions/git/sync/resolve").status_code == 403
    assert application.post("/actions/git/sync/resolve").status_code == 200
    assert reader.post("/actions/git/sync/resolve").status_code == 403


# The update.


def test_005_the_update_brings_the_changes_and_tells_the_server(
    project: Project,
) -> None:
    project.colleague_changes("shall steer", "shall steer left")

    assert project.synchronize() is True

    assert "steer left" in project.read()
    assert project.rebuilt == ["rebuilt"]
    assert [Path(path_).name for path_ in project.inhibited] == ["doc.sdoc"]
    # A fast-forward makes no commit: nothing to send.
    assert project.queue.notified == []
    assert project.get_parents() == 1


def test_006_nothing_to_bring_changes_nothing(project: Project) -> None:
    assert project.synchronize() is False
    assert project.rebuilt == []


def test_007_a_page_that_types_defers_the_update(project: Project) -> None:
    project.colleague_changes("shall steer", "shall steer left")
    project.runtime.leases.renew("page-1")

    with pytest.raises(UpdateDeferredError):
        project.synchronize()

    assert "steer left" not in project.read()
    project.runtime.leases.close()


def test_008_nothing_is_fetched_while_a_merge_waits(project: Project) -> None:
    project.change_statement("shall brake", "shall brake hard", COLLEAGUE)
    project.colleague_changes("shall brake", "shall brake softly")
    assert project.synchronize() is True
    assert (
        get_merge_key(
            DesktopGitService(str(project.folder), GitAccess()),
            str(project.folder),
        )
        != ""
    )
    # The server is gone: a synchronization that fetched would fail.
    Repo(project.folder).git.remote("set-url", "origin", "/nowhere/at/all")
    heads = project.rebuilt[:]

    assert project.synchronize() is False
    assert project.synchronize(is_forced=True) is False

    assert project.rebuilt == heads


def test_009_offline_the_update_fails_and_the_files_stay(
    project: Project,
) -> None:
    before = project.read()
    Repo(project.folder).git.remote("set-url", "origin", "/nowhere/at/all")

    with pytest.raises(WorkspaceError):
        project.synchronize()

    assert project.read() == before
    assert project.rebuilt == []


# The merge that is made alone.


def test_010_other_nodes_are_merged_without_a_question_and_sent(
    project: Project,
) -> None:
    project.change_statement("shall brake", "shall brake hard", AUTHOR_ACTOR)
    project.colleague_changes("shall steer", "shall steer left")

    assert project.synchronize("author") is True

    text = project.read()
    assert "brake hard" in text and "steer left" in text
    assert project.get_parents() == 2
    repo = Repo(project.folder)
    assert repo.head.commit.author.email == "jeanne@example.org"
    repo.close()
    assert (
        get_merge_key(
            DesktopGitService(str(project.folder), GitAccess()),
            str(project.folder),
        )
        == ""
    )
    # The queue sends the merge, as it sends every commit.
    assert project.queue.notified == [str(project.folder)]
    assert project.rebuilt == ["rebuilt"]


def test_011_a_reader_who_commented_receives_the_update_by_a_merge(
    project: Project,
) -> None:
    # The comment of a reader is a commit that is never sent: the update of
    # that reader is a merge, which keeps it.
    project.change_statement("shall brake", "shall brake hard", AUTHOR_ACTOR)
    project.colleague_changes("shall steer", "shall steer left")

    assert project.synchronize("reader") is True

    text = project.read()
    assert "brake hard" in text and "steer left" in text
    assert project.queue.notified == []


# The merge that waits.


def test_012_the_same_node_leaves_the_merge_waiting_with_the_local_text(
    project: Project,
) -> None:
    project.change_statement("shall brake", "shall brake hard", AUTHOR_ACTOR)
    project.colleague_changes("shall brake", "shall brake softly")

    assert project.synchronize("author") is True

    service = DesktopGitService(str(project.folder), GitAccess())
    key = get_merge_key(service, str(project.folder))
    assert key != ""
    assert service.unmerged_paths(str(project.folder)) == ["doc.sdoc"]
    # The server of the project reads the local text until the user chooses.
    assert "brake hard" in project.read() and "<<<<" not in project.read()
    assert project.queue.notified == []
    assert project.rebuilt == ["rebuilt"]


def test_013_a_reader_never_gets_a_window_and_loses_nothing(
    project: Project,
) -> None:
    project.change_statement("shall brake", "shall brake hard", AUTHOR_ACTOR)
    project.colleague_changes("shall brake", "shall brake softly")
    head = Repo(project.folder).head.commit.hexsha

    assert project.synchronize("reader") is False

    service = DesktopGitService(str(project.folder), GitAccess())
    assert get_merge_key(service, str(project.folder)) == ""
    assert "brake hard" in project.read()
    assert Repo(project.folder).head.commit.hexsha == head
    assert project.runtime.sync_notice_state == "update_blocked"
    # The same two sides give the same answer, with no new attempt.
    assert project.synchronize("reader") is False
    assert project.rebuilt == []
    # Until the user asks.
    assert project.synchronize("reader", is_forced=True) is False


def test_014_a_file_that_is_not_a_document_keeps_both_versions(
    project: Project,
) -> None:
    (project.folder / "picture.png").write_bytes(b"\x89PNG mine")
    repo = Repo(project.folder)
    repo.index.add(["picture.png"])
    repo.index.commit("Mine", author=AUTHOR_ACTOR, committer=AUTHOR_ACTOR)
    repo.close()
    project.colleague_sends({"picture.png": b"\x89PNG theirs"})
    project.colleague_changes("shall steer", "shall steer left")

    assert project.synchronize("author") is True

    # Nothing waits, nothing is lost: the two pictures and the new text.
    assert (project.folder / "picture.png").read_bytes() == b"\x89PNG mine"
    copy = project.folder / "picture (colleague).png"
    assert copy.read_bytes() == b"\x89PNG theirs"
    assert "steer left" in project.read()
    service = DesktopGitService(str(project.folder), GitAccess())
    assert get_merge_key(service, str(project.folder)) == ""
    assert project.runtime.sync_notice_state == "files_kept"
    text = project.runtime.sync_notice_text
    assert "picture.png" in text and "picture (colleague).png" in text
    assert "on this computer only" in text
    assert project.queue.notified == [str(project.folder)]


def test_015_a_file_that_a_colleague_changed_and_the_user_removed_stays(
    project: Project,
) -> None:
    (project.folder / "notes.txt").write_text("one\n")
    repo = Repo(project.folder)
    repo.index.add(["notes.txt"])
    repo.index.commit("Notes", author=AUTHOR_ACTOR, committer=AUTHOR_ACTOR)
    repo.git.push("origin", "main")
    repo.git.rm("notes.txt")
    repo.index.commit("Remove", author=AUTHOR_ACTOR, committer=AUTHOR_ACTOR)
    repo.close()
    project.colleague_sends({"notes.txt": "two\n"})

    assert project.synchronize("author") is True

    assert (project.folder / "notes.txt").read_text() == "two\n"
    assert "removed by you" in project.runtime.sync_notice_text


# The routes of the application.


def _create_application(project: Project, role: str = "author") -> Starlette:
    config = create_desktop_project_config(
        input_path=str(project.folder),
        port=None,
        principal_provider=lambda: Principal(user="jdupont", role=role),
    )
    return create_project_application(
        config,
        lambda: AUTHOR,
        GitAccess(),
        project.queue,  # type: ignore[arg-type]
    )


def _make_conflict(project: Project) -> None:
    project.change_statement("shall brake", "shall brake hard", AUTHOR_ACTOR)
    project.colleague_changes("shall brake", "shall brake softly")
    assert project.synchronize("author") is True


def _get_conflict_regions(client: TestClient) -> str:
    return str(client.get("/actions/git/sync_conflicts").text)


def test_016_an_author_resolves_and_the_queue_sends_the_merge(
    tmp_path: Path,
) -> None:
    project = Project(tmp_path)
    application = _create_application(project)
    client = TestClient(application)
    runtime = get_project_runtime(str(project.folder))
    _make_conflict_with_runtime(project, runtime)
    page = _get_conflict_regions(client)
    assert 'data-wording="application"' in page
    assert "origin/" not in page
    choices = _read_choices(page)
    assert len(choices) == 1

    answer = client.post(
        "/actions/git/sync/resolve",
        data={
            "file": "doc.sdoc",
            "texts": json.dumps(
                {
                    region_: texts_["server"]
                    for region_, texts_ in choices.items()
                }
            ),
        },
    )

    assert answer.status_code == 200, answer.text
    assert answer.json()["ok"] is True
    assert "brake softly" in project.read()
    assert project.get_parents() == 2
    assert project.queue.notified == [str(project.folder)]
    service = DesktopGitService(str(project.folder), GitAccess())
    assert get_merge_key(service, str(project.folder)) == ""
    runtime.leases.close()


def _make_conflict_with_runtime(project: Project, runtime: Any) -> None:
    project.change_statement("shall brake", "shall brake hard", AUTHOR_ACTOR)
    project.colleague_changes("shall brake", "shall brake softly")
    assert (
        synchronize_project(
            str(project.folder),
            git_access=GitAccess(),
            gate=get_project_gate(str(project.folder)),
            runtime=runtime,
            author_provider=lambda: AUTHOR,
            role="author",
            send_queue=project.queue,
        )
        is SyncOutcome.UPDATED
    )


def _read_choices(page: str) -> Dict[str, Dict[str, str]]:
    """The texts that each conflict of the window offers, by region."""
    match = re.search(
        r'<script type="application/json" id="gs-data">(.*?)</script>',
        page,
        re.DOTALL,
    )
    assert match is not None
    choices: Dict[str, Dict[str, str]] = json.loads(match.group(1))
    return choices


def test_017_a_reader_cannot_resolve_or_abandon(tmp_path: Path) -> None:
    project = Project(tmp_path)
    client = TestClient(_create_application(project, role="reader"))

    for path_ in ("/actions/git/sync/resolve", "/actions/git/sync/abort"):
        assert client.post(path_).status_code == 403


def test_018_abandoning_goes_back_and_holds_the_update_until_asked(
    tmp_path: Path,
) -> None:
    project = Project(tmp_path)
    application = _create_application(project)
    client = TestClient(application)
    runtime = get_project_runtime(str(project.folder))
    _make_conflict_with_runtime(project, runtime)

    answer = client.post("/actions/git/sync/abort")

    assert answer.status_code == 200
    service = DesktopGitService(str(project.folder), GitAccess())
    assert get_merge_key(service, str(project.folder)) == ""
    assert "brake hard" in project.read()
    # The same two sides: no new merge until the user asks for the update.
    assert (
        synchronize_project(
            str(project.folder),
            git_access=GitAccess(),
            gate=get_project_gate(str(project.folder)),
            runtime=runtime,
            author_provider=lambda: AUTHOR,
            role="author",
            send_queue=project.queue,
        )
        is SyncOutcome.UP_TO_DATE
    )
    update = client.post("/actions/git/sync")
    assert update.status_code == 200
    assert update.json()["state"] == "merge_waiting"
    runtime.leases.close()


def test_019_the_status_says_that_a_merge_waits_and_how_to_find_it(
    tmp_path: Path,
) -> None:
    project = Project(tmp_path)
    client = TestClient(_create_application(project))
    runtime = get_project_runtime(str(project.folder))
    _make_conflict_with_runtime(project, runtime)

    answer = client.get(STATUS_PATH).json()

    assert answer["state"] == "merge_waiting"
    assert answer["detail"] != ""
    assert answer["detail"] == get_merge_key(
        DesktopGitService(str(project.folder), GitAccess()),
        str(project.folder),
    )
    for word_ in FORBIDDEN_WORDS:
        assert word_ not in answer["message"].lower().split(), word_
    runtime.leases.close()


def test_020_a_write_waits_for_the_merge_and_the_routes_of_the_merge_pass(
    tmp_path: Path,
) -> None:
    project = Project(tmp_path)
    client = TestClient(_create_application(project))
    runtime = get_project_runtime(str(project.folder))
    _make_conflict_with_runtime(project, runtime)

    refused = client.post(
        "/actions/document/save_config",
        data={"document_mid": DOCUMENT_MID, "document[TITLE]": "Doc"},
    )

    assert refused.status_code == 409
    assert refused.headers[CONFLICT_HEADER] == "1"
    message = refused.json()["message"]
    assert "Choose which version to keep" in message
    lowered = message.lower()
    assert "423" not in lowered and "/git" not in lowered
    # The merge routes are not refused (here: 422, nothing chosen).
    assert (
        client.post(
            "/actions/git/sync/resolve", data={"file": "doc.sdoc"}
        ).status_code
        == 422
    )
    runtime.leases.close()


def _create_gate_client(
    runtime: ProjectRuntime, calls: List[str], is_merge_waiting: Any = None
) -> TestClient:
    def answer(request: Request) -> Response:
        calls.append(request.url.path)
        return PlainTextResponse("done")

    return TestClient(
        ProjectGateMiddleware(
            Starlette(
                routes=[
                    Route("/save", answer, methods=["POST"]),
                    Route(
                        "/actions/git/sync/resolve", answer, methods=["POST"]
                    ),
                    Route("/actions/git/sync/abort", answer, methods=["POST"]),
                    Route("/actions/git/tag", answer, methods=["POST"]),
                ]
            ),
            gate=ProjectGate(),
            get_committer=lambda: None,
            runtime=runtime,
            is_merge_waiting=is_merge_waiting,
        )
    )


def test_021_an_index_that_is_late_does_not_stop_the_merge_routes() -> None:
    runtime = ProjectRuntime()
    runtime.mark_files_changed()
    assert runtime.is_index_outdated is True
    calls: List[str] = []
    client = _create_gate_client(runtime, calls)

    saved = client.post("/save")
    resolved = client.post("/actions/git/sync/resolve")
    abandoned = client.post("/actions/git/sync/abort")

    assert saved.status_code == 409
    assert resolved.status_code == 200 and abandoned.status_code == 200
    assert calls == ["/actions/git/sync/resolve", "/actions/git/sync/abort"]


def test_022_a_merge_that_waits_refuses_the_writes_but_not_the_git_ones() -> (
    None
):
    runtime = ProjectRuntime()
    calls: List[str] = []
    client = _create_gate_client(runtime, calls, lambda: True)

    assert client.post("/save").status_code == 409
    assert client.post("/actions/git/tag").status_code == 200
    assert client.post("/actions/git/sync/resolve").status_code == 200
    assert calls == ["/actions/git/tag", "/actions/git/sync/resolve"]


def test_023_the_merge_message_is_in_the_language_of_the_user() -> None:
    i18n.set_language("fr")
    runtime = ProjectRuntime()
    client = _create_gate_client(runtime, [], lambda: True)

    message = client.post("/save").json()["message"]

    assert "Choisissez la version à garder" in message
    assert "merge" not in message.lower() and "git" not in message.lower()


def test_024_the_update_on_request_takes_no_gate_and_says_what_happened(
    tmp_path: Path,
) -> None:
    project = Project(tmp_path)
    client = TestClient(_create_application(project, role="reader"))
    runtime = get_project_runtime(str(project.folder))
    project.colleague_changes("shall steer", "shall steer left")

    # A reader updates; the gate is taken by somebody else meanwhile: the
    # update of the network does not wait for it.
    answer = client.post("/actions/git/sync")

    assert answer.status_code == 200
    assert answer.json()["state"] == "updated"
    assert "steer left" in project.read()
    again = client.post("/actions/git/sync")
    assert again.json()["state"] == "up_to_date"
    runtime.leases.close()


def test_025_the_update_on_request_defers_while_the_user_types(
    tmp_path: Path,
) -> None:
    project = Project(tmp_path)
    client = TestClient(_create_application(project))
    runtime = get_project_runtime(str(project.folder))
    project.colleague_changes("shall steer", "shall steer left")
    runtime.leases.renew("page-1")

    answer = client.post("/actions/git/sync")

    assert answer.json()["state"] == "deferred"
    assert "steer left" not in project.read()
    runtime.leases.close()


def test_026_a_failed_update_has_a_message_without_the_words_of_the_tool(
    tmp_path: Path,
) -> None:
    project = Project(tmp_path)
    client = TestClient(_create_application(project))
    runtime = get_project_runtime(str(project.folder))
    Repo(project.folder).git.remote("set-url", "origin", "/nowhere/at/all")

    answer = client.post("/actions/git/sync")

    assert answer.status_code == 502
    message = answer.json()["message"].lower()
    for word_ in FORBIDDEN_WORDS:
        assert word_ not in message.split(), word_
    assert "nowhere" not in message
    runtime.leases.close()


# The status, the texts.


def test_027_the_order_of_what_the_user_is_told() -> None:
    waiting = ProjectStatus(SendState.WAITING_NETWORK, 2)
    kept = ProjectStatus(SendState.FILES_KEPT, message="x")
    blocked = ProjectStatus(SendState.UPDATE_BLOCKED, message="y")

    assert get_project_status("", waiting, merge_key="abc").state is (
        SendState.MERGE_WAITING
    )
    assert get_project_status("x", waiting, merge_key="abc").state is (
        SendState.NOT_SAVED
    )
    assert get_project_status("", waiting, notice=kept) == waiting
    assert get_project_status("", None, notice=kept) == kept
    assert get_project_status("", waiting, notice=blocked) == blocked


# The timers.


def _create_manager(
    tmp_path: Path, updates: List[str], interval: Optional[float] = 0.05
) -> ProjectServerManager:
    class FakeServer:
        start_url = "http://127.0.0.1:1/start"
        direct_url = "http://127.0.0.1:1/"
        is_bootstrapped = True

        def set_bootstrap_listener(self, listener: Any) -> None:
            pass

        def start(self) -> None:
            pass

        def wait_until_ready(self) -> None:
            pass

        def stop(self) -> None:
            pass

    return ProjectServerManager(
        server_factory=lambda *_: FakeServer(),
        updater=lambda folder_: updates.append(folder_) is None and False,
        settings_path=tmp_path / "settings.json",
        eviction_delay_seconds=0,
        sync_interval_seconds=interval,
    )


def test_028_an_open_project_is_synchronized_again_after_the_interval(
    tmp_path: Path,
) -> None:
    updates: List[str] = []
    manager = _create_manager(tmp_path, updates)

    manager.open("a", "/projects/a")

    assert _wait_for(lambda: len(updates) >= 3)
    manager.stop_all()


def test_029_the_timer_ends_with_the_project_the_pause_and_the_closing(
    tmp_path: Path,
) -> None:
    updates: List[str] = []
    manager = _create_manager(tmp_path, updates)
    manager.open("a", "/projects/a")
    manager.open("b", "/projects/b")
    assert _wait_for(lambda: len(updates) >= 4)

    manager.stop_project("a")
    time.sleep(0.2)
    count_a = updates.count("/projects/a")
    time.sleep(0.3)
    assert updates.count("/projects/a") == count_a
    assert _wait_for(lambda: updates.count("/projects/b") > 0)

    manager.pause_timers()
    time.sleep(0.2)
    paused = len(updates)
    time.sleep(0.3)
    assert len(updates) == paused
    assert manager._sync_timers == {}  # noqa: SLF001

    manager.resume_timers()
    assert _wait_for(lambda: len(updates) > paused)

    manager.stop_all()
    time.sleep(0.2)
    stopped = len(updates)
    time.sleep(0.3)
    assert len(updates) == stopped
    assert manager._sync_timers == {}  # noqa: SLF001


def test_030_the_interval_is_the_setting_of_the_user_in_minutes(
    tmp_path: Path,
) -> None:
    save_settings(
        DesktopSettings(sync_interval_minutes=12), tmp_path / "settings.json"
    )
    manager = _create_manager(tmp_path, [], interval=None)

    assert manager._get_interval_seconds() == 720.0  # noqa: SLF001
    default = _create_manager(tmp_path / "other", [], interval=None)
    assert default._get_interval_seconds() == 300.0  # noqa: SLF001


def test_031_a_merge_that_waits_stops_the_next_synchronizations(
    project: Project,
) -> None:
    project.change_statement("shall brake", "shall brake hard", AUTHOR_ACTOR)
    project.colleague_changes("shall brake", "shall brake softly")
    assert project.synchronize("author") is True
    project.colleague_changes("shall steer", "shall steer left")

    assert project.synchronize("author") is False
    assert "steer left" not in project.read()


# The words of the windows.

BANNED_WORDS = re.compile(
    r"\b(git|gitlab|commit|commits|committed|push|pushed|pull|pulled|branch|"
    r"merge|merged|rebase|fatal|remote|origin|repository|fetch)\b",
    re.IGNORECASE,
)


def _get_visible_text(page: str) -> str:
    """What the user reads of a Turbo stream: no script, no tag."""
    without_scripts = re.sub(r"<script.*?</script>", " ", page, flags=re.DOTALL)
    return re.sub(r"<[^>]+>", " ", without_scripts)


def _get_environment_globals(application: Starlette) -> Dict[str, Any]:
    context = application.state.project_context
    environment = context.html_templates.jinja_environment().environment
    return environment.globals  # type: ignore[no-any-return]


def _render_waiting_dialog(application: Starlette) -> str:
    """The shared window of a merge that waits, as the web server shows it."""
    context = application.state.project_context
    return str(
        context.env().render_template_as_markup(
            "features/git_sync/stream_sync.jinja.html",
            message="",
            result=None,
            waiting=True,
            conflicts=["doc.sdoc"],
            has_remote=True,
            can_sync=True,
        )
    )


def test_032_the_windows_of_the_merge_have_no_word_of_git_in_the_application(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = Project(tmp_path)
    application = _create_application(project)
    client = TestClient(application)
    runtime = get_project_runtime(str(project.folder))
    _make_conflict_with_runtime(project, runtime)

    conflicts = _get_conflict_regions(client)
    waiting = _render_waiting_dialog(application)
    finished = client.get("/actions/git/sync_dialog?merged=1&pushed=0").text

    for page_ in (conflicts, waiting, finished):
        words = BANNED_WORDS.findall(_get_visible_text(page_))
        assert words == [], words
    visible = _get_visible_text(conflicts)
    assert "Keep my version" in visible and "Later" in visible
    assert "Keep my colleague's version" in visible
    assert 'data-requires-role="author"' in conflicts
    assert 'data-requires-role="author"' in waiting
    assert "are combined" in finished

    # The web server keeps its words and its role, to the character.
    for name_ in (
        "desktop_application",
        "desktop_resolve_role",
        "desktop_indicator",
    ):
        monkeypatch.delitem(_get_environment_globals(application), name_)
    web = client.get("/actions/git/sync_conflicts").text
    web_dialog = _render_waiting_dialog(application)
    for phrase_ in (
        "origin/main",
        "Keep the server",
        "Keep the local",
        "Abandon the merge",
        "Finish this document",
        "Conflict: both sides changed this",
        "(the text of the document, as written in the .sdoc file)",
    ):
        assert phrase_ in web, phrase_
    assert "Abandon the merge" in web_dialog
    assert "A merge is waiting for its conflicts to be solved" in web_dialog
    assert 'data-requires-role="administrator"' in web
    assert 'data-requires-role="administrator"' in web_dialog
    assert "data-wording" not in web
    runtime.leases.close()


def test_033_the_windows_are_in_french_without_the_english_words_of_git(
    tmp_path: Path,
) -> None:
    project = Project(tmp_path)
    client = TestClient(_create_application(project))
    runtime = get_project_runtime(str(project.folder))
    _make_conflict_with_runtime(project, runtime)
    i18n.set_language("fr")

    conflicts = _get_conflict_regions(client)

    visible = _get_visible_text(conflicts)
    assert "Garder ma version" in visible
    assert "Plus tard" in visible
    assert BANNED_WORDS.findall(visible) == []
    runtime.leases.close()


# The watcher of the files is told before the files change, never after.


class WatchedProject:
    """A project with its server, and its watcher of the files that runs."""

    def __init__(self, project: Project, role: str = "author") -> None:
        self.project: Project = project
        self.application: Starlette = _create_application(project, role)
        self.runtime: ProjectRuntime = get_project_runtime(str(project.folder))
        self.client: TestClient = TestClient(self.application)
        self.watcher: Any = (
            self.application.state.project_context.document_watcher
        )
        self.watcher._debounce_seconds = 0.05
        self._last_touch: float = time.monotonic()
        touched = self.watcher._on_document_touched

        def on_touched(path: str) -> None:
            self._last_touch = time.monotonic()
            touched(path)

        self.watcher._on_document_touched = on_touched
        self.watcher.start()

    def synchronize(self, role: str = "author") -> SyncOutcome:
        return synchronize_project(
            str(self.project.folder),
            git_access=GitAccess(),
            gate=get_project_gate(str(self.project.folder)),
            runtime=self.runtime,
            author_provider=lambda: AUTHOR,
            role=role,
            send_queue=self.project.queue,
        )

    def wait_until_quiet(self) -> None:
        """
        The events of the update are over. The server builds its index while
        the watcher waits for the processor, so they can come late.
        """
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            is_quiet = time.monotonic() - self._last_touch > 0.5
            if is_quiet and len(self.watcher._pending_paths) == 0:
                return
            time.sleep(0.02)

    def assert_outside_change_is_seen(self, name: str = "doc.sdoc") -> None:
        """What an editor of the user writes next is read by the server."""
        self.wait_until_quiet()
        revision = self.runtime.revision
        document = self.project.folder / name
        text = f"[DOCUMENT]\nTITLE: Outside {time.monotonic_ns()}\n"
        if name == "doc.sdoc":
            text = document.read_text(encoding="utf-8").replace(
                "shall steer", "shall steer outside"
            )
        document.write_text(text, encoding="utf-8")
        assert _wait_for(lambda: self.runtime.revision > revision, 10.0)
        assert self.watcher._inhibited_paths == set()


@pytest.fixture(name="watched")
def fixture_watched(tmp_path: Path) -> Iterator[WatchedProject]:
    watched = WatchedProject(Project(tmp_path))
    yield watched
    watched.watcher.stop()
    watched.runtime.leases.close()


def _slow_down(
    monkeypatch: pytest.MonkeyPatch, name: str, seconds: float = 0.5
) -> None:
    """Git is slow: the files are written, and the call ends much later."""
    original = getattr(DesktopGitService, name)

    def slow(*arguments: Any, **keywords: Any) -> Any:
        result = original(*arguments, **keywords)
        time.sleep(seconds)
        return result

    monkeypatch.setattr(DesktopGitService, name, slow)


def test_034_a_slow_fast_forward_does_not_hide_the_next_outside_change(
    watched: WatchedProject, monkeypatch: pytest.MonkeyPatch
) -> None:
    watched.project.colleague_changes("shall brake", "shall brake softly")
    _slow_down(monkeypatch, "fast_forward")

    assert watched.synchronize() is SyncOutcome.UPDATED

    assert "brake softly" in watched.project.read()
    watched.assert_outside_change_is_seen()


def test_035_a_slow_pull_does_not_hide_the_next_outside_change(
    watched: WatchedProject, monkeypatch: pytest.MonkeyPatch
) -> None:
    watched.project.colleague_changes("shall brake", "shall brake softly")
    original = workspace._list_changed_paths

    def slow(*arguments: Any) -> List[str]:
        paths = original(*arguments)
        time.sleep(0.5)
        return paths

    monkeypatch.setattr(workspace, "_list_changed_paths", slow)

    assert pull_project(
        str(watched.project.folder),
        gate=get_project_gate(str(watched.project.folder)),
        runtime=watched.runtime,
    )

    assert "brake softly" in watched.project.read()
    watched.assert_outside_change_is_seen()


def test_036_a_slow_merge_does_not_hide_the_next_outside_change(
    watched: WatchedProject, monkeypatch: pytest.MonkeyPatch
) -> None:
    watched.project.change_statement(
        "shall brake", "shall brake hard", AUTHOR_ACTOR
    )
    watched.project.colleague_changes("shall steer", "shall steer left")
    _slow_down(monkeypatch, "start_merge")

    assert watched.synchronize() is SyncOutcome.UPDATED

    assert "brake hard" in watched.project.read()
    assert "steer left" in watched.project.read()
    watched.assert_outside_change_is_seen()


def test_037_a_slow_abandon_does_not_hide_the_next_outside_change(
    watched: WatchedProject, monkeypatch: pytest.MonkeyPatch
) -> None:
    watched.project.change_statement(
        "shall brake", "shall brake hard", AUTHOR_ACTOR
    )
    watched.project.colleague_changes("shall brake", "shall brake softly")
    watched.project.colleague_sends({"other.sdoc": "[DOCUMENT]\nTITLE: O\n"})
    assert watched.synchronize() is SyncOutcome.UPDATED
    assert (watched.project.folder / "other.sdoc").exists()
    _slow_down(monkeypatch, "abort_merge")

    answer = watched.client.post("/actions/git/sync/abort")

    assert answer.status_code == 200
    # The file that the merge brought is gone with the merge.
    assert not (watched.project.folder / "other.sdoc").exists()
    watched.assert_outside_change_is_seen("other.sdoc")


def test_038_a_merge_that_does_not_change_a_file_leaves_no_inhibition(
    watched: WatchedProject,
) -> None:
    # The document that only the user changed is in the listing that Git
    # gives before the merge, and the merge does not write it: nobody keeps
    # its inhibition.
    watched.project.change_statement(
        "shall brake", "shall brake hard", AUTHOR_ACTOR
    )
    watched.project.colleague_sends({"other.sdoc": "[DOCUMENT]\nTITLE: O\n"})

    assert watched.synchronize() is SyncOutcome.UPDATED

    watched.wait_until_quiet()
    assert watched.watcher._inhibited_paths == set()
    watched.assert_outside_change_is_seen()


def test_039_the_inhibition_of_a_save_that_waits_is_not_taken_back(
    watched: WatchedProject,
) -> None:
    # A save of the user, whose event the watcher has not looked at yet, is
    # inhibited by the server. The merge does not write that file: the
    # inhibition is the one of the save, and it stays.
    document = str(watched.project.folder / "doc.sdoc")
    watched.project.change_statement(
        "shall brake", "shall brake hard", AUTHOR_ACTOR
    )
    watched.project.colleague_sends({"other.sdoc": "[DOCUMENT]\nTITLE: O\n"})
    watched.wait_until_quiet()
    watched.watcher.inhibit_next_change(document)

    assert watched.synchronize() is SyncOutcome.UPDATED

    assert document in watched.watcher._inhibited_paths


def test_040_a_reader_who_is_blocked_by_his_comments_is_told_so(
    tmp_path: Path,
) -> None:
    project = Project(tmp_path)
    client = TestClient(_create_application(project, role="reader"))
    project.change_statement("shall brake", "shall brake hard", AUTHOR_ACTOR)
    project.colleague_changes("shall brake", "shall brake softly")

    answer = client.post("/actions/git/sync")

    assert answer.status_code == 200
    assert answer.json()["state"] == "update_blocked"
    assert answer.json()["message"] == get_update_blocked_text()
    assert "up to date" not in answer.text
    get_project_runtime(str(project.folder)).leases.close()


# The copy of the colleague stays on this computer.


def _commit_picture_of_user(project: Project, name: str) -> None:
    target = project.folder / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\x89PNG mine")
    repo = Repo(project.folder)
    repo.index.add([name])
    repo.index.commit("Mine", author=AUTHOR_ACTOR, committer=AUTHOR_ACTOR)
    repo.close()


def _get_exclude_lines(project: Project) -> List[str]:
    path = project.folder / ".git" / "info" / "exclude"
    return [
        line_
        for line_ in path.read_text(encoding="utf-8").split("\n")
        if line_ != "" and not line_.startswith("#")
    ]


def _is_excluded(project: Project, relative: str) -> bool:
    repo = Repo(project.folder)
    try:
        # check-ignore answers 0 for an ignored path and 1 for the others.
        repo.git.check_ignore("-q", "--", relative)
    except GitCommandError:
        return False
    finally:
        repo.close()
    return True


def test_041_the_copy_of_the_colleague_is_in_no_commit_and_not_in_status(
    project: Project,
) -> None:
    """
    @relation(SDOC-SRS-1247, scope=function)
    """
    _commit_picture_of_user(project, "picture.png")
    project.colleague_sends({"picture.png": b"\x89PNG theirs"})

    assert project.synchronize("author") is True

    copy = project.folder / "picture (colleague).png"
    assert copy.read_bytes() == b"\x89PNG theirs"
    repo = Repo(project.folder)
    try:
        committed = str(repo.git.ls_tree("-r", "--name-only", "HEAD"))
        status = str(repo.git.status("--porcelain=v1", "--untracked-files=all"))
        indexed = str(repo.git.ls_files())
    finally:
        repo.close()
    assert "picture.png" in committed.split("\n")
    assert "picture (colleague).png" not in committed
    assert "picture (colleague).png" not in indexed
    assert status == ""
    assert _get_exclude_lines(project) == ["/picture (colleague).png"]
    # Nothing of the copy is among the files that wait to be sent.
    service = DesktopGitService(str(project.folder), GitAccess())
    assert str(copy) not in service.list_changed_paths(str(project.folder))


def test_042_two_copies_of_the_same_file_write_one_line_each(
    project: Project,
) -> None:
    """
    @relation(SDOC-SRS-1247, scope=function)
    """
    _commit_picture_of_user(project, "picture.png")
    project.colleague_sends({"picture.png": b"\x89PNG theirs"})
    assert project.synchronize("author") is True
    project.colleague_sends({"picture.png": b"\x89PNG theirs again"})
    assert project.synchronize("author") is True

    assert (project.folder / "picture (colleague).png").read_bytes() == (
        b"\x89PNG theirs"
    )
    assert (project.folder / "picture (colleague 2).png").read_bytes() == (
        b"\x89PNG theirs again"
    )
    assert _get_exclude_lines(project) == [
        "/picture (colleague).png",
        "/picture (colleague 2).png",
    ]
    repo = Repo(project.folder)
    try:
        status = str(repo.git.status("--porcelain=v1", "--untracked-files=all"))
    finally:
        repo.close()
    assert status == ""


def test_043_a_line_that_exists_is_not_written_again(project: Project) -> None:
    """
    @relation(SDOC-SRS-1247, scope=function)
    """
    service = DesktopGitService(str(project.folder), GitAccess())
    repo = Repo(project.folder)
    try:
        # A file that has no end of line, as an editor can leave it.
        exclude = project.folder / ".git" / "info" / "exclude"
        exclude.write_text("/other", encoding="utf-8")
        service._exclude_path(repo, str(project.folder), "a (colleague).png")
        service._exclude_path(repo, str(project.folder), "a (colleague).png")
    finally:
        repo.close()

    assert _get_exclude_lines(project) == ["/other", "/a (colleague).png"]


@pytest.mark.parametrize(
    ("name", "other"),
    [
        ("pic[1].png", "pic1 (colleague).png"),
        ("pic*.png", "picture (colleague).png"),
        ("pic?.png", "picx (colleague).png"),
        ("#pic.png", "pic (colleague).png"),
        ("!pic.png", "pic (colleague).png"),
        ("pic.png ", "pic (colleague).png"),
        ("pic one.png", "pic (colleague).png"),
        ("sub folder/pic.png", "pic (colleague).png"),
    ],
)
def test_044_a_name_with_special_characters_is_excluded_as_it_is(
    project: Project, name: str, other: str
) -> None:
    """
    @relation(SDOC-SRS-1247, scope=function)
    """
    _commit_picture_of_user(project, name)
    project.colleague_sends({name: b"\x89PNG theirs"})

    assert project.synchronize("author") is True

    directory, file_name = os.path.split(name)
    stem, extension = os.path.splitext(file_name)
    copy = os.path.join(directory, f"{stem} (colleague){extension}")
    assert (project.folder / copy).read_bytes() == b"\x89PNG theirs"
    assert _is_excluded(project, copy) is True
    # The pattern matches this file and no other: not the file of the user,
    # and not a name that the special characters would match.
    assert _is_excluded(project, name) is False
    assert _is_excluded(project, other) is False
    repo = Repo(project.folder)
    try:
        status = str(repo.git.status("--porcelain=v1", "--untracked-files=all"))
    finally:
        repo.close()
    assert status == ""


def test_045_a_backslash_in_the_name_is_escaped(project: Project) -> None:
    """
    @relation(SDOC-SRS-1247, scope=function)
    """
    service = DesktopGitService(str(project.folder), GitAccess())
    repo = Repo(project.folder)
    try:
        service._exclude_path(repo, str(project.folder), "a\\b (colleague).png")
    finally:
        repo.close()

    assert _get_exclude_lines(project) == ["/a\\\\b (colleague).png"]
    assert _is_excluded(project, "a\\b (colleague).png") is True
    assert _is_excluded(project, "ab (colleague).png") is False


# The lines of the application in ".git/info/exclude" follow their copies.


def _get_status(project: Project) -> str:
    repo = Repo(project.folder)
    try:
        return str(repo.git.status("--porcelain=v1", "--untracked-files=all"))
    finally:
        repo.close()


def _keep_a_copy(project: Project) -> Path:
    _commit_picture_of_user(project, "picture.png")
    project.colleague_sends({"picture.png": b"\x89PNG theirs"})
    assert project.synchronize("author") is True
    copy = project.folder / "picture (colleague).png"
    assert copy.exists()
    return copy


def test_046_the_lines_of_the_application_are_in_a_block_of_their_own(
    project: Project,
) -> None:
    """
    @relation(SDOC-SRS-1247, scope=function)
    """
    exclude = project.folder / ".git" / "info" / "exclude"
    exclude.write_text(exclude.read_text() + "/mine.log\n", encoding="utf-8")

    _keep_a_copy(project)

    lines = exclude.read_text(encoding="utf-8").split("\n")
    begin = lines.index(EXCLUDE_BLOCK_BEGIN)
    end = lines.index(EXCLUDE_BLOCK_END)
    assert lines[begin + 1 : end] == ["/picture (colleague).png"]
    # What the user wrote stays where it is, outside of the block.
    assert "/mine.log" in lines[:begin]
    assert "/mine.log" not in lines[begin:end]


def test_047_a_copy_that_is_removed_is_forgotten_at_the_next_update(
    project: Project,
) -> None:
    """
    @relation(SDOC-SRS-1247, scope=function)
    """
    copy = _keep_a_copy(project)
    # While the copy is there, its line stays through an update.
    assert project.synchronize("author") is False
    assert _get_exclude_lines(project) == ["/picture (colleague).png"]

    copy.unlink()
    project.synchronize("author")

    assert _get_exclude_lines(project) == []
    # A file saved at this path afterwards is an ordinary file: it is shared.
    copy.write_bytes(b"a new file")
    assert _get_status(project) == '?? "picture (colleague).png"'
    service = DesktopGitService(str(project.folder), GitAccess())
    assert str(copy) in service.list_changed_paths(str(project.folder))
    # The lines that are not the application's are not touched.
    exclude = project.folder / ".git" / "info" / "exclude"
    assert EXCLUDE_BLOCK_BEGIN not in exclude.read_text(encoding="utf-8")


def test_048_a_copy_that_is_renamed_is_shared(project: Project) -> None:
    """
    @relation(SDOC-SRS-1247, scope=function)
    """
    copy = _keep_a_copy(project)
    assert _get_status(project) == ""

    copy.rename(project.folder / "picture of the colleague.png")

    # The new name was never hidden, and the old line goes at the next update.
    assert _get_status(project) == '?? "picture of the colleague.png"'
    project.synchronize("author")
    assert _get_exclude_lines(project) == []


def test_049_only_the_lines_of_missing_files_are_forgotten(
    project: Project,
) -> None:
    """
    @relation(SDOC-SRS-1247, scope=function)
    """
    first = _keep_a_copy(project)
    project.colleague_sends({"picture.png": b"\x89PNG theirs again"})
    assert project.synchronize("author") is True
    second = project.folder / "picture (colleague 2).png"
    assert second.exists()
    exclude = project.folder / ".git" / "info" / "exclude"
    # A line that is not a path of this application stays.
    text = exclude.read_text(encoding="utf-8").replace(
        EXCLUDE_BLOCK_END, "/odd?name.png\n" + EXCLUDE_BLOCK_END
    )
    exclude.write_text(text, encoding="utf-8")

    first.unlink()
    project.synchronize("author")

    assert _get_exclude_lines(project) == [
        "/picture (colleague 2).png",
        "/odd?name.png",
    ]
    second.unlink()
    project.synchronize("author")
    assert _get_exclude_lines(project) == ["/odd?name.png"]


def test_050_the_notice_says_how_to_share_the_copy(project: Project) -> None:
    """
    @relation(SDOC-SRS-1247, scope=function)
    """
    _keep_a_copy(project)

    text = project.runtime.sync_notice_text

    assert "on this computer only" in text
    assert "rename the file" in text
