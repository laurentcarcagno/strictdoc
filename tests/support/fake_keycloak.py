"""A small HTTP server that answers like the parts of Keycloak that we use."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

SECRET = "s3cret"


class FakeKeycloak:
    def __init__(self, users: List[Dict[str, Any]]) -> None:
        self.users = users
        self.tokens_issued = 0
        self.user_requests = 0
        self.down = False
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def _send(self, status: int, body: Any) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self) -> None:
                if outer.down:
                    self._send(503, {})
                    return
                length = int(self.headers.get("Content-Length", 0))
                form = parse_qs(self.rfile.read(length).decode())
                if (
                    self.path != "/realms/infra/protocol/openid-connect/token"
                    or form.get("client_secret") != [SECRET]
                    or form.get("grant_type") != ["client_credentials"]
                ):
                    self._send(401, {"error": "unauthorized_client"})
                    return
                outer.tokens_issued += 1
                self._send(200, {"access_token": "tok", "expires_in": 300})

            def do_GET(self) -> None:
                if outer.down:
                    self._send(503, {})
                    return
                url = urlparse(self.path)
                if (
                    url.path != "/admin/realms/infra/users"
                    or self.headers.get("Authorization") != "Bearer tok"
                ):
                    self._send(401, {})
                    return
                outer.user_requests += 1
                query = parse_qs(url.query)
                first = int(query["first"][0])
                size = int(query["max"][0])
                self._send(200, outer.users[first : first + size])

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> "FakeKeycloak":
        self._thread.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self._server.shutdown()
        self._server.server_close()
