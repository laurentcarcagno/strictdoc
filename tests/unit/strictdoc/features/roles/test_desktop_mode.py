"""
@relation(SDOC-SRS-1236, scope=file)
"""

from pathlib import Path
from typing import Any, Optional

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocket, WebSocketDisconnect

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfig, ProjectConfigLoader
from strictdoc.features.roles.middleware import PrincipalMiddleware
from strictdoc.features.roles.principal import CURRENT_ROLE, Principal
from strictdoc.helpers.exception import StrictDocException


class Provider:
    """The function that the desktop application gives to the server."""

    def __init__(self, principal: Optional[Principal]) -> None:
        self.principal: Optional[Principal] = principal
        self.call_count: int = 0

    def __call__(self) -> Optional[Principal]:
        self.call_count += 1
        return self.principal


def _create_principal(role: str = "author") -> Principal:
    return Principal(
        user="jdupont",
        subject="jdupont",
        email="jdupont@example.org",
        role=role,
    )


async def _whoami(request: Request) -> JSONResponse:
    principal: Principal = request.scope["state"]["principal"]
    return JSONResponse(
        {
            "user": principal.user,
            "role": principal.role,
            "current_role": CURRENT_ROLE.get(),
        }
    )


async def _socket(websocket: WebSocket) -> None:
    await websocket.accept()
    principal: Principal = websocket.scope["state"]["principal"]
    await websocket.send_json(
        {"user": principal.user, "role": CURRENT_ROLE.get()}
    )
    await websocket.close()


def _create_client(provider: Optional[Provider]) -> TestClient:
    application = Starlette(
        routes=[Route("/whoami", _whoami), WebSocketRoute("/ws", _socket)]
    )
    application.add_middleware(
        PrincipalMiddleware,
        auth_mode="desktop",
        principal_provider=provider,
    )
    return TestClient(application)


def test_001_the_desktop_mode_needs_a_function_that_gives_the_principal() -> (
    None
):
    async def application(scope: Any, receive: Any, send: Any) -> None:
        del scope, receive, send
        raise AssertionError("Not called.")

    with pytest.raises(ValueError, match="needs a function"):
        PrincipalMiddleware(application, auth_mode="desktop")


def test_002_the_principal_of_the_function_reaches_the_route() -> None:
    provider = Provider(_create_principal("reader"))
    client = _create_client(provider)

    response = client.get("/whoami")

    assert response.status_code == 200
    assert response.json() == {
        "user": "jdupont",
        "role": "reader",
        "current_role": "reader",
    }
    # The function is called at each request: a change of role is seen.
    provider.principal = _create_principal("author")
    assert client.get("/whoami").json()["role"] == "author"
    assert provider.call_count == 2


def test_003_without_a_principal_the_request_is_refused() -> None:
    provider = Provider(None)
    client = _create_client(provider)

    response = client.get("/whoami")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}


def test_004_the_websocket_gets_the_principal_too() -> None:
    provider = Provider(_create_principal("reviewer"))
    client = _create_client(provider)

    with client.websocket_connect("/ws") as websocket:
        assert websocket.receive_json() == {
            "user": "jdupont",
            "role": "reviewer",
        }

    provider.principal = None
    with pytest.raises(WebSocketDisconnect) as refused:
        with client.websocket_connect("/ws"):
            pass  # pragma: no cover
    assert refused.value.code == 4401


def test_005_the_other_modes_do_not_call_the_function() -> None:
    provider = Provider(_create_principal())
    application = Starlette(routes=[Route("/whoami", _whoami)])
    application.add_middleware(
        PrincipalMiddleware, auth_mode="none", principal_provider=provider
    )

    response = TestClient(application).get("/whoami")

    assert response.json()["user"] == "anonymous"
    assert provider.call_count == 0


def _load_config(root: Path) -> ProjectConfig:
    input_path = root / "input"
    input_path.mkdir(parents=True, exist_ok=True)
    return ProjectConfigLoader.load_using_server_config(
        ServerCommandConfig(
            debug=False,
            command="server",
            input_path=str(input_path),
            output_path=str(root / "output"),
            config=None,
            reload=False,
            host="127.0.0.1",
            port=8001,
        )
    )


def test_006_no_variable_and_no_file_can_start_a_server_in_desktop_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STRICTDOC_AUTH_MODE", "desktop")

    with pytest.raises(StrictDocException, match="belongs to the desktop"):
        _load_config(tmp_path)


def test_007_the_desktop_application_enables_the_mode_with_its_function(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("STRICTDOC_AUTH_MODE", raising=False)
    config = _load_config(tmp_path)
    assert config.auth_mode == "none"
    assert config.principal_provider is None
    provider = Provider(_create_principal())

    config.enable_desktop_mode(provider)

    assert config.auth_mode == "desktop"
    assert config.principal_provider is provider
