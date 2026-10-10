import asyncio
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfig, ProjectConfigLoader
from strictdoc.features.roles.middleware import PrincipalMiddleware
from strictdoc.features.roles.principal import Principal
from strictdoc.helpers.exception import StrictDocException
from strictdoc.server.app import create_app

PATH_TO_THIS_TEST_FOLDER = Path(__file__).parent
PROXY_NETWORK = "10.89.2.0/24"
PROXY_ADDRESS = ("10.89.2.7", 40000)
OUTSIDE_ADDRESS = ("192.168.1.50", 40000)
IDENTITY = {
    "X-Forwarded-User": "002b056a-a9ca-4369-828f-13abe69ae6c9",
    "X-Forwarded-Preferred-Username": "laurent.carcagno",
    "X-Forwarded-Email": "laurent.carcagno@hemeria-group.com",
    "X-Forwarded-Groups": "strictdoc-authors,role:offline_access",
}


def _project_config(
    root: Path, auth_mode: str = "none", trusted: Tuple[str, ...] = ()
) -> ProjectConfig:
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
    project_config = ProjectConfigLoader.load_using_server_config(server_config)
    project_config.auth_mode = auth_mode
    project_config.trusted_proxies = list(trusted)
    return project_config


def _client(
    root: Path,
    auth_mode: str = "none",
    peer: Tuple[str, int] = PROXY_ADDRESS,
) -> TestClient:
    config = _project_config(root, auth_mode, (PROXY_NETWORK,))
    return TestClient(create_app(project_config=config), client=peer)


def test_001_none_mode_gives_everybody_the_anonymous_principal(tmp_path):
    client = _client(tmp_path)
    body = client.get("/whoami").json()
    assert body["user"] == "anonymous"
    assert body["authenticated"] is False
    assert body["auth_mode"] == "none"
    # Headers are ignored in this mode.
    forged = client.get("/whoami", headers=IDENTITY).json()
    assert forged["user"] == "anonymous"
    assert client.get("/input/document.html").status_code == 200


def test_002_proxy_mode_reads_the_identity_from_a_trusted_proxy(tmp_path):
    client = _client(tmp_path, "proxy")
    body = client.get("/whoami", headers=IDENTITY).json()
    assert body == {
        "user": "laurent.carcagno",
        "subject": "002b056a-a9ca-4369-828f-13abe69ae6c9",
        "email": "laurent.carcagno@hemeria-group.com",
        "groups": ["strictdoc-authors"],
        "authenticated": True,
        "auth_mode": "proxy",
    }
    page = client.get("/input/document.html", headers=IDENTITY)
    assert page.status_code == 200
    assert "The system shall start." in page.text


def test_003_proxy_mode_refuses_a_request_without_identity(tmp_path):
    client = _client(tmp_path, "proxy")
    for path in ("/whoami", "/", "/input/document.html", "/_static/base.css"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.json() == {"detail": "Authentication required."}
    assert (
        client.post("/actions/document/update_requirement").status_code == 401
    )


def test_004_proxy_mode_refuses_forged_headers_from_outside_the_proxy(
    tmp_path,
):
    client = _client(tmp_path, "proxy", peer=OUTSIDE_ADDRESS)
    for path in ("/whoami", "/input/document.html"):
        assert client.get(path, headers=IDENTITY).status_code == 401, path


def test_005_proxy_mode_ignores_the_auth_request_headers(tmp_path):
    client = _client(tmp_path, "proxy")
    only_forged = {
        "X-Auth-Request-User": "attacker",
        "X-Auth-Request-Groups": "strictdoc-admins",
    }
    assert client.get("/whoami", headers=only_forged).status_code == 401
    mixed = {**IDENTITY, **only_forged}
    assert client.get("/whoami", headers=mixed).json()["user"] == (
        "laurent.carcagno"
    )


def test_006_proxy_mode_closes_a_websocket_without_identity(tmp_path):
    client = _client(tmp_path, "proxy")
    with pytest.raises(WebSocketDisconnect) as refused:
        with client.websocket_connect("/ws/1"):
            pass  # pragma: no cover
    assert refused.value.code == 4401
    with client.websocket_connect("/ws/1", headers=IDENTITY):
        pass


def test_007_an_ipv4_address_in_ipv6_form_is_matched(tmp_path):
    client = _client(tmp_path, "proxy", peer=("::ffff:10.89.2.7", 1))
    assert client.get("/whoami", headers=IDENTITY).status_code == 200


def test_008_the_middleware_refuses_a_bad_configuration():
    async def app(_scope: Dict[str, Any], _receive: Any, _send: Any) -> None:
        pass  # pragma: no cover

    with pytest.raises(ValueError, match="auth_mode"):
        PrincipalMiddleware(app, auth_mode="open")
    with pytest.raises(ValueError, match="trusted_proxies"):
        PrincipalMiddleware(app, auth_mode="proxy")
    with pytest.raises(ValueError):
        PrincipalMiddleware(app, auth_mode="proxy", trusted_proxies=["nope"])


def test_009_the_middleware_sets_the_principal_for_the_application():
    seen: List[Principal] = []

    async def app(scope: Dict[str, Any], _receive: Any, _send: Any) -> None:
        seen.append(scope["state"]["principal"])

    middleware = PrincipalMiddleware(
        app, auth_mode="proxy", trusted_proxies=[PROXY_NETWORK]
    )
    scope = {
        "type": "http",
        "client": PROXY_ADDRESS,
        "headers": [
            (b"x-forwarded-preferred-username", b"anna"),
            (b"x-forwarded-groups", b"g1,role:r"),
        ],
    }
    asyncio.run(middleware(scope, None, None))  # type: ignore[arg-type]
    assert seen == [Principal(user="anna", groups=("g1",))]


def test_010_project_config_validates_the_authentication_options(tmp_path):
    config = _project_config(tmp_path / "a")
    config.validate_and_finalize()

    config.auth_mode = "open"
    with pytest.raises(StrictDocException, match="auth_mode"):
        config.validate_and_finalize()

    config.auth_mode = "proxy"
    config.trusted_proxies = []
    with pytest.raises(StrictDocException, match="trusted_proxies"):
        config.validate_and_finalize()

    config.trusted_proxies = ["not-a-network"]
    with pytest.raises(StrictDocException, match="not a network"):
        config.validate_and_finalize()

    config.trusted_proxies = [PROXY_NETWORK]
    config.validate_and_finalize()


def test_011_the_environment_wins_over_the_project_file(monkeypatch):
    monkeypatch.setenv("STRICTDOC_AUTH_MODE", "proxy")
    monkeypatch.setenv("STRICTDOC_TRUSTED_PROXIES", "10.89.2.0/24, 10.0.0.0/8")
    config = ProjectConfig(auth_mode="none", trusted_proxies=["1.2.3.4/32"])
    assert config.auth_mode == "proxy"
    assert config.trusted_proxies == ["10.89.2.0/24", "10.0.0.0/8"]

    monkeypatch.delenv("STRICTDOC_AUTH_MODE")
    monkeypatch.delenv("STRICTDOC_TRUSTED_PROXIES")
    config = ProjectConfig(auth_mode="proxy", trusted_proxies=["1.2.3.4/32"])
    assert config.auth_mode == "proxy"
    assert config.trusted_proxies == ["1.2.3.4/32"]
