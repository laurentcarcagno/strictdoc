import re
from pathlib import Path
from typing import Dict, List, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfig, ProjectConfigLoader
from strictdoc.features.roles.roles import (
    ROLES,
    resolve_role,
    role_allows,
    role_rank,
    validate_roles,
)
from strictdoc.features.roles.route_roles import (
    ROUTE_ROLES,
    check_routes_classified,
    match_route_key,
    route_keys,
)
from strictdoc.server.app import create_app

PATH_TO_THIS_TEST_FOLDER = Path(__file__).parent
PROXY = ("10.89.2.7", 40000)
ROLE_GROUPS = {
    "administrator": ["t-admins"],
    "author": ["t-authors"],
    "reviewer": ["t-reviewers"],
    "reader": ["t-readers"],
}


def _headers(group: str) -> Dict[str, str]:
    return {
        "X-Forwarded-Preferred-Username": f"user-of-{group}",
        "X-Forwarded-User": f"id-{group}",
        "X-Forwarded-Groups": f"{group},role:offline_access",
    }


def _app(root: Path, auth_mode: str = "proxy") -> FastAPI:
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
    return create_app(project_config=config)


def _sample_path(template: str) -> str:
    path = template.replace("{full_path:path}", "x/y")
    return re.sub(r"\{[^}]+\}", "x", path)


def _all_routes() -> List[Tuple[str, str, str]]:
    return [
        (method_, path_, role_)
        for (method_, path_), role_ in ROUTE_ROLES.items()
        if method_ != "WS"
    ]


def test_001_role_helpers():
    assert ROLES == ("reader", "reviewer", "author", "administrator")
    assert role_rank("reader") < role_rank("administrator")
    assert role_allows("author", "reviewer")
    assert role_allows("author", "author")
    assert not role_allows("reader", "author")
    assert not role_allows(None, "reader")
    mapping = {"reader": ["a", "b"], "author": ["c"]}
    assert resolve_role(["a"], mapping) == "reader"
    assert resolve_role(["a", "c"], mapping) == "author"
    assert resolve_role(["x"], mapping) is None
    assert resolve_role([], mapping) is None


def test_002_the_role_mapping_is_validated():
    assert validate_roles({"author": ["g"]}) == {"author": ["g"]}
    with pytest.raises(ValueError, match="not a role"):
        validate_roles({"boss": ["g"]})
    with pytest.raises(ValueError, match="list of names"):
        validate_roles({"author": "g"})  # type: ignore[dict-item]
    with pytest.raises(ValueError, match="both"):
        validate_roles({"author": ["g"], "reader": ["g"]})


def test_003_every_route_of_the_server_has_a_role(tmp_path):
    app = _app(tmp_path, "none")
    check_routes_classified(app.router.routes)

    @app.get("/a-new-route-that-nobody-classified")
    def _unclassified() -> str:
        return "x"  # pragma: no cover

    with pytest.raises(RuntimeError, match="a-new-route-that-nobody"):
        check_routes_classified(app.router.routes)


@pytest.mark.parametrize("role", ROLES)
def test_004_a_role_is_refused_exactly_where_the_table_says(tmp_path, role):
    client = TestClient(
        _app(tmp_path), client=PROXY, raise_server_exceptions=False
    )
    headers = _headers(ROLE_GROUPS[role][0])
    for method_, path_, required_ in _all_routes():
        if role_allows(role, required_):
            continue  # Allowed routes are checked in the next test.
        response = client.request(method_, _sample_path(path_), headers=headers)
        assert response.status_code == 403, (role, method_, path_)
        assert required_ in response.json()["detail"], (method_, path_)


def test_005_an_allowed_role_gets_through(tmp_path):
    client = TestClient(
        _app(tmp_path), client=PROXY, raise_server_exceptions=False
    )
    cheap = [
        ("GET", "/input/document.html", "reader"),
        ("GET", "/whoami", "reader"),
        ("GET", "/search", "reader"),
        ("POST", "/actions/document/update_requirement", "author"),
        ("DELETE", "/actions/table/delete_node", "author"),
        ("POST", "/actions/project_index/save_project_title", "administrator"),
    ]
    for role in ROLES:
        headers = _headers(ROLE_GROUPS[role][0])
        for method_, path_, required_ in cheap:
            status = client.request(method_, path_, headers=headers).status_code
            if role_allows(role, required_):
                # Past the role check; a missing form field is a 422 at most.
                assert status != 403, (role, method_, path_)
            else:
                assert status == 403, (role, method_, path_)


def test_006_a_user_without_a_group_of_the_project_is_refused_everywhere(
    tmp_path,
):
    client = TestClient(
        _app(tmp_path), client=PROXY, raise_server_exceptions=False
    )
    headers = _headers("some-other-group")
    for path in ("/", "/whoami", "/input/document.html", "/_static/base.css"):
        response = client.get(path, headers=headers)
        assert response.status_code == 403, path
        assert "not a member" in response.json()["detail"]


def test_007_a_browser_gets_a_page_and_a_script_gets_json(tmp_path):
    client = TestClient(_app(tmp_path), client=PROXY)
    headers = _headers("t-readers")
    page = client.get(
        "/actions/document/edit_grammar",
        headers={**headers, "Accept": "text/html,application/xhtml+xml"},
    )
    assert page.status_code == 403
    assert page.headers["content-type"].startswith("text/html")
    assert "administrator" in page.text
    script = client.get("/actions/document/edit_grammar", headers=headers)
    assert script.headers["content-type"] == "application/json"


def test_008_a_websocket_needs_a_role(tmp_path):
    client = TestClient(_app(tmp_path), client=PROXY)
    with client.websocket_connect("/ws/1", headers=_headers("t-readers")):
        pass
    with pytest.raises(WebSocketDisconnect) as refused:
        with client.websocket_connect("/ws/1", headers=_headers("nobody")):
            pass  # pragma: no cover
    assert refused.value.code == 4403


def test_009_whoami_tells_the_role(tmp_path):
    client = TestClient(_app(tmp_path), client=PROXY)
    body = client.get("/whoami", headers=_headers("t-reviewers")).json()
    assert body["role"] == "reviewer"
    assert body["user"] == "user-of-t-reviewers"
    anonymous = TestClient(_app(tmp_path / "none", "none")).get("/whoami")
    assert anonymous.json()["role"] == "administrator"


def test_010_behind_the_proxy_the_route_documentation_is_off(tmp_path):
    client = TestClient(
        _app(tmp_path), client=PROXY, raise_server_exceptions=False
    )
    response = client.get("/openapi.json", headers=_headers("t-admins"))
    assert "openapi" not in response.text[:200].lower() or (
        response.status_code != 200
    )
    open_app = TestClient(_app(tmp_path / "none", "none"))
    assert open_app.get("/openapi.json").status_code == 200


def test_011_none_mode_refuses_nothing(tmp_path):
    client = TestClient(_app(tmp_path, "none"), raise_server_exceptions=False)
    for method_, path_, _required in _all_routes()[:10]:
        status = client.request(method_, _sample_path(path_)).status_code
        assert status != 403, (method_, path_)


def test_012_the_table_finds_each_route_of_the_application(tmp_path):
    app = _app(tmp_path, "none")
    for method_, path_ in route_keys(app.router.routes):
        if method_ == "WS":
            continue
        assert match_route_key(method_, _sample_path(path_)) == (
            method_,
            path_,
        ), (method_, path_)
    assert match_route_key("WS", "/ws/1") == ("WS", "/ws/{client_id}")
    assert match_route_key("GET", "/does/not/exist.html") == (
        "GET",
        "/{full_path:path}",
    )
