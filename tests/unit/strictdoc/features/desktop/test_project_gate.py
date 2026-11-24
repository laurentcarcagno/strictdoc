"""
The gate of a project, and the commit at the end of a write request.

@relation(SDOC-SRS-1242, scope=file)
@relation(SDOC-SRS-1243, scope=file)
"""

import asyncio
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest
from git import Actor, Repo
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from strictdoc.features.desktop import project_gate as project_gate_module
from strictdoc.features.desktop.commit_author import CommitAuthorError
from strictdoc.features.desktop.git_access import DesktopGitService, GitAccess
from strictdoc.features.desktop.local_server import (
    create_desktop_project_config,
    create_project_application,
)
from strictdoc.features.desktop.project_gate import (
    ProjectGate,
    ProjectGateMiddleware,
    commit_pending_changes,
    get_project_gate,
)
from strictdoc.features.desktop.workspace import pull_project
from strictdoc.features.git_config.committer import GitCommitter
from strictdoc.features.git_config.git_service import Author
from strictdoc.features.roles.principal import Principal

SEED = Actor("Seed", "seed@example.org")
JEANNE = Author("Jeanne Dupont", "jeanne@example.org")


@dataclass
class Setup:
    root: Path
    committer: GitCommitter
    client: TestClient
    commits: List[int]

    def get_head(self) -> str:
        return _git(self.root, "rev-parse", "HEAD")

    def get_count(self) -> int:
        return int(_git(self.root, "rev-list", "--count", "HEAD"))


