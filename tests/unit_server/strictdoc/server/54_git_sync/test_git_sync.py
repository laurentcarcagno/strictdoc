import json
import subprocess
from pathlib import Path
from typing import Any, Tuple

from fastapi.testclient import TestClient

from strictdoc.core.project_config import ProjectFeature
from strictdoc.features.git_config.config import GitConfig
from strictdoc.server.app import create_app
from tests.support.llm_fixture import (
    ADMIN,
    AUTHOR,
    PROXY,
    READER,
    ROLE_GROUPS,
    make_config,
)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _project(tmp_path: Path) -> Tuple[Any, Path, Path, Path]:
    """A project in a git repository with an origin, and a second clone."""
    root = tmp_path / "project"
    root.mkdir()
    config = make_config(root, None)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(root, "remote", "add", "origin", str(origin))
    _git(root, "push", "-q", "-u", "origin", "main")
    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", str(origin), str(other))
    config.project_features.append(ProjectFeature.GIT)
    config.git = GitConfig(push_on_tag=False)
    config.auth_mode = "proxy"
    config.trusted_proxies = ["10.89.2.0/24"]
    config.roles = ROLE_GROUPS
    config.audit_dir = str(tmp_path / "audit")
    client = TestClient(
        create_app(project_config=config),
        client=PROXY,
        raise_server_exceptions=False,
    )
    return client, root, origin, other


def _edit(root: Path, old: str, new: str, message: str) -> None:
    path = root / "input" / "flight.sdoc"
    path.write_text(
        path.read_text(encoding="utf8").replace(old, new), encoding="utf8"
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def test_001_the_menu_has_synchronize_and_the_page_opens(
    tmp_path: Path,
) -> None:
    client, _, _, _ = _project(tmp_path)
    tree = client.get("/fragments/project_tree", headers=ADMIN).text
    assert "tree-sync-action" in tree and "/actions/git/sync_dialog" in tree
    assert "tree-git-action" in tree and "/actions/git/overview" in tree
    # The dialogs are Turbo streams for the modal of the page.
    dialog = client.get("/actions/git/sync_dialog", headers=READER)
    assert dialog.status_code == 200
    assert dialog.headers["content-type"].startswith(
        "text/vnd.turbo-stream.html"
    )
    assert 'target="modal"' in dialog.text and "sync-dialog" in dialog.text
    # The reader reads the dialog; the button that synchronizes is for the
    # administrator.
    assert "form-submit-action" not in dialog.text
    admin = client.get("/actions/git/sync_dialog", headers=ADMIN)
    assert "form-submit-action" in admin.text
    overview = client.get("/actions/git/overview", headers=READER)
    assert overview.status_code == 200 and "git-repositories" in overview.text


def test_002_only_an_administrator_synchronizes(tmp_path: Path) -> None:
    client, _, origin, _ = _project(tmp_path)
    for headers in (READER, AUTHOR):
        for method, path in (
            ("POST", "/actions/git/sync"),
            ("POST", "/actions/git/sync/abort"),
            ("POST", "/actions/git/sync/resolve"),
            ("GET", "/actions/git/sync_conflicts"),
        ):
            assert (
                client.request(method, path, headers=headers).status_code == 403
            )
    assert "input" in _git(origin, "ls-tree", "main", "--name-only")


def test_003_a_synchronization_without_conflict_pushes(tmp_path: Path) -> None:
    client, root, origin, other = _project(tmp_path)
    _edit(other, "at most 32 MB", "at most 16 MB", "server")
    _git(other, "push", "-q")
    result = client.post("/actions/git/sync", headers=ADMIN)
    assert result.status_code == 200
    assert "16 MB" in (root / "input" / "flight.sdoc").read_text(
        encoding="utf8"
    )
    assert "sync-result" in result.text


def test_004_a_conflict_opens_the_view_and_locks_the_project(
    tmp_path: Path,
) -> None:
    client, root, origin, other = _project(tmp_path)
    _edit(other, "at most 32 MB", "at most 16 MB", "server")
    _git(other, "push", "-q")
    _edit(root, "at most 32 MB", "at most 64 MB", "local")

    result = client.post("/actions/git/sync", headers=ADMIN)
    # The conflict view opens at once.
    assert result.status_code == 200
    assert (
        'context="merge"' in result.text and "sync-row-conflict" in result.text
    )
    # The document on disk is the local one while the conflict waits.
    assert "64 MB" in (root / "input" / "flight.sdoc").read_text(
        encoding="utf8"
    )
    assert "<<<<<<<" not in (root / "input" / "flight.sdoc").read_text(
        encoding="utf8"
    )

    view = client.get(
        "/actions/git/sync_conflicts?file=input/flight.sdoc", headers=ADMIN
    )
    assert view.status_code == 200
    assert 'context="merge"' in view.text
    assert "sync-row-conflict" in view.text
    assert "16 MB" in view.text and "64 MB" in view.text
    assert "sync-keep-server" in view.text

    # Nothing else is saved during the merge.
    locked = client.post(
        "/actions/project_index/create_folder",
        data={"folder_path": "x"},
        headers=ADMIN,
    )
    assert locked.status_code == 423

    status = client.get("/actions/git/sync_dialog", headers=ADMIN)
    assert "input/flight.sdoc" in status.text and "sync-abort" in status.text


def test_005_resolving_the_conflict_commits_the_merge_and_pushes(
    tmp_path: Path,
) -> None:
    client, root, origin, other = _project(tmp_path)
    _edit(other, "at most 32 MB", "at most 16 MB", "server")
    _git(other, "push", "-q")
    _edit(root, "at most 32 MB", "at most 64 MB", "local")
    client.post("/actions/git/sync", headers=ADMIN)
    view = client.get(
        "/actions/git/sync_conflicts?file=input/flight.sdoc", headers=ADMIN
    ).text
    data = json.loads(view.split('id="gs-data">')[1].split("</script>")[0])
    [region] = data.keys()

    bad = client.post(
        "/actions/git/sync/resolve",
        data={"file": "input/flight.sdoc", "texts": "{}"},
        headers=ADMIN,
    )
    assert bad.status_code == 422

    done = client.post(
        "/actions/git/sync/resolve",
        data={
            "file": "input/flight.sdoc",
            "texts": json.dumps({region: data[region]["server"]}),
        },
        headers=ADMIN,
    )
    assert done.status_code == 200, done.text
    assert done.json()["next"].startswith(
        "/actions/git/sync_dialog?merged=1&pushed=1"
    )
    merged = _git(origin, "show", "main:input/flight.sdoc")
    assert "16 MB" in merged and "64 MB" not in merged
    assert _git(root, "rev-list", "--merges", "--count", "HEAD") == "1"
    # The project can be changed again.
    ok = client.post(
        "/actions/project_index/create_folder",
        data={"folder_path": "x"},
        headers=ADMIN,
    )
    assert ok.status_code != 423


def test_006_abandoning_goes_back_to_the_local_state(tmp_path: Path) -> None:
    client, root, _, other = _project(tmp_path)
    _edit(other, "at most 32 MB", "at most 16 MB", "server")
    _git(other, "push", "-q")
    _edit(root, "at most 32 MB", "at most 64 MB", "local")
    client.post("/actions/git/sync", headers=ADMIN)
    abandoned = client.post("/actions/git/sync/abort", headers=ADMIN)
    assert abandoned.status_code == 200 and "sync-dialog" in abandoned.text
    assert "64 MB" in (root / "input" / "flight.sdoc").read_text(
        encoding="utf8"
    )
    assert _git(root, "status", "--porcelain", "--", "input") == ""
