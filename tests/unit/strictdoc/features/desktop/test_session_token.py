"""
@relation(SDOC-SRS-1221, scope=file)
@relation(SDOC-SRS-1222, scope=file)
@relation(SDOC-SRS-1234, scope=file)
"""

import urllib.error
import urllib.request
from typing import Any, Optional

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocket, WebSocketDisconnect

from strictdoc.features.desktop.local_server import LocalServer
from strictdoc.features.desktop.session_token import (
    BOOTSTRAP_PATH,
    DesktopSessionMiddleware,
    SessionCredentials,
    get_session_cookie_name,
)
from strictdoc.features.i18n import i18n

PORT = 18080
HOST = f"127.0.0.1:{PORT}"
COOKIE_NAME = get_session_cookie_name(PORT)


def _home(request: Request) -> PlainTextResponse:  # noqa: ARG001
    return PlainTextResponse("home")


async def _edit(request: Request) -> PlainTextResponse:  # noqa: ARG001
    return PlainTextResponse("edited")


async def _socket(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_text("hello")
    await websocket.close()


@pytest.fixture(name="credentials")
def fixture_credentials() -> SessionCredentials:
    return SessionCredentials.create()


def _create_client(credentials: SessionCredentials, port: int) -> TestClient:
    application = Starlette(
        routes=[
            Route("/", _home),
            Route("/edit", _edit, methods=["POST"]),
            WebSocketRoute("/ws", _socket),
        ]
    )
    application.add_middleware(
        DesktopSessionMiddleware,
        credentials=credentials,
        port=port,
        allowed_hosts=frozenset({f"127.0.0.1:{port}", f"localhost:{port}"}),
    )
    return TestClient(application, base_url=f"http://127.0.0.1:{port}")


@pytest.fixture(name="client")
def fixture_client(credentials: SessionCredentials) -> TestClient:
    return _create_client(credentials, PORT)


def _bootstrap_path(credentials: SessionCredentials) -> str:
    return f"{BOOTSTRAP_PATH}?code={credentials.bootstrap_code}"


def test_001_token_and_code_are_distinct_and_random() -> None:
    first = SessionCredentials.create()
    second = SessionCredentials.create()

    assert first.token != first.bootstrap_code
    assert first.token != second.token
    assert first.bootstrap_code != second.bootstrap_code
    assert len(first.token) >= 43


def test_002_request_without_cookie_is_refused(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 403
    assert response.text == "Forbidden\n"

    assert client.post("/edit").status_code == 403


def test_003_request_with_wrong_cookie_is_refused(
    client: TestClient, credentials: SessionCredentials
) -> None:
    client.cookies.set(COOKIE_NAME, "wrong")
    assert client.get("/").status_code == 403

    # The bootstrap code is not the token.
    client.cookies.set(COOKIE_NAME, credentials.bootstrap_code)
    assert client.get("/").status_code == 403


def test_004_wrong_host_is_refused_even_with_the_cookie(
    client: TestClient, credentials: SessionCredentials
) -> None:
    response = client.get(_bootstrap_path(credentials), follow_redirects=False)
    assert response.status_code == 303
    assert client.get("/").status_code == 200

    for host_ in ("evil.example", f"evil.example:{PORT}", "127.0.0.1:1234"):
        assert client.get("/", headers={"host": host_}).status_code == 403


def test_005_localhost_is_allowed(
    client: TestClient, credentials: SessionCredentials
) -> None:
    response = client.get(
        _bootstrap_path(credentials),
        headers={"host": f"localhost:{PORT}"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_006_bootstrap_code_works_once(
    client: TestClient, credentials: SessionCredentials
) -> None:
    first = client.get(_bootstrap_path(credentials), follow_redirects=False)
    assert first.status_code == 303

    second = client.get(_bootstrap_path(credentials), follow_redirects=False)
    assert second.status_code == 403


def test_007_wrong_bootstrap_code_is_refused_and_keeps_the_right_one(
    client: TestClient, credentials: SessionCredentials
) -> None:
    wrong = client.get(f"{BOOTSTRAP_PATH}?code=wrong", follow_redirects=False)
    assert wrong.status_code == 403
    assert "set-cookie" not in wrong.headers

    assert client.get(BOOTSTRAP_PATH, follow_redirects=False).status_code == 403
    assert (
        client.post(
            _bootstrap_path(credentials), follow_redirects=False
        ).status_code
        == 403
    )

    right = client.get(_bootstrap_path(credentials), follow_redirects=False)
    assert right.status_code == 303


def test_008_bootstrap_then_pages_are_served(
    client: TestClient, credentials: SessionCredentials
) -> None:
    response = client.get(_bootstrap_path(credentials))

    assert response.status_code == 200
    assert response.text == "home"
    assert client.post("/edit").status_code == 200


def test_009_cookie_attributes(
    client: TestClient, credentials: SessionCredentials
) -> None:
    response = client.get(_bootstrap_path(credentials), follow_redirects=False)

    assert response.headers["location"] == "/"
    set_cookie = response.headers["set-cookie"]
    attributes = [part_.strip() for part_ in set_cookie.split(";")]
    assert attributes[0] == f"{COOKIE_NAME}={credentials.token}"
    assert "HttpOnly" in attributes
    assert "SameSite=Strict" in attributes
    assert "Path=/" in attributes
    assert not any(
        attribute_.lower().startswith(("max-age", "expires"))
        for attribute_ in attributes
    )


def test_010_token_is_never_in_a_response_body(
    client: TestClient, credentials: SessionCredentials
) -> None:
    refused = client.get("/")
    assert credentials.token not in refused.text

    client.get(_bootstrap_path(credentials))
    assert credentials.token not in client.get("/").text


def test_011_websocket_needs_the_cookie(
    client: TestClient, credentials: SessionCredentials
) -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws"):
            pass

    # The test client sends neither its cookies nor its Host to a WebSocket.
    with client.websocket_connect(
        "/ws",
        headers={
            "host": HOST,
            "origin": f"http://{HOST}",
            "cookie": f"{COOKIE_NAME}={credentials.token}",
        },
    ) as websocket:
        assert websocket.receive_text() == "hello"

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/ws",
            headers={
                "host": "evil.example",
                "origin": f"http://{HOST}",
                "cookie": f"{COOKIE_NAME}={credentials.token}",
            },
        ):
            pass


@pytest.mark.parametrize(
    "origin",
    [
        # A page of the neighbour port of the same address.
        f"http://127.0.0.1:{PORT + 1}",
        f"http://localhost:{PORT + 1}",
        "http://evil.example",
        "https://127.0.0.1:" + str(PORT),
        "null",
        "",
    ],
)
def test_011b_a_websocket_of_another_origin_is_refused(
    client: TestClient, credentials: SessionCredentials, origin: str
) -> None:
    with pytest.raises(WebSocketDisconnect) as refused:
        with client.websocket_connect(
            "/ws",
            headers={
                "host": HOST,
                "origin": origin,
                "cookie": f"{COOKIE_NAME}={credentials.token}",
            },
        ):
            pass

    assert refused.value.code == 1008


def test_011c_a_websocket_without_origin_is_refused(
    client: TestClient, credentials: SessionCredentials
) -> None:
    with pytest.raises(WebSocketDisconnect) as refused:
        with client.websocket_connect(
            "/ws",
            headers={
                "host": HOST,
                "cookie": f"{COOKIE_NAME}={credentials.token}",
            },
        ):
            pass

    assert refused.value.code == 1008


def test_011d_a_websocket_of_the_server_is_accepted(
    client: TestClient, credentials: SessionCredentials
) -> None:
    for host_ in (f"127.0.0.1:{PORT}", f"localhost:{PORT}"):
        with client.websocket_connect(
            "/ws",
            headers={
                "host": host_,
                "origin": f"http://{host_}",
                "cookie": f"{COOKIE_NAME}={credentials.token}",
            },
        ) as websocket:
            assert websocket.receive_text() == "hello"


def test_011e_the_http_requests_keep_their_rule_on_the_origin(
    client: TestClient, credentials: SessionCredentials
) -> None:
    client.get(_bootstrap_path(credentials))

    # No Origin: a program, not a page of a browser. It is accepted still.
    assert client.post("/edit").status_code == 200
    assert (
        client.get("/", headers={"origin": "http://evil.example"}).status_code
        == 200
    )
    assert (
        client.post(
            "/edit", headers={"origin": "http://evil.example"}
        ).status_code
        == 403
    )


def test_011f_a_new_bootstrap_code_gives_the_same_cookie_again(
    client: TestClient, credentials: SessionCredentials
) -> None:
    first_code = credentials.bootstrap_code
    client.get(_bootstrap_path(credentials), follow_redirects=False)
    assert credentials.is_bootstrap_code_used is True

    new_code = credentials.renew_bootstrap_code()

    assert new_code != first_code
    assert credentials.token not in (first_code, new_code)
    # The old code is void, and the new one works once.
    assert credentials.consume_bootstrap_code(first_code) is False
    assert credentials.consume_bootstrap_code(new_code) is True
    assert credentials.consume_bootstrap_code(new_code) is False
    assert credentials.is_bootstrap_code_used is True


def test_012_each_server_accepts_only_the_cookie_of_its_port() -> None:
    # The browser keeps one cookie jar for all the ports of 127.0.0.1 and sends
    # every cookie of the jar to every server.
    credentials_a = SessionCredentials.create()
    credentials_b = SessionCredentials.create()
    client_a = _create_client(credentials_a, PORT)
    client_b = _create_client(credentials_b, PORT + 1)
    cookie_a = f"{get_session_cookie_name(PORT)}={credentials_a.token}"
    cookie_b = f"{get_session_cookie_name(PORT + 1)}={credentials_b.token}"
    assert (
        cookie_a.split("=", maxsplit=1)[0] != cookie_b.split("=", maxsplit=1)[0]
    )

    both_cookies = {"cookie": f"{cookie_a}; {cookie_b}"}
    assert client_a.get("/", headers=both_cookies).status_code == 200
    assert client_b.get("/", headers=both_cookies).status_code == 200

    # Only the cookie of the other server.
    assert client_a.get("/", headers={"cookie": cookie_b}).status_code == 403
    assert client_b.get("/", headers={"cookie": cookie_a}).status_code == 403
    # The cookie of the other server with the name of this server.
    name_a = get_session_cookie_name(PORT)
    stolen = {"cookie": f"{name_a}={credentials_b.token}"}
    assert client_a.get("/", headers=stolen).status_code == 403


def test_013_cookie_name_holds_the_port(
    client: TestClient, credentials: SessionCredentials
) -> None:
    response = client.get(_bootstrap_path(credentials), follow_redirects=False)

    assert response.headers["set-cookie"].startswith(
        f"strictdoc_desktop_session_{PORT}="
    )


def _create_public_path_client(
    credentials: SessionCredentials, *, is_accepted: bool
) -> TestClient:
    application = Starlette(
        routes=[
            Route("/", _home),
            Route("/public", _home),
        ]
    )
    application.add_middleware(
        DesktopSessionMiddleware,
        credentials=credentials,
        port=PORT,
        allowed_hosts=frozenset({HOST}),
        public_paths={"/public": lambda _: is_accepted},
    )
    return TestClient(application, base_url=f"http://{HOST}")


def test_014_a_public_path_that_the_checker_accepts_needs_no_cookie(
    credentials: SessionCredentials,
) -> None:
    client = _create_public_path_client(credentials, is_accepted=True)

    assert client.get("/public").text == "home"
    # Only that path, and only a GET request.
    assert client.get("/").status_code == 403
    # A POST request is not a callback: the page of the refusal answers.
    assert client.post("/public").status_code == 403


def test_015_a_public_path_that_the_checker_refuses_shows_a_page(
    credentials: SessionCredentials,
) -> None:
    client = _create_public_path_client(credentials, is_accepted=False)

    response = client.get("/public?state=abc&code=secret-value")

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"
    assert "The sign-in has expired or is no longer valid." in response.text
    assert 'href="/"' in response.text
    # Nothing of the request is in the page.
    assert "abc" not in response.text
    assert "secret-value" not in response.text
    # A POST request gets the same page: no data goes with it either.
    assert client.post("/public").status_code == 403


def test_016_the_other_paths_keep_the_plain_refusal(
    credentials: SessionCredentials,
) -> None:
    client = _create_public_path_client(credentials, is_accepted=False)

    response = client.get("/")

    assert response.status_code == 403
    assert response.text == "Forbidden\n"
    assert response.headers["content-type"].startswith("text/plain")


def test_017_the_page_of_the_public_path_follows_the_language(
    credentials: SessionCredentials,
) -> None:
    client = _create_public_path_client(credentials, is_accepted=False)
    i18n.set_language("fr")
    try:
        response = client.get("/public")
    finally:
        i18n.set_language(i18n.DEFAULT_LANGUAGE)

    assert "La connexion a expiré ou n&#x27;est plus valide." in response.text
    assert "Retour à l&#x27;accueil" in response.text
    assert '<html lang="fr">' in response.text


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *arguments: Any, **keywords: Any) -> None:
        del arguments, keywords


def _get_cookie_of(url: str) -> Optional[str]:
    """Follow the URL with no redirect; the cookie that it sets, if any."""
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        answer = opener.open(url, timeout=10)
    except urllib.error.HTTPError as error_:
        answer = error_
    cookie = answer.headers.get("Set-Cookie")
    return cookie.split(";")[0] if cookie is not None else None


def test_018_a_server_gives_the_cookie_again_through_a_new_start_path() -> None:
    """
    @relation(SDOC-SRS-1234, scope=function)
    """
    server = LocalServer(
        application_factory=lambda: Starlette(routes=[Route("/", _home)])
    )
    server.start()
    try:
        server.wait_until_ready()
        first_start_url = server.start_url
        first_cookie = _get_cookie_of(first_start_url)
        assert first_cookie is not None
        assert server.is_bootstrapped is True

        restart_path = server.create_restart_path()

        assert restart_path.startswith(f"{BOOTSTRAP_PATH}?code=")
        # The start URL of the first code does not work any more.
        assert _get_cookie_of(first_start_url) is None
        assert _get_cookie_of(server.url + restart_path) == first_cookie
        # And the new code works once.
        assert _get_cookie_of(server.url + restart_path) is None
    finally:
        server.stop()