def _git(folder: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=folder,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _create_application(
    root: Path, committer: GitCommitter
) -> ProjectGateMiddleware:
    def delete_document(_: Request) -> Response:
        os.remove(root / "doc.sdoc")
        return PlainTextResponse("deleted")

    def rename_document(_: Request) -> Response:
        os.rename(root / "doc.sdoc", root / "renamed.sdoc")
        return PlainTextResponse("renamed")

    def touch_by_get(_: Request) -> Response:
        (root / "touched.sdoc").write_text("[DOCUMENT]\nTITLE: Touched\n")
        return PlainTextResponse("touched")

    def fail(_: Request) -> Response:
        (root / "failed.sdoc").write_text("[DOCUMENT]\nTITLE: Failed\n")
        return PlainTextResponse("failed", status_code=500)

    def refuse(_: Request) -> Response:
        (root / "refused.sdoc").write_text("[DOCUMENT]\nTITLE: Refused\n")
        return PlainTextResponse("refused", status_code=403)

    def write_ignored(_: Request) -> Response:
        (root / "ignored.txt").write_text("a secret of the user\n")
        (root / "new.sdoc").write_text("[DOCUMENT]\nTITLE: New\n")
        return PlainTextResponse("written")

    def upload(_: Request) -> Response:
        asset = root / "_assets" / "a.png"
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(b"png")
        committer.on_asset_written(str(asset))
        return PlainTextResponse("uploaded")

    def delete_and_upload(_: Request) -> Response:
        os.remove(root / "doc.sdoc")
        return upload(_)

    def nothing(_: Request) -> Response:
        return PlainTextResponse("nothing")

    application = Starlette(
        routes=[
            Route("/delete", delete_document, methods=["POST"]),
            Route("/rename", rename_document, methods=["POST"]),
            Route("/touch", touch_by_get, methods=["GET", "POST"]),
            Route("/fail", fail, methods=["POST"]),
            Route("/refuse", refuse, methods=["POST"]),
            Route("/ignored", write_ignored, methods=["POST"]),
            Route("/upload", upload, methods=["POST"]),
            Route("/delete-and-upload", delete_and_upload, methods=["POST"]),
            Route("/nothing", nothing, methods=["POST"]),
        ]
    )
    return ProjectGateMiddleware(
        application,
        gate=ProjectGate(),
        get_committer=lambda: committer,
        # The routes of this application are the ones of an author.
        get_required_role=lambda *_: "author",
    )


def _create_repository(root: Path) -> None:
    root.mkdir()
    (root / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: Doc\n")
    (root / ".gitignore").write_text("ignored.txt\n")
    repo = Repo.init(root, initial_branch="main")
    repo.index.add(["doc.sdoc", ".gitignore"])
    repo.index.commit("Seed", author=SEED, committer=SEED)
    repo.close()


@pytest.fixture(name="setup")
def fixture_setup(tmp_path: Path) -> Setup:
    root = tmp_path / "project"
    _create_repository(root)
    service = DesktopGitService(str(root), GitAccess())
    committer = GitCommitter(service, lambda: JEANNE)
    commits: List[int] = []
    committer.after_commit = lambda: commits.append(1)
    client = TestClient(_create_application(root, committer))
    return Setup(root, committer, client, commits)


def test_001_a_deletion_is_committed_at_the_end_of_the_request(
    setup: Setup,
) -> None:
    response = setup.client.post("/delete")

    assert response.status_code == 200
    assert setup.get_count() == 2
    assert _git(setup.root, "log", "-1", "--format=%an <%ae>") == (
        "Jeanne Dupont <jeanne@example.org>"
    )
    assert (
        _git(setup.root, "log", "-1", "--format=%s") == "chore: save doc.sdoc"
    )
    assert _git(setup.root, "status", "--porcelain") == ""
    # The commit goes to the queue.
    assert setup.commits == [1]


def test_002_a_move_is_one_commit(setup: Setup) -> None:
    setup.client.post("/rename")

    assert setup.get_count() == 2
    assert _git(setup.root, "log", "-1", "--format=%s") == "chore: save 2 files"
    assert _git(setup.root, "status", "--porcelain") == ""


def test_003_a_request_that_reads_commits_nothing(setup: Setup) -> None:
    head = setup.get_head()

    response = setup.client.get("/touch")

    assert response.status_code == 200
    assert setup.get_head() == head
    # The file is there for the next write of the user.
    assert (setup.root / "touched.sdoc").exists()
    assert setup.commits == []


@pytest.mark.parametrize("path", ["/fail", "/refuse"])
def test_004_a_request_that_failed_or_was_refused_commits_nothing(
    setup: Setup, path: str
) -> None:
    head = setup.get_head()

    setup.client.post(path)

    assert setup.get_head() == head
    assert setup.commits == []


def test_005_what_gitignore_ignores_stays_out(setup: Setup) -> None:
    setup.client.post("/ignored")

    assert setup.get_count() == 2
    names = _git(setup.root, "show", "--name-only", "--format=", "HEAD")
    assert names == "new.sdoc"
    assert (setup.root / "ignored.txt").exists()


def test_006_an_upload_waits_for_its_document(setup: Setup) -> None:
    head = setup.get_head()

    setup.client.post("/upload")

    assert setup.get_head() == head
    assert setup.committer.pending_paths == [
        str(setup.root / "_assets" / "a.png")
    ]


def test_007_the_commit_of_a_request_leaves_the_uploads_that_wait(
    setup: Setup,
) -> None:
    setup.client.post("/delete-and-upload")

    names = _git(setup.root, "show", "--name-only", "--format=", "HEAD")
    assert names == "doc.sdoc"
    # The upload is still not committed, and still waits.
    assert _git(setup.root, "status", "--porcelain") == "?? _assets/"
    assert len(setup.committer.pending_paths) == 1

    # The next save of a document commits it, as before.
    (setup.root / "new.sdoc").write_text("[DOCUMENT]\nTITLE: New\n")
    setup.committer.on_document_written(str(setup.root / "new.sdoc"))
    assert _git(setup.root, "status", "--porcelain") == ""


def _start_conflicting_merge(root: Path) -> str:
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@example.org")
    _git(root, "checkout", "-q", "-b", "other")
    (root / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: On the other branch\n")
    _git(root, "commit", "-q", "-am", "other")
    _git(root, "checkout", "-q", "main")
    (root / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: On main\n")
    _git(root, "commit", "-q", "-am", "main")
    merge = subprocess.run(
        ["git", "merge", "other"], cwd=root, capture_output=True, check=False
    )
    assert merge.returncode != 0
    assert (root / ".git" / "MERGE_HEAD").exists()
    return _git(root, "rev-parse", "HEAD")


def test_008_nothing_is_committed_while_a_merge_waits(setup: Setup) -> None:
    head = _start_conflicting_merge(setup.root)
    conflicted = (setup.root / "doc.sdoc").read_text()
    assert "<<<<<<<" in conflicted

    response = setup.client.post("/ignored")

    assert response.status_code == 200
    # The merge is not concluded with the markers, and nothing else is
    # committed with it.
    assert setup.get_head() == head
    assert (setup.root / ".git" / "MERGE_HEAD").exists()
    assert (setup.root / "doc.sdoc").read_text() == conflicted
    assert setup.commits == []
    # Not an error to show: the commit was not tried.
    assert setup.committer.last_error == ""
    assert commit_pending_changes(setup.committer) is False
    assert setup.committer.last_error == ""


@pytest.mark.parametrize(
    "marker",
    ["CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"],
)
def test_009_a_rebase_a_cherry_pick_or_a_revert_that_waits_blocks_the_commit(
    setup: Setup, marker: str
) -> None:
    head = setup.get_head()
    marker_path = setup.root / ".git" / marker
    if marker.startswith("rebase"):
        marker_path.mkdir()
    else:
        marker_path.write_text(f"{head}\n")

    setup.client.post("/delete")

    assert setup.get_head() == head
    assert setup.commits == []


def test_010_a_commit_that_fails_is_shown_and_never_breaks_the_answer(
    setup: Setup,
) -> None:
    def refuse() -> Author:
        raise CommitAuthorError(
            "Nobody is signed in: the change has no author."
        )

    setup.committer.author_provider = refuse
    head = setup.get_head()

    response = setup.client.post("/delete")

    assert response.status_code == 200
    assert response.text == "deleted"
    assert setup.get_head() == head
    assert "Nobody is signed in" in setup.committer.last_error


def test_011_a_function_after_the_commit_that_fails_never_breaks_the_save(
    setup: Setup,
) -> None:
    def fail() -> None:
        raise RuntimeError("the queue is broken")

    setup.committer.after_commit = fail

    response = setup.client.post("/delete")

    assert response.status_code == 200
    assert setup.get_count() == 2
    assert setup.committer.last_error == ""


def test_012_a_write_waits_for_the_gate_and_a_read_does_not(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    _create_repository(root)
    committer = GitCommitter(
        DesktopGitService(str(root), GitAccess()), lambda: JEANNE
    )
    gate = ProjectGate()
    client = TestClient(
        ProjectGateMiddleware(
            _create_application(root, committer).app,
            gate=gate,
            get_committer=lambda: committer,
        )
    )
    answers: List[int] = []

    def write() -> None:
        answers.append(client.post("/nothing").status_code)

    with gate.hold():
        thread = threading.Thread(target=write)
        thread.start()
        thread.join(0.5)
        assert thread.is_alive()
        assert client.get("/touch").status_code == 200
    thread.join(10)

    assert answers == [200]


def test_013_the_same_folder_has_the_same_gate(tmp_path: Path) -> None:
    folder = tmp_path / "project"
    folder.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(folder, target_is_directory=True)
    except OSError:
        pytest.skip("No symbolic link here.")

    assert get_project_gate(str(folder)) is get_project_gate(str(folder))
    assert get_project_gate(str(link)) is get_project_gate(str(folder))
    assert get_project_gate(str(tmp_path)) is not get_project_gate(str(folder))


def test_014_the_update_changes_the_files_inside_the_gate_only(
    tmp_path: Path,
) -> None:
    # A project and its server, and a colleague who changes the document.
    server = tmp_path / "remote.git"
    work = tmp_path / "work"
    _create_repository(work)
    Repo.clone_from(str(work), str(server), bare=True).close()
    folder = tmp_path / "workspace"
    Repo.clone_from(str(server), str(folder)).close()
    colleague = tmp_path / "colleague"
    colleague_repo = Repo.clone_from(str(server), str(colleague))
    (colleague / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: Colleague\n")
    colleague_repo.index.add(["doc.sdoc"])
    colleague_repo.index.commit("Change", author=SEED, committer=SEED)
    colleague_repo.git.push("origin", "main")
    colleague_repo.close()
    gate = get_project_gate(str(folder))
    results: List[bool] = []

    def update() -> None:
        results.append(pull_project(str(folder), gate=gate))

    with gate.hold():
        thread = threading.Thread(target=update)
        thread.start()
        time.sleep(1.0)
        # The fetch is done and the update waits: the files are not changed.
        assert thread.is_alive()
        assert "Colleague" not in (folder / "doc.sdoc").read_text()
    thread.join(20)

    assert results == [True]
    assert "Colleague" in (folder / "doc.sdoc").read_text()


def test_015_a_project_with_no_committer_is_served_as_it_is() -> None:
    gate = ProjectGate()
    client = TestClient(
        ProjectGateMiddleware(
            Starlette(
                routes=[
                    Route(
                        "/x",
                        lambda _: PlainTextResponse("x"),
                        methods=["POST"],
                    )
                ]
            ),
            gate=gate,
            get_committer=lambda: None,
        )
    )

    assert client.post("/x").status_code == 200
    # The gate is free again after the request.
    with gate.hold():
        pass


def _create_provider(role: str) -> Callable[[], Optional[Principal]]:
    return lambda: Principal(user="jdupont", role=role)


def _create_two_documents(root: Path) -> None:
    root.mkdir()
    for name_ in ("a", "b"):
        (root / f"{name_}.sdoc").write_text(f"[DOCUMENT]\nTITLE: Doc {name_}\n")
    repo = Repo.init(root, initial_branch="main")
    repo.index.add(["a.sdoc", "b.sdoc"])
    repo.index.commit("Seed", author=SEED, committer=SEED)
    repo.close()


def _delete_first_document(root: Path, role: str) -> int:
    """Delete a document in the server of the application, with this role."""
    config = create_desktop_project_config(
        input_path=str(root),
        port=None,
        principal_provider=lambda: Principal(user="jdupont", role=role),
    )
    application = create_project_application(
        config, lambda: JEANNE, GitAccess()
    )
    index = application.state.project_context.export_action.traceability_index
    document = index.document_tree.document_list[0]
    answer = TestClient(application).delete(
        "/actions/document/delete_document",
        params={"document_mid": document.reserved_mid, "confirmed": "true"},
        follow_redirects=False,
    )
    return int(answer.status_code)


def test_017_the_deletion_of_a_document_of_the_server_is_committed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STRICTDOC_AUTH_MODE", raising=False)
    root = tmp_path / "project"
    _create_two_documents(root)

    status_code = _delete_first_document(root, "administrator")

    assert status_code == 303
    assert sorted(path_.name for path_ in root.glob("*.sdoc")) == ["b.sdoc"]
    assert _git(root, "log", "-1", "--format=%an %s") == (
        "Jeanne Dupont chore: save a.sdoc"
    )
    assert _git(root, "status", "--porcelain") == ""


def test_018_a_reader_that_the_roles_refuse_commits_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STRICTDOC_AUTH_MODE", raising=False)
    root = tmp_path / "project"
    _create_two_documents(root)
    head = _git(root, "rev-parse", "HEAD")
    # A change of the user that waits in the files: the refusal of another
    # request does not commit it.
    (root / "waiting.sdoc").write_text("[DOCUMENT]\nTITLE: Waiting\n")

    status_code = _delete_first_document(root, "reader")

    assert status_code == 403
    assert sorted(path_.name for path_ in root.glob("*.sdoc")) == [
        "a.sdoc",
        "b.sdoc",
        "waiting.sdoc",
    ]
    assert _git(root, "rev-parse", "HEAD") == head


# The gate does not leak, does not starve, and does not hold what does not
# write.


def _create_asgi_request(method: str, path: str) -> Dict[str, Any]:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "query_string": b"",
    }


async def _receive() -> Dict[str, Any]:
    return {"type": "http.request", "body": b"", "more_body": False}


async def _send(message: Dict[str, Any]) -> None:
    del message


async def _answer_ok(
    scope: Dict[str, Any],
    receive: Callable[..., Any],
    send: Callable[..., Any],
) -> None:
    del scope, receive
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def test_019_a_request_cancelled_while_it_waits_leaves_the_gate_free() -> None:
    gate = ProjectGate()
    middleware = ProjectGateMiddleware(
        _answer_ok, gate=gate, get_committer=lambda: None
    )

    async def scenario() -> None:
        gate.acquire()
        task = asyncio.create_task(
            middleware(_create_asgi_request("POST", "/x"), _receive, _send)
        )
        await asyncio.sleep(0.2)
        task.cancel()
        await asyncio.sleep(0.1)
        # The holder lets go: nobody takes the gate for the dead request.
        gate.release()
        await asyncio.sleep(0.3)
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())

    assert gate.try_acquire() is True
    gate.release()


def test_020_a_request_cancelled_while_it_runs_leaves_the_gate_free() -> None:
    gate = ProjectGate()
    started = threading.Event()

    async def slow_application(
        scope: Dict[str, Any],
        receive: Callable[..., Any],
        send: Callable[..., Any],
    ) -> None:
        del scope, receive, send
        started.set()
        await asyncio.sleep(30)

    middleware = ProjectGateMiddleware(
        slow_application, gate=gate, get_committer=lambda: None
    )

    async def scenario() -> None:
        task = asyncio.create_task(
            middleware(_create_asgi_request("POST", "/x"), _receive, _send)
        )
        while not started.is_set():
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())

    assert gate.try_acquire() is True
    gate.release()


def test_021_a_request_cancelled_during_its_commit_ends_the_commit_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = ProjectGate()
    in_commit = threading.Event()
    let_commit_end = threading.Event()
    gate_during_commit: List[bool] = []

    def slow_commit(committer: object) -> bool:
        del committer
        in_commit.set()
        let_commit_end.wait(10)
        return False

    monkeypatch.setattr(
        project_gate_module, "commit_pending_changes", slow_commit
    )
    middleware = ProjectGateMiddleware(
        _answer_ok,
        gate=gate,
        get_committer=object,  # type: ignore[arg-type]
        get_required_role=lambda *_: "author",
    )

    async def scenario() -> None:
        task = asyncio.create_task(
            middleware(_create_asgi_request("POST", "/x"), _receive, _send)
        )
        while not in_commit.is_set():
            await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0.1)
        # The commit still runs: nobody else may change the files now.
        gate_during_commit.append(gate.try_acquire())
        let_commit_end.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())

    assert gate_during_commit == [False]
    assert gate.try_acquire() is True
    gate.release()


def test_022_fifty_writes_at_once_all_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = ProjectGate()
    monkeypatch.setattr(
        project_gate_module, "commit_pending_changes", lambda _: False
    )
    middleware = ProjectGateMiddleware(
        _answer_ok,
        gate=gate,
        get_committer=object,  # type: ignore[arg-type]
        get_required_role=lambda *_: "author",
    )

    async def scenario() -> None:
        await asyncio.wait_for(
            asyncio.gather(
                *[
                    middleware(
                        _create_asgi_request("POST", "/x"), _receive, _send
                    )
                    for _ in range(50)
                ]
            ),
            30,
        )

    asyncio.run(scenario())

    assert gate.try_acquire() is True
    gate.release()


UNGATED_ROUTES = [
    ("POST", "/actions/llm/assist"),
    ("POST", "/actions/llm/draft"),
    ("DELETE", "/actions/llm/jobs/j-1"),
    ("POST", "/docx/export"),
    ("POST", "/actions/project_index/export_docx_preview"),
    ("POST", "/actions/project_index/import_docx_preview"),
    ("POST", "/actions/git/push"),
]


def _create_client_of_routes(
    gate: ProjectGate, committer: Optional[GitCommitter] = None
) -> TestClient:
    paths = {path_ for _, path_ in UNGATED_ROUTES} | {"/unknown"}
    routes = [
        Route(path_, lambda _: PlainTextResponse("done"), methods=["POST"])
        for path_ in paths
        if "jobs" not in path_
    ] + [
        Route(
            "/actions/llm/jobs/{job_id}",
            lambda _: PlainTextResponse("done"),
            methods=["DELETE"],
        )
    ]
    return TestClient(
        ProjectGateMiddleware(
            Starlette(routes=routes),
            gate=gate,
            get_committer=lambda: committer,
        )
    )


def _call_in_thread(
    client: TestClient, method: str, path: str
) -> "tuple[threading.Thread, List[int]]":
    answers: List[int] = []

    def call() -> None:
        answers.append(client.request(method, path).status_code)

    thread = threading.Thread(target=call)
    thread.start()
    return thread, answers


@pytest.mark.parametrize(("method", "path"), UNGATED_ROUTES)
def test_023_a_long_request_that_writes_nothing_does_not_wait_for_the_gate(
    method: str, path: str
) -> None:
    gate = ProjectGate()
    client = _create_client_of_routes(gate)

    with gate.hold():
        thread, answers = _call_in_thread(client, method, path)
        thread.join(2)
        assert answers == [200]


def test_024_a_route_that_is_not_in_the_list_waits_for_the_gate() -> None:
    gate = ProjectGate()
    client = _create_client_of_routes(gate)

    with gate.hold():
        thread, answers = _call_in_thread(client, "POST", "/unknown")
        thread.join(0.5)
        assert thread.is_alive()
    thread.join(10)

    assert answers == [200]


def test_025_a_long_request_does_not_hold_the_gate_while_it_runs() -> None:
    gate = ProjectGate()
    release_request = threading.Event()
    started = threading.Event()

    def slow(_: Request) -> Response:
        started.set()
        release_request.wait(10)
        return PlainTextResponse("done")

    client = TestClient(
        ProjectGateMiddleware(
            Starlette(
                routes=[Route("/actions/llm/assist", slow, methods=["POST"])]
            ),
            gate=gate,
            get_committer=lambda: None,
        )
    )
    thread, answers = _call_in_thread(client, "POST", "/actions/llm/assist")
    try:
        assert started.wait(10)

        # A save meanwhile: the gate is free.
        assert gate.try_acquire() is True
        gate.release()
    finally:
        release_request.set()
        thread.join(10)
    assert answers == [200]


def _create_behind_workspace(tmp_path: Path) -> "tuple[Path, Path]":
    server = tmp_path / "remote.git"
    work = tmp_path / "work"
    _create_repository(work)
    Repo.clone_from(str(work), str(server), bare=True).close()
    folder = tmp_path / "workspace"
    Repo.clone_from(str(server), str(folder)).close()
    colleague = tmp_path / "colleague"
    colleague_repo = Repo.clone_from(str(server), str(colleague))
    (colleague / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: Colleague\n")
    colleague_repo.index.add(["doc.sdoc"])
    colleague_repo.index.commit("Change", author=SEED, committer=SEED)
    colleague_repo.git.push("origin", "main")
    colleague_repo.close()
    return folder, server


def test_026_the_push_changes_the_files_inside_the_gate_only(
    tmp_path: Path,
) -> None:
    folder, server = _create_behind_workspace(tmp_path)
    service = DesktopGitService(str(folder), GitAccess())
    gate = get_project_gate(str(folder))
    errors: List[BaseException] = []

    def push() -> None:
        try:
            service.push(str(folder))
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    with gate.hold():
        thread = threading.Thread(target=push)
        thread.start()
        time.sleep(1.5)
        # Behind the server: the fast-forward waits, the files are not changed.
        assert thread.is_alive()
        assert "Colleague" not in (folder / "doc.sdoc").read_text()
    thread.join(20)

    assert errors == []
    assert "Colleague" in (folder / "doc.sdoc").read_text()


def test_027_a_push_inside_a_request_does_not_wait_for_itself(
    tmp_path: Path,
) -> None:
    folder, server = _create_behind_workspace(tmp_path)
    service = DesktopGitService(str(folder), GitAccess())
    gate = get_project_gate(str(folder))
    answers: List[str] = []

    def push_route(_: Request) -> Response:
        # A route that writes, and pushes, as the version of a document does.
        service.push(str(folder))
        answers.append("pushed")
        return PlainTextResponse("done")

    client = TestClient(
        ProjectGateMiddleware(
            Starlette(routes=[Route("/push", push_route, methods=["POST"])]),
            gate=gate,
            get_committer=lambda: None,
        )
    )
    thread, codes = _call_in_thread(client, "POST", "/push")
    thread.join(30)

    assert codes == [200]
    assert answers == ["pushed"]
    assert gate.try_acquire() is True
    gate.release()


# Who commits the changes of a request.

REVIEWER_ROUTE = ("POST", "/actions/comments/add")
AUTHOR_ROUTE = ("POST", "/actions/project_index/rename_folder")


class _WithPrincipal:
    """The role that the middleware of the principal sets, in a test."""

    def __init__(self, app: Any, role: Optional[str]) -> None:
        self._app = app
        self._role = role

    async def __call__(
        self, scope: Dict[str, Any], receive: Any, send: Any
    ) -> None:
        if self._role is not None:
            scope.setdefault("state", {})["principal"] = Principal(
                user="jdupont", role=self._role
            )
        await self._app(scope, receive, send)


def _create_routes(root: Path) -> List[Route]:
    def write(_: Request) -> Response:
        (root / "written.sdoc").write_text("[DOCUMENT]\nTITLE: Written\n")
        return PlainTextResponse("written")

    return [
        Route(path_, write, methods=[method_])
        for method_, path_ in (REVIEWER_ROUTE, AUTHOR_ROUTE)
    ]


@pytest.mark.parametrize(
    ("role", "route", "is_committed"),
    [
        ("administrator", REVIEWER_ROUTE, False),
        ("reader", REVIEWER_ROUTE, False),
        ("reader", AUTHOR_ROUTE, False),
        ("reviewer", AUTHOR_ROUTE, False),
        ("author", AUTHOR_ROUTE, True),
        ("administrator", AUTHOR_ROUTE, True),
        (None, AUTHOR_ROUTE, True),
    ],
)
def test_028_the_commit_of_a_request_needs_a_route_and_a_role_of_an_author(
    tmp_path: Path,
    role: Optional[str],
    route: "tuple[str, str]",
    is_committed: bool,
) -> None:
    root = tmp_path / "project"
    _create_repository(root)
    committer = GitCommitter(
        DesktopGitService(str(root), GitAccess()), lambda: JEANNE
    )
    client = TestClient(
        _WithPrincipal(
            ProjectGateMiddleware(
                Starlette(routes=_create_routes(root)),
                gate=ProjectGate(),
                get_committer=lambda: committer,
            ),
            role,
        )
    )
    method, path = route

    answer = client.request(method, path)

    assert answer.status_code == 200
    assert int(_git(root, "rev-list", "--count", "HEAD")) == (
        2 if is_committed else 1
    )


def test_029_a_reader_of_the_application_commits_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STRICTDOC_AUTH_MODE", raising=False)
    root = tmp_path / "project"
    _create_two_documents(root)
    head = _git(root, "rev-parse", "HEAD")
    results: Dict[str, str] = {}
    for role in ("reader", "administrator"):
        config = create_desktop_project_config(
            input_path=str(root),
            port=None,
            principal_provider=_create_provider(role),
        )
        application = create_project_application(
            config, lambda: JEANNE, GitAccess()
        )

        def write(_: Request) -> Response:
            (root / "touched.sdoc").write_text("[DOCUMENT]\nTITLE: Touched\n")
            return PlainTextResponse("written")

        # A route that the table gives to a reviewer, and that succeeds.
        method, path = REVIEWER_ROUTE
        application.router.routes.insert(
            0, Route(path, write, methods=[method])
        )
        answer = TestClient(application).request(method, path)
        assert answer.status_code == 200
        results[role] = _git(root, "rev-parse", "HEAD")

    # The tree was changed by a request that succeeded, for a reader and for
    # an administrator: neither commits it, the route is not one of an author.
    assert results == {"reader": head, "administrator": head}
