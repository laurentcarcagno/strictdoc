"""
A small HTTP server that answers like the parts of GitLab that the sign-in of
the desktop application uses: the authorization page, the token endpoint and
the user of the API.

It follows what the test GitLab does (see D2-0): a registered application, a
loopback callback address with any port, and, once the user is signed in to
GitLab, an authorization page that answers 200 with a page whose script sets
window.location to the callback address. It is not a 302 redirect.

@relation(SDOC-SRS-1234, scope=file)
@relation(SDOC-SRS-1235, scope=file)
@relation(SDOC-SRS-1237, scope=file)
@relation(SDOC-SRS-1240, scope=file)
"""

import base64
import hashlib
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Set
from urllib.parse import parse_qs, unquote, urlencode, urlparse

CLIENT_ID = "fake-desktop-application"
USERNAME = "jdupont"
DISPLAY_NAME = "Jeanne Dupont"
EMAIL = "jeanne.dupont@example.org"
CALLBACK_PATH = "/__desktop/oauth/callback"
# The group of the catalog and its identifier.
GROUP_PATH = "demo"
GROUP_ID = 7

# GitLab access levels.
GUEST = 10
REPORTER = 20
DEVELOPER = 30
MAINTAINER = 40

# What the authorization page does.
MODE_GRANT = "grant"
# The user refuses on the page of GitLab.
MODE_DENY = "deny"
# The callback carries a state that the application did not send.
MODE_WRONG_STATE = "wrong_state"

# What the token endpoint does with a refresh token.
REFRESH_GRANT = "grant"
# GitLab refuses the refresh token: {"error": "invalid_grant"}.
REFRESH_INVALID_GRANT = "invalid_grant"


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
        # The forms of the renewals, without the refresh token.
        self.refresh_requests: List[Dict[str, str]] = []
        self.user_request_count: int = 0
        # The projects of the group: their GitLab data, and the access level
        # that the user has on each. A project with no level is not listed.
        self.projects: Dict[int, Dict[str, Any]] = {}
        self.access_levels: Dict[int, int] = {}
        self.project_request_count: int = 0
        # The life of the access tokens that the server gives, in seconds.
        self.expires_in: int = 7200
        self.refresh_mode: str = REFRESH_GRANT
        self._refresh_tokens: Set[str] = set()
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
                elif unquote(url.path).startswith("/api/v4/groups/"):
                    outer.handle_group(self, unquote(url.path), query)
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
        self._is_stopped: bool = False

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
        """Stop the server. A test can stop it before the end of its block."""
        if self._is_stopped:
            return
        self._is_stopped = True
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
        if form.get("grant_type") == "refresh_token":
            self.handle_refresh(handler, form)
            return
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
        self.send_json(handler, 200, self._create_tokens(request["scope"]))

    def handle_refresh(
        self, handler: BaseHTTPRequestHandler, form: Dict[str, str]
    ) -> None:
        self.refresh_requests.append(
            {
                name_: value_
                for name_, value_ in form.items()
                if name_ != "refresh_token"
            }
        )
        refresh_token = form.get("refresh_token", "")
        # Like GitLab: a refresh token works once, the answer gives the next.
        if (
            self.refresh_mode == REFRESH_INVALID_GRANT
            or form.get("client_id") != CLIENT_ID
            or refresh_token not in self._refresh_tokens
        ):
            self.send_json(handler, 400, {"error": "invalid_grant"})
            return
        self._refresh_tokens.discard(refresh_token)
        self.send_json(handler, 200, self._create_tokens("read_user"))

    def _create_tokens(self, scope: str) -> Dict[str, Any]:
        access_token = secrets.token_urlsafe(24)
        refresh_token = secrets.token_urlsafe(24)
        self._access_tokens.append(access_token)
        self._refresh_tokens.add(refresh_token)
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": self.expires_in,
            "refresh_token": refresh_token,
            "scope": scope,
            "created_at": 0,
        }

    def add_project(
        self,
        project_id: int,
        name: str,
        clone_url: str,
        access_level: int,
        *,
        subgroup: str = "",
    ) -> None:
        """A project of the group, with the access level of the user."""
        path = "/".join(
            part_ for part_ in (GROUP_PATH, subgroup, name.lower()) if part_
        )
        self.projects[project_id] = {
            "id": project_id,
            "name": name,
            "path_with_namespace": path,
            "description": "",
            "http_url_to_repo": clone_url,
            "archived": False,
        }
        self.access_levels[project_id] = access_level

    def handle_group(
        self,
        handler: BaseHTTPRequestHandler,
        path: str,
        query: Dict[str, str],
    ) -> None:
        """
        GET /api/v4/groups/<path or id> and /api/v4/groups/<id>/projects, with
        the filter min_access_level, as python-gitlab asks them.
        """
        if not self._has_good_token(handler):
            self.send_json(handler, 401, {"message": "401 Unauthorized"})
            return
        parts = path[len("/api/v4/groups/") :].split("/projects")
        if parts[0] not in (GROUP_PATH, str(GROUP_ID)):
            self.send_json(handler, 404, {"message": "404 Group Not Found"})
            return
        if len(parts) == 1:
            self.send_json(
                handler, 200, {"id": GROUP_ID, "full_path": GROUP_PATH}
            )
            return
        self.project_request_count += 1
        minimum = int(query.get("min_access_level", "0"))
        listed = [
            project_
            for id_, project_ in sorted(self.projects.items())
            if id_ in self.access_levels and self.access_levels[id_] >= minimum
        ]
        data = json.dumps(listed).encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("X-Page", "1")
        handler.send_header("X-Total-Pages", "1")
        handler.send_header("X-Total", str(len(listed)))
        handler.end_headers()
        handler.wfile.write(data)

    def handle_user(self, handler: BaseHTTPRequestHandler) -> None:
        self.user_request_count += 1
        if not self._has_good_token(handler):
            self.send_json(handler, 401, {"message": "401 Unauthorized"})
            return
        self.send_json(
            handler,
            200,
            {"username": USERNAME, "name": DISPLAY_NAME, "email": EMAIL},
        )

    def _has_good_token(self, handler: BaseHTTPRequestHandler) -> bool:
        authorization = handler.headers.get("Authorization", "")
        token: Optional[str] = (
            authorization[len("Bearer ") :]
            if authorization.startswith("Bearer ")
            else None
        )
        return token is not None and token in self._access_tokens

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
