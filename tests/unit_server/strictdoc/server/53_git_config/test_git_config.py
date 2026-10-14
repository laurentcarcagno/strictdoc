import subprocess
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from strictdoc.core.project_config import ProjectFeature
from strictdoc.features.git_config.config import GitConfig
from strictdoc.server.app import create_app
from tests.support.llm_fixture import (
    ADMIN,
    AUTHOR,
    FL_2,
    PROXY,
    READER,
    ROLE_GROUPS,
    make_config,
)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _client(root: Path, feature: bool = True, git_repo: bool = True) -> Any:
    config = make_config(root, None)
    if git_repo:
        _git(root, "init", "-q", "-b", "master")
        _git(root, "config", "user.name", "i")
        _git(root, "config", "user.email", "i@e")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "init", "--allow-empty")
    if feature:
        config.project_features.append(ProjectFeature.GIT)
        config.git = GitConfig(push_on_tag=False)
    config.auth_mode = "proxy"
    config.trusted_proxies = ["10.89.2.0/24"]
    config.roles = ROLE_GROUPS
    config.audit_dir = str(root / "audit")
    return TestClient(
        create_app(project_config=config),
        client=PROXY,
        raise_server_exceptions=False,
    )


def test_001_disabled_feature_closes_the_routes(tmp_path: Path) -> None:
    client = _client(tmp_path, feature=False)
    assert client.get("/git", headers=READER).status_code == 412


def test_002_reader_sees_the_page_but_cannot_tag(tmp_path: Path) -> None:
    client = _client(tmp_path)
    page = client.get("/git", headers=READER)
    assert page.status_code == 200
    assert "git-repositories" in page.text
    denied = client.post(
        "/actions/git/tag",
        data={"repository": ".", "kind": "draft"},
        headers=READER,
    )
    assert denied.status_code == 403


def test_003_admin_tags_a_draft_then_a_major(tmp_path: Path) -> None:
    client = _client(tmp_path)
    for expected_tags in (["A1"], ["A1", "A2"]):
        response = client.post(
            "/actions/git/tag",
            data={"repository": ".", "kind": "draft"},
            headers=ADMIN,
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert _git(tmp_path, "tag").split() == expected_tags
    client.post(
        "/actions/git/tag",
        data={"repository": ".", "kind": "major"},
        headers=ADMIN,
    )
    assert "A" in _git(tmp_path, "tag").split()


def test_004_unknown_repository_and_kind_are_refused(tmp_path: Path) -> None:
    client = _client(tmp_path)
    for data in (
        {"repository": "../..", "kind": "draft"},
        {"repository": ".", "kind": "bogus"},
    ):
        response = client.post("/actions/git/tag", data=data, headers=ADMIN)
        assert response.status_code == 400


def test_005_major_without_draft_shows_the_reason(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.post(
        "/actions/git/tag",
        data={"repository": ".", "kind": "major"},
        headers=ADMIN,
    )
    assert response.status_code == 400
    assert "intermediate version" in response.text


def test_006_saving_a_node_makes_a_commit(tmp_path: Path) -> None:
    client = _client(tmp_path)
    before = _git(tmp_path, "rev-list", "--count", "HEAD")
    response = client.post(
        "/actions/table/update_node_field",
        data={"node_mid": FL_2, "field_name": "TITLE", "field_value": "Reboot"},
        headers=AUTHOR,
    )
    assert response.status_code == 200, response.text
    assert int(_git(tmp_path, "rev-list", "--count", "HEAD")) == int(before) + 1
    assert _git(tmp_path, "log", "-1", "--format=%s") == (
        "feat(doc): update requirement [FSW-2]"
    )
    # One author, whoever is signed in.
    assert _git(tmp_path, "log", "-1", "--format=%an <%ae>") == (
        "Laurent Carcagno <laurent.carcagno@hemeria-group.com>"
    )


SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"><rect width="4" height="4"/></svg>'


def test_007_uploaded_assets_join_the_next_commit(tmp_path: Path) -> None:
    client = _client(tmp_path)
    upload = client.post(
        f"/actions/document/upload_asset?requirement_mid={FL_2}&document_mid={'f' * 32}",
        files=[("uploaded_files", ("pic.svg", SVG, "image/svg+xml"))],
        headers=AUTHOR,
    )
    assert upload.status_code == 200, upload.text
    # The upload alone makes no commit.
    assert _git(tmp_path, "rev-list", "--count", "HEAD") == "1"
    pending = client.get("/git", headers=READER)
    assert "1 " in pending.text

    client.post(
        "/actions/table/update_node_field",
        data={"node_mid": FL_2, "field_name": "TITLE", "field_value": "Reboot"},
        headers=AUTHOR,
    )
    files = _git(tmp_path, "show", "--name-only", "--format=", "HEAD")
    assert f"input/_assets/{FL_2}/pic.svg" in files
    assert "input/flight.sdoc" in files


def test_008_deleting_a_node_removes_its_assets(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post(
        f"/actions/document/upload_asset?requirement_mid={FL_2}&document_mid={'f' * 32}",
        files=[("uploaded_files", ("pic.svg", SVG, "image/svg+xml"))],
        headers=AUTHOR,
    )
    client.post(
        "/actions/table/update_node_field",
        data={"node_mid": FL_2, "field_name": "TITLE", "field_value": "Reboot"},
        headers=AUTHOR,
    )
    folder = tmp_path / "input" / "_assets" / FL_2
    assert (folder / "pic.svg").exists()

    deleted = client.delete(
        "/actions/table/delete_node",
        params={
            "node_id": FL_2,
            "context_document_mid": "f" * 32,
            "confirmed": "true",
        },
        headers=AUTHOR,
    )
    assert deleted.status_code == 200, deleted.text
    assert not folder.exists()
    files = _git(tmp_path, "show", "--name-only", "--format=", "HEAD")
    assert f"input/_assets/{FL_2}/pic.svg" in files
    assert _git(tmp_path, "status", "--porcelain", "-uno") == ""


def test_009_menu_entry_only_when_activated(tmp_path: Path) -> None:
    (tmp_path / "on").mkdir()
    client = _client(tmp_path / "on")
    assert "tree-git-action" in client.get("/", headers=READER).text
    document = client.get("/UID/FSW-2", headers=READER, follow_redirects=True)
    assert "document-git-action" in document.text

    off = _client(tmp_path / "off", feature=False)
    assert "tree-git-action" not in off.get("/", headers=READER).text
