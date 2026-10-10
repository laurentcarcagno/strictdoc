"""
The audit log: who did what, one JSON line per change.

A line is written for every request that changes something (POST, PUT, PATCH,
DELETE and the GET that writes the Nestor export), with the user, the role,
the route, the node or document identifier when the request names one, and the
status code. A refused request is logged too, with status 403: an attempt to do
what the role does not allow is worth knowing. The body of a request is never
read or written.
"""

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib.parse import parse_qs

from strictdoc.features.roles.principal import Principal

Scope = Dict[str, Any]
Receive = Callable[[], Awaitable[Dict[str, Any]]]
Send = Callable[[Dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_CHANGING_METHODS = ("POST", "PUT", "PATCH", "DELETE")
_ALWAYS_LOGGED = (("GET", "/__nestor"),)
_MID_PARAMETERS = (
    "requirement_mid",
    "node_id",
    "node_mid",
    "document_mid",
    "reference_mid",
    "context_document_mid",
)


class AuditLog:
    """A JSON-lines file that is rotated by size."""

    def __init__(
        self, path: str, max_bytes: int = 5 * 1024 * 1024, backups: int = 5
    ) -> None:
        self.path = path
        self._max_bytes = max_bytes
        self._backups = backups
        self._lock = threading.Lock()

    def record(self, entry: Dict[str, Any]) -> None:
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
        with self._lock:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            if (
                os.path.exists(self.path)
                and os.path.getsize(self.path) + len(line) > self._max_bytes
            ):
                self._rotate()
            with open(self.path, "a", encoding="utf8") as file_:
                file_.write(line)

    def tail(self, count: int = 200) -> List[Dict[str, Any]]:
        """The last entries, the newest first."""
        entries: List[Dict[str, Any]] = []
        with self._lock:
            files = [self.path] + [
                f"{self.path}.{index_}"
                for index_ in range(1, self._backups + 1)
            ]
            for path_ in files:
                if not os.path.exists(path_):
                    continue
                with open(path_, encoding="utf8") as file_:
                    lines = file_.read().splitlines()
                for line_ in reversed(lines):
                    try:
                        entries.append(json.loads(line_))
                    except ValueError:
                        continue
                    if len(entries) >= count:
                        return entries
        return entries

    def _rotate(self) -> None:
        oldest = f"{self.path}.{self._backups}"
        if os.path.exists(oldest):
            os.remove(oldest)
        for index_ in range(self._backups - 1, 0, -1):
            source = f"{self.path}.{index_}"
            if os.path.exists(source):
                os.replace(source, f"{self.path}.{index_ + 1}")
        os.replace(self.path, f"{self.path}.1")


def _mid_of(scope: Scope) -> Optional[str]:
    query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
    for name_ in _MID_PARAMETERS:
        if name_ in query and len(query[name_]) > 0:
            return query[name_][0]
    return None


class AuditMiddleware:
    """Writes the audit line of a request once its status is known."""

    def __init__(self, app: ASGIApp, *, audit_log: Optional[AuditLog]) -> None:
        self.app = app
        self._audit_log = audit_log

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if self._audit_log is None or scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope["method"].upper()
        path = scope["path"]
        if method not in _CHANGING_METHODS and (method, path) not in (
            _ALWAYS_LOGGED
        ):
            await self.app(scope, receive, send)
            return

        status = {"code": 0}

        async def capture(message: Dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            principal: Principal = scope["state"]["principal"]
            self._audit_log.record(
                {
                    "time": datetime.now(timezone.utc).isoformat(
                        timespec="seconds"
                    ),
                    "user": principal.user,
                    "subject": principal.subject,
                    "role": principal.role,
                    "method": method,
                    "path": path,
                    "mid": _mid_of(scope),
                    "status": status["code"],
                }
            )
