"""
A Git server on the loopback address, for the tests of the Git access: Git over
HTTP (the program "git http-backend") behind a Basic authentication. It tells
which credentials it was given, so that a test can tell what Git sent and to
whom.

The credentials are made up for the tests. Nothing here reads a credential of
the computer.

@relation(SDOC-SRS-1239, scope=file)
@relation(SDOC-SRS-1241, scope=file)
"""

import base64
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional, Set, Tuple
from urllib.parse import urlsplit


class GitHttpServer:
    """
    Serves the bare repositories of a folder at http://127.0.0.1:<port>/<name>
    to the one user that it knows. A request without a credential, or with
    another one, gets a 401.
    """

    def __init__(self, repositories: Path, user: str, password: str) -> None:
        self.repositories: Path = repositories
        self.seen_credentials: Set[str] = set()
        self.unauthenticated_request_count: int = 0
        self._expected: str = f"{user}:{password}"
        self._user: str = user
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        assert self._server is not None
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def start(self) -> None:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                owner._handle(self)

            def do_POST(self) -> None:  # noqa: N802
                owner._handle(self)

            def log_message(
                self,
                format: str,  # noqa: A002
                *args: object,
            ) -> None:
                del format, args

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(5)
            self._thread = None

    def _handle(self, handler: BaseHTTPRequestHandler) -> None:
        body = _read_body(handler)
        header = handler.headers.get("Authorization", "")
        if header == "":
            self.unauthenticated_request_count += 1
            self._challenge(handler)
            return
        decoded = base64.b64decode(header.split(" ", 1)[-1]).decode("utf8")
        self.seen_credentials.add(decoded)
        if decoded != self._expected:
            self._challenge(handler)
            return
        status, headers, content = self._run_backend(handler, body)
        handler.send_response(status)
        for name_, value_ in headers.items():
            handler.send_header(name_, value_)
        handler.send_header("Content-Length", str(len(content)))
        handler.end_headers()
        handler.wfile.write(content)

    @staticmethod
    def _challenge(handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(401)
        handler.send_header("WWW-Authenticate", 'Basic realm="git"')
        handler.send_header("Content-Length", "0")
        handler.end_headers()

    def _run_backend(
        self, handler: BaseHTTPRequestHandler, body: bytes
    ) -> Tuple[int, Dict[str, str], bytes]:
        parts = urlsplit(handler.path)
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "GIT_PROJECT_ROOT": str(self.repositories),
            "GIT_HTTP_EXPORT_ALL": "1",
            "REQUEST_METHOD": handler.command,
            "PATH_INFO": parts.path,
            "QUERY_STRING": parts.query,
            "CONTENT_TYPE": handler.headers.get("Content-Type", ""),
            "CONTENT_LENGTH": str(len(body)),
            "REMOTE_USER": self._user,
            "REMOTE_ADDR": "127.0.0.1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.receivepack",
            "GIT_CONFIG_VALUE_0": "true",
        }
        encoding = handler.headers.get("Content-Encoding")
        if encoding is not None:
            environment["HTTP_CONTENT_ENCODING"] = encoding
        result = subprocess.run(
            ["git", "http-backend"],
            input=body,
            env=environment,
            capture_output=True,
            check=False,
            timeout=60,
        )
        raw_headers, _, content = result.stdout.partition(b"\r\n\r\n")
        status = 200
        headers: Dict[str, str] = {}
        for line_ in raw_headers.decode("utf8").splitlines():
            name_, _, value_ = line_.partition(":")
            if name_.lower() == "status":
                status = int(value_.strip().split(" ", 1)[0])
            else:
                headers[name_] = value_.strip()
        return status, headers, content


def _read_body(handler: BaseHTTPRequestHandler) -> bytes:
    if handler.headers.get("Transfer-Encoding", "").lower() == "chunked":
        chunks = []
        while True:
            size = int(handler.rfile.readline().strip() or b"0", 16)
            if size == 0:
                handler.rfile.readline()
                break
            chunks.append(handler.rfile.read(size))
            handler.rfile.readline()
        return b"".join(chunks)
    length = int(handler.headers.get("Content-Length", "0"))
    return handler.rfile.read(length) if length > 0 else b""
