"""
A small HTTP server that answers like the parts of GitLab that the sign-in of
the desktop application uses: the authorization page, the token endpoint and
the user of the API.

It follows what the test GitLab does (see D2-0): a registered application, a
loopback callback address with any port, and, once the user is signed in to
GitLab, an authorization page that answers 200 with a page whose script sets
window.location to the callback address. It is not a 302 redirect.

@relation(SDOC-SRS-1234, scope=file)
"""

import base64
import hashlib
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse

CLIENT_ID = "fake-desktop-application"
USERNAME = "jdupont"
DISPLAY_NAME = "Jeanne Dupont"
EMAIL = "jeanne.dupont@example.org"
CALLBACK_PATH = "/__desktop/oauth/callback"

# What the authorization page does.
MODE_GRANT = "grant"
# The user refuses on the page of GitLab.
MODE_DENY = "deny"
# The callback carries a state that the application did not send.
MODE_WRONG_STATE = "wrong_state"


class FakeGitLab:
    """
    The server runs in a thread. The attributes tell what a test needs to
    check afterwards: the requests that the server got, the tokens it issued.
    """

    def __init__(self) -> None:
        self.mode: str = MODE_GRANT
        # The authorization requests that were accepted (their query).
        self.authorization_requests: List[Dict[str, str]] = []
        # The forms that the token endpoint received, without the code.
        self.token_requests: List[Dict[str, str]] = []
        self.user_request_count: int = 0
        # code -> the authorization request that issued it.
        self._codes: Dict[str, Dict[str, str]] = {}
        self._access_tokens: List[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def do_GET(self) -> None:
                url = urlparse(self.path)
                query = {
                    name_: values_[0]
                    for name_, values_ in parse_qs(url.query).items()
                }
                if url.path == "/oauth/authorize":
                    outer.handle_authorize(self, query)
                elif url.path == "/api/v4/user":
                    outer.handle_user(self)
                else:
                    outer.send_text(self, 404, "Not found")

            def do_POST(self) -> None:
                url = urlparse(self.path)
                length = int(self.headers.get("Content-Length", 0))
                form = {
                    name_: values_[0]
                    for name_, values_ in parse_qs(
                        self.rfile.read(length).decode("utf-8")
                    ).items()
                }
                if url.path == "/oauth/token":
                    outer.handle_token(self, form)
                else:
                    outer.send_text(self, 404, "Not found")

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )

    @property
    def port(self) -> int:
        port: int = self._server.server_address[1]
        return port

    @property
    def url(self) -> str:
        """
        The address of the fake GitLab. The name "localhost" and not the
        address 127.0.0.1: for the browser it is another site than the home
        server, as the real GitLab is, so the callback arrives without the
        SameSite=Strict cookie of the home server.
        """
        return f"http://localhost:{self.port}"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(10)

    def __enter__(self) -> "FakeGitLab":
        self.start()
        return self

    def __exit__(self, *arguments: Any) -> None:
        self.stop()

    def handle_authorize(
        self, handler: BaseHTTPRequestHandler, query: Dict[str, str]
    ) -> None:
        redirect_uri = query.get("redirect_uri", "")
        parts = urlparse(redirect_uri)
        # GitLab: the host and the path must be the registered ones, and any
        # port goes for a loopback address.
        if (
            query.get("client_id") != CLIENT_ID
            or parts.scheme != "http"
            or parts.hostname != "127.0.0.1"
            or parts.path != CALLBACK_PATH
            or query.get("response_type") != "code"
            or query.get("code_challenge_method") != "S256"
            or len(query.get("code_challenge", "")) == 0
            or len(query.get("state", "")) == 0
        ):
            self.send_text(
                handler,
                400,
                "The authorization request is not valid: "
                "the redirect URI included is not valid.",
            )
            return
        self.authorization_requests.append(dict(query))
        if self.mode == MODE_DENY:
            parameters = {"error": "access_denied", "state": query["state"]}
        else:
            code = secrets.token_urlsafe(24)
            self._codes[code] = dict(query)
            parameters = {
                "code": code,
                "state": "forged"
                if self.mode == MODE_WRONG_STATE
                else query["state"],
            }
        target = f"{redirect_uri}?{urlencode(parameters)}"
        body = (
            "<!DOCTYPE html><html><body><h1>Redirecting</h1>"
            f'<a href="{target}">Click here to redirect</a>'
            f'<script>window.location = "{target}";</script>'
            "</body></html>"
        )
        self.send_text(handler, 200, body, content_type="text/html")

    def handle_token(
        self, handler: BaseHTTPRequestHandler, form: Dict[str, str]
    ) -> None:
        self.token_requests.append(
            {name_: value_ for name_, value_ in form.items() if name_ != "code"}
        )
        # A code works once.
        request = self._codes.pop(form.get("code", ""), None)
        if (
            request is None
            or form.get("grant_type") != "authorization_code"
            or form.get("client_id") != CLIENT_ID
            or form.get("redirect_uri") != request["redirect_uri"]
            or self._create_challenge(form.get("code_verifier", ""))
            != request["code_challenge"]
        ):
            self.send_json(handler, 400, {"error": "invalid_grant"})
            return
        access_token = secrets.token_urlsafe(24)
        self._access_tokens.append(access_token)
        self.send_json(
            handler,
            200,
            {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 7200,
                "refresh_token": secrets.token_urlsafe(24),
                "scope": request["scope"],
                "created_at": 0,
            },
        )

    def handle_user(self, handler: BaseHTTPRequestHandler) -> None:
        self.user_request_count += 1
        authorization = handler.headers.get("Authorization", "")
        token: Optional[str] = (
            authorization[len("Bearer ") :]
            if authorization.startswith("Bearer ")
            else None
        )
        if token is None or token not in self._access_tokens:
            self.send_json(handler, 401, {"message": "401 Unauthorized"})
            return
        self.send_json(
            handler,
            200,
            {"username": USERNAME, "name": DISPLAY_NAME, "email": EMAIL},
        )

    @staticmethod
    def send_json(
        handler: BaseHTTPRequestHandler, status: int, body: Dict[str, Any]
    ) -> None:
        FakeGitLab.send_text(
            handler,
            status,
            json.dumps(body),
            content_type="application/json",
        )

    @staticmethod
    def send_text(
        handler: BaseHTTPRequestHandler,
        status: int,
        body: str,
        content_type: str = "text/plain",
    ) -> None:
        data = body.encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)

    @staticmethod
    def _create_challenge(code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
