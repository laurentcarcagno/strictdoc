"""
The session token of the desktop server and the middleware that checks it.

@relation(SDOC-SRS-1221, scope=file)
@relation(SDOC-SRS-1222, scope=file)
"""

import hmac
import secrets
import threading
from typing import Callable, FrozenSet, List, Optional, Tuple
from urllib.parse import parse_qs

from starlette.types import ASGIApp, Message, Receive, Scope, Send

SESSION_COOKIE_NAME_PREFIX = "strictdoc_desktop_session"
BOOTSTRAP_PATH = "/__desktop/start"
BOOTSTRAP_CODE_PARAMETER = "code"

_TOKEN_BYTES = 32
_FORBIDDEN_BODY = b"Forbidden\n"


def get_session_cookie_name(port: int) -> str:
    """
    A cookie jar is shared by all the ports of an address. A name per port
    keeps the cookie of one desktop server from replacing the cookie of
    another, when the application keeps several servers open.
    """
    return f"{SESSION_COOKIE_NAME_PREFIX}_{port}"


class SessionCredentials:
    """
    The two secrets of one run of the desktop server.

    The session token goes to the window in a cookie. The bootstrap code is the
    only way to get that cookie and works once.
    """

    def __init__(self, *, token: str, bootstrap_code: str) -> None:
        assert token != bootstrap_code
        self.token: str = token
        self._bootstrap_code: str = bootstrap_code
        self._bootstrap_code_used: bool = False
        self._lock: threading.Lock = threading.Lock()
        # Called once, when the code is used: the window has the cookie.
        self.bootstrap_listener: Optional[Callable[[], None]] = None

    @classmethod
    def create(cls) -> "SessionCredentials":
        return cls(
            token=secrets.token_urlsafe(_TOKEN_BYTES),
            bootstrap_code=secrets.token_urlsafe(_TOKEN_BYTES),
        )

    @property
    def bootstrap_code(self) -> str:
        return self._bootstrap_code

    @property
    def is_bootstrap_code_used(self) -> bool:
        """True once a window has used the code and has the session cookie."""
        with self._lock:
            return self._bootstrap_code_used

    def is_token(self, candidate: str) -> bool:
        return hmac.compare_digest(
            candidate.encode("utf-8"), self.token.encode("utf-8")
        )

    def consume_bootstrap_code(self, candidate: str) -> bool:
        """True once for the right code, then false for every code."""
        is_right_code = hmac.compare_digest(
            candidate.encode("utf-8"), self._bootstrap_code.encode("utf-8")
        )
        with self._lock:
            if not is_right_code or self._bootstrap_code_used:
                return False
            self._bootstrap_code_used = True
            listener = self.bootstrap_listener
        if listener is not None:
            listener()
        return True


class DesktopSessionMiddleware:
    """
    A pure ASGI middleware: it refuses every request that does not come from
    the window of the application.

    - The Host header must name the address of the server (a defense against
      DNS rebinding).
    - A request with the bootstrap code gets the session cookie.
    - Any other request needs the session cookie.

    It covers the HTTP requests and the WebSocket connections.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        credentials: SessionCredentials,
        port: int,
        allowed_hosts: FrozenSet[str],
    ) -> None:
        self.app: ASGIApp = app
        self.cookie_name: str = get_session_cookie_name(port)
        self.credentials: SessionCredentials = credentials
        self.allowed_hosts: FrozenSet[str] = frozenset(
            host_.lower() for host_ in allowed_hosts
        )

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        header_pairs: List[Tuple[bytes, bytes]] = list(scope["headers"])
        if not self._has_allowed_host(header_pairs):
            await self._refuse(scope, send)
            return

        if scope["type"] == "http" and scope["path"] == BOOTSTRAP_PATH:
            await self._bootstrap(scope, send)
            return

        if not self._has_session_cookie(header_pairs):
            await self._refuse(scope, send)
            return

        await self.app(scope, receive, send)

    def _has_allowed_host(
        self, header_pairs: List[Tuple[bytes, bytes]]
    ) -> bool:
        hosts = [value_ for name_, value_ in header_pairs if name_ == b"host"]
        if len(hosts) != 1:
            return False
        return hosts[0].decode("latin-1").strip().lower() in self.allowed_hosts

    def _has_session_cookie(
        self, header_pairs: List[Tuple[bytes, bytes]]
    ) -> bool:
        for name_, value_ in header_pairs:
            if name_ != b"cookie":
                continue
            for cookie_ in value_.decode("latin-1").split(";"):
                cookie_name, _, cookie_value = cookie_.strip().partition("=")
                if cookie_name == self.cookie_name and (
                    self.credentials.is_token(cookie_value)
                ):
                    return True
        return False

    async def _bootstrap(self, scope: Scope, send: Send) -> None:
        code: Optional[str] = None
        if scope["method"] == "GET":
            query = parse_qs(scope["query_string"].decode("latin-1"))
            codes = query.get(BOOTSTRAP_CODE_PARAMETER, [])
            if len(codes) == 1:
                code = codes[0]
        if code is None or not self.credentials.consume_bootstrap_code(code):
            await self._refuse(scope, send)
            return
        cookie = (
            f"{self.cookie_name}={self.credentials.token}; "
            "HttpOnly; SameSite=Strict; Path=/"
        )
        start_message: Message = {
            "type": "http.response.start",
            "status": 303,
            "headers": [
                (b"location", b"/"),
                (b"set-cookie", cookie.encode("latin-1")),
                (b"cache-control", b"no-store"),
                (b"content-length", b"0"),
            ],
        }
        await send(start_message)
        await send({"type": "http.response.body", "body": b""})

    @staticmethod
    async def _refuse(scope: Scope, send: Send) -> None:
        if scope["type"] == "websocket":
            # Before the handshake is accepted, this answers with HTTP 403.
            await send({"type": "websocket.close", "code": 1008})
            return
        refused_message: Message = {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(_FORBIDDEN_BODY)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        }
        await send(refused_message)
        await send({"type": "http.response.body", "body": _FORBIDDEN_BODY})
