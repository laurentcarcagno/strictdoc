import json
import os
from pathlib import Path
from typing import Dict

from fastapi.testclient import TestClient

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfig, ProjectConfigLoader
from strictdoc.features.roles.audit import AuditLog
from strictdoc.server.app import create_app

PATH_TO_THIS_TEST_FOLDER = Path(__file__).parent
PROXY = ("10.89.2.7", 40000)
ROLE_GROUPS = {
    "administrator": ["t-admins"],
    "author": ["t-authors"],
    "reviewer": ["t-reviewers"],
    "reader": ["t-readers"],
}


def _headers(group: str, user: str = "") -> Dict[str, str]:
    return {
        "X-Forwarded-Preferred-Username": user or f"user-of-{group}",
        "X-Forwarded-User": f"id-{group}",
        "X-Forwarded-Groups": group,
    }


def _setup(root: Path, auth_mode: str = "proxy"):
    input_path = root / "input"
    input_path.mkdir(parents=True)
    (input_path / "document.sdoc").write_text(
        (PATH_TO_THIS_TEST_FOLDER / "document.sdoc").read_text(encoding="utf8"),
        encoding="utf8",
    )
    server_config = ServerCommandConfig(
        debug=False,
        command="server",
        input_path=str(input_path),
        output_path=str(root / "output"),
        config=None,
        reload=False,
        host="127.0.0.1",
        port=8001,
    )
    config: ProjectConfig = ProjectConfigLoader.load_using_server_config(
        server_config
    )
    config.auth_mode = auth_mode
    config.trusted_proxies = ["10.89.2.0/24"]
    config.roles = ROLE_GROUPS
    client = TestClient(
        create_app(project_config=config),
        client=PROXY,
        raise_server_exceptions=False,
    )
    return client, root / "output" / "audit.jsonl"


def _lines(path: Path):
    if not path.exists():
        return []
    return [json.loads(line_) for line_ in path.read_text().splitlines()]


def test_001_the_audit_log_is_a_rotated_json_lines_file(tmp_path):
    log = AuditLog(str(tmp_path / "audit.jsonl"), max_bytes=300, backups=2)
    for index_ in range(12):
        log.record({"n": index_, "text": "é" * 20})
    newest = log.tail(3)
    assert [entry_["n"] for entry_ in newest] == [11, 10, 9]
    assert os.path.exists(tmp_path / "audit.jsonl.1")
    assert os.path.exists(tmp_path / "audit.jsonl.2")
    assert not os.path.exists(tmp_path / "audit.jsonl.3")
    (tmp_path / "audit.jsonl").open("a").write("not json\n")
    assert log.tail(1) == [] or isinstance(log.tail(1)[0], dict)


def test_002_a_change_is_logged_with_the_user_and_the_status(tmp_path):
    client, path = _setup(tmp_path)
    response = client.delete(
        "/actions/table/delete_node?node_mid=abc123",
        headers=_headers("t-authors", "anna"),
    )
    (entry,) = _lines(path)
    assert entry["user"] == "anna"
    assert entry["role"] == "author"
    assert entry["method"] == "DELETE"
    assert entry["path"] == "/actions/table/delete_node"
    assert entry["mid"] == "abc123"
    assert entry["status"] == response.status_code
    assert entry["time"].endswith("+00:00")


def test_003_a_refused_attempt_is_logged_as_403(tmp_path):
    client, path = _setup(tmp_path)
    response = client.post(
        "/actions/document/update_requirement?requirement_mid=m1",
        headers=_headers("t-readers", "ruth"),
    )
    assert response.status_code == 403
    (entry,) = _lines(path)
    assert (entry["user"], entry["role"], entry["status"]) == (
        "ruth",
        "reader",
        403,
    )
    assert entry["mid"] == "m1"


def test_004_reading_is_not_logged_but_the_nestor_export_is(tmp_path):
    client, path = _setup(tmp_path)
    client.get("/input/document.html", headers=_headers("t-readers"))
    client.get("/whoami", headers=_headers("t-readers"))
    assert _lines(path) == []
    client.get("/__nestor", headers=_headers("t-readers"))
    (entry,) = _lines(path)
    assert (entry["path"], entry["status"]) == ("/__nestor", 403)


def test_005_no_audit_file_without_a_login_proxy(tmp_path):
    client, path = _setup(tmp_path, "none")
    client.delete("/actions/table/delete_node?node_mid=x")
    assert not path.exists()
    page = client.get("/audit")
    assert page.status_code == 200
    assert "only behind a login proxy" in page.text


def test_006_the_audit_screen_is_for_administrators(tmp_path):
    client, _ = _setup(tmp_path)
    client.delete(
        "/actions/table/delete_node?node_mid=<b>x</b>",
        headers=_headers("t-authors", "anna"),
    )
    refused = client.get("/audit", headers=_headers("t-authors"))
    assert refused.status_code == 403
    page = client.get("/audit", headers=_headers("t-admins"))
    assert page.status_code == 200
    assert "anna" in page.text and "delete_node" in page.text
    assert "<b>x</b>" not in page.text  # escaped


def test_007_pages_load_the_role_gating_only_behind_a_proxy(tmp_path):
    client, _ = _setup(tmp_path)
    page = client.get("/input/document.html", headers=_headers("t-readers"))
    assert "roles/role_gating.js" in page.text
    assert "roles/role_gating.css" in page.text
    script = client.get(
        "/_static/roles/role_gating.js", headers=_headers("t-readers")
    )
    assert script.status_code == 200 and "/whoami" in script.text
    style = client.get(
        "/_static/roles/role_gating.css", headers=_headers("t-readers")
    )
    assert 'html[data-role="reader"] [data-testid^="node-edit-action"]' in (
        style.text
    )

    open_client, _ = _setup(tmp_path / "open", "none")
    open_page = open_client.get("/input/document.html")
    assert "role_gating" not in open_page.text
