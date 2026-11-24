"""
The files of the working copy do not change under the typing: the update
waits, applies at the end of the typing with the index built again before
another save, and a form that was opened on older files is not saved.

@relation(SDOC-SRS-1246, scope=file)
"""

import json
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest
from git import Actor, Repo
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from strictdoc.features.desktop.git_access import GitAccess
from strictdoc.features.desktop.local_server import (
    create_desktop_project_config,
    create_project_application,
)
from strictdoc.features.desktop.project_gate import (
    CONFLICT_HEADER,
    REVISION_HEADER,
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
    EDITING_PATH,
    STATUS_PATH,
    ProjectStatus,
    ProjectStatusMiddleware,
    SendState,
)
from strictdoc.features.desktop.workspace import (
    UpdateDeferredError,
    WorkspaceError,
    pull_project,
)
from strictdoc.features.git_config.git_service import Author
from strictdoc.features.i18n import i18n
from strictdoc.features.roles.principal import Principal
from strictdoc.helpers.exception import StrictDocException
from strictdoc.server import project_context

SEED = Actor("Seed", "seed@example.org")
COLLEAGUE = Actor("Colleague", "colleague@example.org")
AUTHOR = Author("Jeanne Dupont", "jeanne@example.org")
DOCUMENT = (
    "[DOCUMENT]\nMID: 1d6c2b5f8a9e4e1fb7c3a0d4e5f60a11\nTITLE: Doc\n"
    "OPTIONS:\n  ENABLE_MID: True\n\n"
    "[REQUIREMENT]\nMID: 2e7d3c6a9b0f4f2ac8d4b1e5f6a70b22\nUID: REQ-1\n"
    "STATEMENT: The system shall brake.\n\n"
    "[REQUIREMENT]\nMID: 3f8e4d7bac104a3bd9e5c2f6a7b81c33\nUID: REQ-2\n"
    "STATEMENT: The system shall steer.\n"
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
        time.sleep(0.05)
    return False


class Colleague:
    """A server, a clone that is the project, and a clone of the colleague."""

    def __init__(self, root: Path) -> None:
        work = root / "work"
        work.mkdir()
        (work / "doc.sdoc").write_text(DOCUMENT)
        repo = Repo.init(work, initial_branch="main")
        repo.index.add(["doc.sdoc"])
        repo.index.commit("Seed", author=SEED, committer=SEED)
        repo.close()
        self.bare = root / "remote.git"
        Repo.clone_from(str(work), str(self.bare), bare=True).close()
        self.folder = root / "project"
        Repo.clone_from(str(self.bare), str(self.folder)).close()
        self._root = root

    def change(self, old: str, new: str) -> None:
        """The colleague changes a sentence and sends it."""
        document = (self._clone() / "doc.sdoc").read_text()
        self.send({"doc.sdoc": document.replace(old, new)})

    def send(self, files: Dict[str, str]) -> None:
        """The colleague writes these files, commits and sends them."""
        path = self._root / f"colleague-{time.monotonic_ns()}"
        repo = Repo.clone_from(str(self.bare), str(path))
        for name_, text_ in files.items():
            (path / name_).write_text(text_, encoding="utf-8")
        repo.index.add(list(files))
        repo.index.commit("Change", author=COLLEAGUE, committer=COLLEAGUE)
        repo.git.push("origin", "main")
        repo.close()

    def _clone(self) -> Path:
        path = self._root / f"colleague-{time.monotonic_ns()}"
        Repo.clone_from(str(self.bare), str(path)).close()
        return path

    def read(self) -> str:
        return (self.folder / "doc.sdoc").read_text()


@pytest.fixture(name="colleague")
def fixture_colleague(tmp_path: Path) -> Colleague:
    return Colleague(tmp_path)


def test_001_an_update_waits_while_a_page_has_an_editor_open(
    colleague: Colleague,
) -> None:
    runtime = ProjectRuntime()
    gate = ProjectGate()
    colleague.change("shall steer", "shall steer left")
    runtime.leases.renew("page-1")

    with pytest.raises(UpdateDeferredError):
        pull_project(str(colleague.folder), gate=gate, runtime=runtime)

    # The files are as they were, the revision too: nothing was told.
    assert "steer left" not in colleague.read()
    assert runtime.revision == 0
    # The fetch was made: the update is ready to apply.
    repo = Repo(colleague.folder)
    assert "steer left" in repo.git.show("origin/main:doc.sdoc")
    repo.close()
    assert gate.try_acquire() is True
    gate.release()


def test_002_nothing_waits_when_there_is_nothing_to_bring(
    colleague: Colleague,
) -> None:
    runtime = ProjectRuntime()
    runtime.leases.renew("page-1")

    assert pull_project(str(colleague.folder), runtime=runtime) is False


def test_003_the_update_applies_with_the_gate_held_and_the_index_rebuilt(
    colleague: Colleague,
) -> None:
    runtime = ProjectRuntime()
    gate = ProjectGate()
    colleague.change("shall steer", "shall steer left")
    calls: List[str] = []

    def inhibit(path: str) -> None:
        calls.append(f"inhibit {Path(path).name}")

    def rebuild() -> None:
        # What the server does: it builds the index from the new files, and
        # nobody saves meanwhile.
        calls.append(f"rebuild gate-held={not gate.try_acquire()}")
        calls.append(f"new-files={'steer left' in colleague.read()}")

    runtime.inhibit_change = inhibit
    runtime.rebuild_and_notify = rebuild

    assert pull_project(str(colleague.folder), gate=gate, runtime=runtime)

    assert calls == [
        "inhibit doc.sdoc",
        "rebuild gate-held=True",
        "new-files=True",
    ]
    assert runtime.revision == 1


def test_004_the_end_of_the_typing_applies_the_update_that_waited(
    colleague: Colleague,
) -> None:
    runtime = get_project_runtime(str(colleague.folder))
    runtime.is_update_waiting = False
    manager = _create_manager_with_open_project(str(colleague.folder))
    colleague.change("shall steer", "shall steer left")
    runtime.leases.renew("page-1")

    manager._update_in_background("p", str(colleague.folder))

    assert _wait_for(lambda: runtime.is_update_waiting)
    assert "steer left" not in colleague.read()

    # The editor is closed: the update applies by itself.
    runtime.leases.release("page-1")

    assert _wait_for(lambda: "steer left" in colleague.read())
    assert _wait_for(lambda: runtime.is_update_waiting is False)
    assert runtime.revision >= 1
    runtime.leases.close()


def test_005_an_update_that_waited_applies_if_the_typing_ended_meanwhile(
    colleague: Colleague, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = get_project_runtime(str(colleague.folder))
    manager = _create_manager_with_open_project(str(colleague.folder))
    colleague.change("shall steer", "shall steer left")
    runtime.leases.renew("page-1")
    original = runtime.leases.is_editing
    answers: List[bool] = []

    def is_editing() -> bool:
        # The editor is open when the update looks, closed when it has
        # waited: the end of the typing came between the two.
        answers.append(original())
        if len(answers) == 1:
            return True
        runtime.leases.release("page-1")
        return False

    monkeypatch.setattr(runtime.leases, "is_editing", is_editing)

    manager._update_in_background("p", str(colleague.folder))

    assert _wait_for(lambda: "steer left" in colleague.read())
    runtime.leases.close()


# The server of the project.


def _create_application(
    colleague: Colleague, role: Optional[str] = "administrator"
) -> Starlette:
    config = create_desktop_project_config(
        input_path=str(colleague.folder),
        port=None,
        principal_provider=(
            (lambda: Principal(user="jdupont", role=role))
            if role is not None
            else (lambda: None)
        ),
    )
    return create_project_application(config, lambda: AUTHOR, GitAccess())


def test_006_the_save_after_an_update_is_made_on_the_new_index(
    colleague: Colleague,
) -> None:
    application = _create_application(colleague)
    context = application.state.project_context
    runtime = get_project_runtime(str(colleague.folder))
    colleague.change("shall steer", "shall steer left")

    assert pull_project(
        str(colleague.folder),
        gate=get_project_gate(str(colleague.folder)),
        runtime=runtime,
    )

    # The index was built again inside the update: a save that follows at
    # once writes the new text of the other requirement, not the old one.
    index = context.export_action.traceability_index
    document = index.document_tree.document_list[0]
    context.write_document_to_file(document)
    assert "steer left" in colleague.read()
    # Raised before the build of the index and after it.
    assert runtime.revision == 2


def test_007_a_page_is_stamped_with_the_revision_of_the_files(
    colleague: Colleague,
) -> None:
    client = TestClient(_create_application(colleague))
    runtime = get_project_runtime(str(colleague.folder))
    before = runtime.revision

    answer = client.get("/")
    runtime.bump_revision()
    later = client.get("/")

    assert answer.headers[REVISION_HEADER] == str(before)
    assert answer.headers["server-timing"] == (
        f'desktop_revision;desc="{before}"'
    )
    assert later.headers[REVISION_HEADER] == str(before + 1)


def _create_client_with_write(
    runtime: ProjectRuntime, calls: List[str]
) -> TestClient:
    def write(_: Request) -> Response:
        calls.append("written")
        return PlainTextResponse("written")

    return TestClient(
        ProjectGateMiddleware(
            Starlette(routes=[Route("/save", write, methods=["POST"])]),
            gate=ProjectGate(),
            get_committer=lambda: None,
            runtime=runtime,
        )
    )


def test_008_a_form_on_older_files_is_refused_before_it_writes() -> None:
    runtime = ProjectRuntime()
    calls: List[str] = []
    client = _create_client_with_write(runtime, calls)
    runtime.bump_revision()
    runtime.bump_revision()

    stale = client.post("/save", headers={REVISION_HEADER: "1"})
    current = client.post("/save", headers={REVISION_HEADER: "2"})
    without = client.post("/save")
    garbage = client.post("/save", headers={REVISION_HEADER: "later"})

    assert stale.status_code == 409
    assert stale.headers[CONFLICT_HEADER] == "1"
    assert "Your text is still on the screen" in stale.json()["message"]
    assert [current.status_code, without.status_code, garbage.status_code] == [
        200,
        200,
        200,
    ]
    # Only the three saves that were not refused wrote.
    assert calls == ["written", "written", "written"]


def test_009_the_refusal_is_a_message_for_the_user_in_his_language() -> None:
    i18n.set_language("fr")
    runtime = ProjectRuntime()
    runtime.bump_revision()
    client = _create_client_with_write(runtime, [])

    answer = client.post("/save", headers={REVISION_HEADER: "0"})

    assert answer.status_code == 409
    message = answer.json()["message"]
    assert "Votre texte est toujours à l'écran" in message
    assert "git" not in message.lower()


def test_010_a_read_is_never_refused_and_an_update_is_never_waited_for() -> (
    None
):
    runtime = ProjectRuntime()
    runtime.bump_revision()
    client = TestClient(
        ProjectGateMiddleware(
            Starlette(
                routes=[Route("/page", lambda _: PlainTextResponse("p"))]
            ),
            gate=ProjectGate(),
            get_committer=lambda: None,
            runtime=runtime,
        )
    )

    assert (
        client.get("/page", headers={REVISION_HEADER: "0"}).status_code == 200
    )


# The signal of the editing.


def _post_signal(client: TestClient, page: Any, editing: Any) -> Any:
    return client.post(EDITING_PATH, json={"page": page, "editing": editing})


def test_011_the_signal_takes_a_lease_and_ends_it() -> None:
    runtime = ProjectRuntime()
    client = TestClient(
        ProjectStatusMiddleware(
            Starlette(),
            get_status=lambda: ProjectStatus(SendState.IDLE),
            runtime=runtime,
        )
    )

    first = _post_signal(client, "page-1", True)
    second = _post_signal(client, "page-2", True)
    assert runtime.leases.get_page_count() == 2
    _post_signal(client, "page-1", False)
    assert runtime.leases.is_editing() is True
    _post_signal(client, "page-2", False)

    assert first.status_code == 200
    assert first.json() == {"revision": 0, "update_waiting": False}
    assert second.status_code == 200
    assert runtime.leases.is_editing() is False


@pytest.mark.parametrize(
    "body",
    [
        {"page": "", "editing": True},
        {"page": "x" * 65, "editing": True},
        {"page": 1, "editing": True},
        {"page": "a", "editing": "yes"},
        {"page": "a"},
        ["page"],
    ],
)
def test_012_a_signal_that_is_not_one_of_the_page_is_refused(
    body: Any,
) -> None:
    runtime = ProjectRuntime()
    client = TestClient(
        ProjectStatusMiddleware(
            Starlette(),
            get_status=lambda: ProjectStatus(SendState.IDLE),
            runtime=runtime,
        )
    )

    answer = client.post(EDITING_PATH, json=body)
    not_json = client.post(EDITING_PATH, content=b"\xff\xfe")

    assert answer.status_code == 400
    assert not_json.status_code == 400
    assert runtime.leases.get_page_count() == 0


def test_013_the_status_tells_the_editing_the_revision_and_the_update(
    colleague: Colleague,
) -> None:
    client = TestClient(_create_application(colleague))
    runtime = get_project_runtime(str(colleague.folder))
    runtime.leases.renew("page-1")
    runtime.is_update_waiting = True
    try:
        answer = client.get(STATUS_PATH).json()

        assert answer["editing"] is True
        assert answer["update_waiting"] is True
        assert answer["revision"] == runtime.revision
    finally:
        runtime.leases.release("page-1")
        runtime.is_update_waiting = False


def test_014_the_signal_takes_no_gate_commits_nothing_and_asks_for_a_user(
    colleague: Colleague,
) -> None:
    reader = TestClient(_create_application(colleague, role="reader"))
    nobody = TestClient(_create_application(colleague, role=None))
    gate = get_project_gate(str(colleague.folder))
    head = Repo(colleague.folder).head.commit.hexsha
    (colleague.folder / "waiting.sdoc").write_text("[DOCUMENT]\nTITLE: W\n")

    # A page that types never waits for the gate, and a reader may signal.
    with gate.hold():
        thread_result: List[int] = []
        thread = threading.Thread(
            target=lambda: thread_result.append(
                _post_signal(reader, "page-1", True).status_code
            )
        )
        thread.start()
        thread.join(5)
        assert thread_result == [200]
    refused = _post_signal(nobody, "page-2", True)

    assert refused.status_code == 401
    assert Repo(colleague.folder).head.commit.hexsha == head
    runtime = get_project_runtime(str(colleague.folder))
    assert runtime.leases.get_page_count() == 1
    runtime.leases.release("page-1")


def test_015_the_pages_of_the_application_have_the_code_of_the_editing(
    colleague: Colleague,
) -> None:
    client = TestClient(_create_application(colleague))
    # The language of the application is the one of the process.
    i18n.set_language("fr")

    page = client.get("/").text

    assert "window.sdocDesktop" in page
    assert "/__desktop/editing" in page
    # A window that comes back renews its lease at once.
    assert "visibilitychange" in page
    # The reload that the server asks for asks the code of the application.
    assert "window.sdocDesktop.onReload()" in page
    # The texts are in the language, as the data of a script.
    assert (
        "elle s\\u0027applique quand vous fermez l\\u0027\\u00e9diteur" in page
    )
    assert "La page se recharge quand vous fermez l\\u0027\\u00e9diteur" in page


def test_016_the_watcher_raises_the_revision_for_a_change_from_outside(
    colleague: Colleague,
) -> None:
    application = _create_application(colleague)
    context = application.state.project_context
    runtime = get_project_runtime(str(colleague.folder))
    watcher = context.document_watcher
    assert watcher is not None
    before = runtime.revision

    # The function that the watcher calls after a change that nobody made
    # through the server: the revision rises, and the index is built again
    # (the revision rises once more when the build ends).
    watcher._on_documents_changed()

    assert runtime.revision == before + 2
    assert runtime.rebuild_and_notify is not None
    assert runtime.inhibit_change is not None
    _ = json


# An update that brings files that do not build.

DOCUMENT_MID = "1d6c2b5f8a9e4e1fb7c3a0d4e5f60a11"
BROKEN = "[DOCUMENT]\nTITLE: B\n\n[REQUIREMENT]\nUID: REQ-9\nTHIS IS NOT SDOC\n"
REPAIRED = "[DOCUMENT]\nTITLE: B\n"


def _save_title(client: TestClient) -> Any:
    return client.post(
        "/actions/document/save_config",
        data={"document_mid": DOCUMENT_MID, "document[TITLE]": "Doc"},
    )


def _apply_broken_update(
    colleague: Colleague, client: TestClient, runtime: ProjectRuntime
) -> None:
    colleague.send(
        {
            "doc.sdoc": colleague.read().replace(
                "shall steer", "shall steer left"
            ),
            "b.sdoc": BROKEN,
        }
    )
    assert pull_project(
        str(colleague.folder),
        gate=get_project_gate(str(colleague.folder)),
        runtime=runtime,
    )
    # The files are the ones of the colleague, and the index is the old one.
    assert "steer left" in colleague.read()
    assert "steer left" not in _get_statement_texts(client)


def _get_statement_texts(client: TestClient) -> str:
    return str(client.get("/").text)


def test_017_no_save_replaces_the_files_while_the_index_is_the_old_one(
    colleague: Colleague,
) -> None:
    client = TestClient(_create_application(colleague))
    runtime = get_project_runtime(str(colleague.folder))
    _apply_broken_update(colleague, client, runtime)
    head = Repo(colleague.folder).head.commit.hexsha

    refused = _save_title(client)

    assert refused.status_code == 409
    assert refused.headers[CONFLICT_HEADER] == "1"
    message = refused.json()["message"]
    assert "cannot be read" in message
    assert "git" not in message.lower()
    # The sentence of the colleague is still on the disk, nothing committed.
    assert "steer left" in colleague.read()
    assert Repo(colleague.folder).head.commit.hexsha == head
    # A page is not refused, and the indicator says why saving is refused.
    assert client.get("/").status_code == 200
    status = client.get(STATUS_PATH).json()
    assert status["state"] == "unreadable"
    assert "git" not in status["message"].lower()


def test_018_the_refusal_covers_a_write_that_has_no_header_of_revision(
    colleague: Colleague,
) -> None:
    client = TestClient(_create_application(colleague))
    runtime = get_project_runtime(str(colleague.folder))
    _apply_broken_update(colleague, client, runtime)

    answer = client.post(
        "/actions/document/save_config",
        data={"document_mid": DOCUMENT_MID, "document[TITLE]": "Doc"},
        headers={REVISION_HEADER: str(runtime.revision)},
    )

    assert answer.status_code == 409
    assert "steer left" in colleague.read()


def test_019_the_next_update_that_repairs_the_files_lifts_the_refusal(
    colleague: Colleague,
) -> None:
    client = TestClient(_create_application(colleague))
    runtime = get_project_runtime(str(colleague.folder))
    _apply_broken_update(colleague, client, runtime)
    assert _save_title(client).status_code == 409

    colleague.send({"b.sdoc": REPAIRED})
    assert pull_project(
        str(colleague.folder),
        gate=get_project_gate(str(colleague.folder)),
        runtime=runtime,
    )

    assert _save_title(client).status_code != 409
    assert client.get(STATUS_PATH).json()["state"] != "unreadable"
    # The save was made on the new index: the sentence is still there.
    assert "steer left" in colleague.read()


def test_020_a_change_from_outside_that_does_not_build_refuses_the_saves(
    colleague: Colleague,
) -> None:
    application = _create_application(colleague)
    client = TestClient(application)
    watcher = application.state.project_context.document_watcher
    (colleague.folder / "doc.sdoc").write_text(
        colleague.read().replace("shall steer", "shall steer left")
    )
    (colleague.folder / "b.sdoc").write_text(BROKEN)

    watcher._on_documents_changed()

    assert _save_title(client).status_code == 409
    assert "steer left" in colleague.read()
    (colleague.folder / "b.sdoc").write_text(REPAIRED)
    watcher._on_documents_changed()
    assert _save_title(client).status_code != 409


def test_021_the_revision_rises_after_the_index_is_built_not_only_before(
    colleague: Colleague, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_application(colleague)
    runtime = get_project_runtime(str(colleague.folder))
    seen: List[int] = []
    create = project_context.TraceabilityIndexBuilder.create

    def create_and_look(*arguments: Any, **keywords: Any) -> Any:
        # A page that is served now is built on the old index.
        seen.append(runtime.revision)
        return create(*arguments, **keywords)

    monkeypatch.setattr(
        project_context.TraceabilityIndexBuilder, "create", create_and_look
    )
    colleague.change("shall steer", "shall steer left")

    assert pull_project(
        str(colleague.folder),
        gate=get_project_gate(str(colleague.folder)),
        runtime=runtime,
    )

    assert len(seen) == 1
    assert runtime.revision > seen[0]


def test_022_the_watcher_raises_the_revision_after_the_build_too(
    colleague: Colleague, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = _create_application(colleague)
    runtime = get_project_runtime(str(colleague.folder))
    watcher = application.state.project_context.document_watcher
    seen: List[int] = []
    create = project_context.TraceabilityIndexBuilder.create

    def create_and_look(*arguments: Any, **keywords: Any) -> Any:
        seen.append(runtime.revision)
        return create(*arguments, **keywords)

    monkeypatch.setattr(
        project_context.TraceabilityIndexBuilder, "create", create_and_look
    )

    watcher._on_documents_changed()

    assert len(seen) == 1
    assert runtime.revision > seen[0]


@pytest.mark.parametrize(
    "failure",
    [WorkspaceError("not a fast-forward"), RuntimeError("boom"), None],
)
def test_023_an_update_that_ends_without_a_report_is_not_announced_any_more(
    tmp_path: Path, failure: Optional[Exception]
) -> None:
    folder = str(tmp_path)
    runtime = get_project_runtime(folder)
    runtime.is_update_waiting = True

    def update(_: str) -> bool:
        if failure is not None:
            raise failure
        return False

    manager = _create_manager_with_open_project(folder, update)

    manager._update_in_background("p", folder)

    assert _wait_for(lambda: runtime.is_update_waiting is False)


def test_024_an_update_that_is_postponed_stays_announced(
    tmp_path: Path,
) -> None:
    folder = str(tmp_path / "waiting")
    runtime = get_project_runtime(folder)
    runtime.is_update_waiting = False
    runtime.leases.renew("page-1")

    def update(_: str) -> bool:
        raise UpdateDeferredError("waits")

    manager = _create_manager_with_open_project(folder, update)

    manager._update_in_background("p", folder)

    assert _wait_for(lambda: runtime.is_update_waiting is True)
    runtime.leases.close()


def test_025_a_file_with_an_accent_is_given_to_the_watcher_by_its_name(
    colleague: Colleague,
) -> None:
    runtime = ProjectRuntime()
    seen: List[str] = []
    runtime.inhibit_change = seen.append
    runtime.rebuild_and_notify = lambda: None
    colleague.send({"é.sdoc": REPAIRED, "with space.sdoc": REPAIRED})

    assert pull_project(str(colleague.folder), runtime=runtime)

    assert sorted(Path(path_).name for path_ in seen) == [
        "with space.sdoc",
        "é.sdoc",
    ]
    assert all(Path(path_).is_file() for path_ in seen)


def test_026_a_project_that_opens_again_on_repaired_files_accepts_saves(
    colleague: Colleague,
) -> None:
    client = TestClient(_create_application(colleague))
    runtime = get_project_runtime(str(colleague.folder))
    _apply_broken_update(colleague, client, runtime)
    assert runtime.is_index_outdated is True
    # The project is closed, the user repairs the file outside of the
    # application, and the project opens again on a new server.
    (colleague.folder / "b.sdoc").write_text(REPAIRED)

    new_client = TestClient(_create_application(colleague))

    assert runtime.is_index_outdated is False
    assert _save_title(new_client).status_code != 409


def test_027_a_first_index_that_fails_leaves_the_saves_refused(
    colleague: Colleague,
) -> None:
    client = TestClient(_create_application(colleague))
    runtime = get_project_runtime(str(colleague.folder))
    _apply_broken_update(colleague, client, runtime)

    with pytest.raises(StrictDocException):
        _create_application(colleague)

    assert runtime.is_index_outdated is True


class _StubServer:
    start_url = "http://127.0.0.1:1/start"
    direct_url = "http://127.0.0.1:1/"
    is_bootstrapped = False

    def set_bootstrap_listener(self, listener: object) -> None:
        del listener

    def start(self) -> None:
        pass

    def wait_until_ready(self) -> None:
        pass

    def stop(self) -> None:
        pass


def _create_stub_server(*arguments: Any) -> _StubServer:
    del arguments
    return _StubServer()


def _create_manager_with_open_project(
    folder: str, updater: Optional[Callable[[str], bool]] = None
) -> ProjectServerManager:
    manager = ProjectServerManager(
        server_factory=_create_stub_server,  # type: ignore[arg-type]
        updater=updater,
        eviction_delay_seconds=0,
        sync_interval_seconds=3600,
    )
    manager.open("p", folder, is_update_needed=False)
    return manager


def _create_recorder(calls: List[str]) -> Callable[[str], bool]:
    def update(folder: str) -> bool:
        calls.append(folder)
        return False

    return update


def test_028_an_update_that_waited_does_not_apply_to_a_closed_project(
    tmp_path: Path,
) -> None:
    folder = str(tmp_path / "closed")
    runtime = get_project_runtime(folder)
    runtime.is_update_waiting = False
    runtime.leases.renew("page-1")
    calls: List[str] = []

    def update(_: str) -> bool:
        calls.append("update")
        if len(calls) == 1:
            raise UpdateDeferredError("waits")
        return False

    manager = _create_manager_with_open_project(folder, update)
    manager._update_in_background("p", folder)
    assert _wait_for(lambda: runtime.is_update_waiting is True)

    manager.stop_project("p")
    runtime.leases.release("page-1")

    assert _wait_for(lambda: len(calls) > 1, seconds=0.5) is False
    assert manager._deferred == {}
    assert manager._rerun == {}
    assert runtime.is_update_waiting is False
    runtime.leases.close()


def test_029_an_update_asked_for_a_closed_project_does_nothing(
    tmp_path: Path,
) -> None:
    folder = str(tmp_path / "closed")
    calls: List[str] = []
    manager = _create_manager_with_open_project(folder, _create_recorder(calls))
    manager.stop_servers()

    manager._update_in_background("p", folder)

    assert _wait_for(lambda: len(calls) > 0, seconds=0.5) is False
    assert manager._updating == set()


def test_030_an_update_asked_with_another_folder_does_nothing(
    tmp_path: Path,
) -> None:
    folder = str(tmp_path / "open")
    calls: List[str] = []
    manager = _create_manager_with_open_project(folder, _create_recorder(calls))

    manager._update_in_background("p", str(tmp_path / "elsewhere"))

    assert _wait_for(lambda: len(calls) > 0, seconds=0.5) is False
    manager.stop_servers()
