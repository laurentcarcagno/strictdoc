"""
A small server of the protocol of OpenAI for the end2end tests: it lists one
model and answers a chat completion with a canned text. It runs on the loopback
address of the computer, so no test reaches a real service, and it counts the
requests, so that a test can tell that nothing was sent.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import TracebackType
from typing import Any, Dict, List, Optional, Type

MODEL = "fake-model"
SIMULATED_REMARK = "Start what, and when?"
ANSWER = {
    "comments": [
        {"severity": "warning", "quote": "start", "body": SIMULATED_REMARK},
    ]
}


class FakeOpenAI:
    def __init__(self) -> None:
        self.requests: List[Dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                outer.requests.append(
                    {
                        "method": "GET",
                        "path": self.path,
                        "headers": self._get_headers(),
                    }
                )
                if self.path.rstrip("/").endswith("/v1/models"):
                    self._send({"data": [{"id": MODEL}]})
                else:
                    self._send({"error": "not found"}, 404)

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                outer.requests.append(
                    {
                        "method": "POST",
                        "path": self.path,
                        "body": body,
                        "headers": self._get_headers(),
                    }
                )
                if self.path.endswith("/chat/completions"):
                    self._send(
                        {
                            "model": MODEL,
                            "choices": [
                                {
                                    "message": {
                                        "role": "assistant",
                                        "content": json.dumps(ANSWER),
                                    }
                                }
                            ],
                            "usage": {
                                "prompt_tokens": 10,
                                "completion_tokens": 5,
                            },
                        }
                    )
                else:
                    self._send({"error": "not found"}, 404)

            def _get_headers(self) -> Dict[str, str]:
                return {k_.lower(): v_ for k_, v_ in self.headers.items()}

            def _send(self, body: Dict[str, Any], status: int = 200) -> None:
                raw = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *_: Any) -> None:
                pass

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True
        )

    @property
    def url(self) -> str:
        """The address to give as the one of a server compatible with OpenAI."""
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def get_chat_count(self) -> int:
        return len(
            [
                request_
                for request_ in self.requests
                if request_["method"] == "POST"
            ]
        )

    def __enter__(self) -> "FakeOpenAI":
        self._thread.start()
        return self

    def __exit__(
        self,
        exception_type: Optional[Type[BaseException]],
        exception: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self._server.shutdown()
        self._server.server_close()
