"""
An ASGI application in front of the applications of the projects: it picks the
application by the Host header and runs the lifespan of each one.

    <root host>          -> the portal
    <slug>.<root host>   -> the application of the project <slug>
    anything else        -> 404, with no information

Each project keeps its own application as it is, so every absolute URL of its
pages (/actions/..., /_static/...) stays valid: the project is the host name.
"""

from contextlib import AsyncExitStack
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

Scope = Dict[str, Any]
Receive = Callable[[], Awaitable[Dict[str, Any]]]
Send = Callable[[Dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def host_of(scope: Scope) -> str:
    """The host name of the request, lower case, without the port."""
    for name_, value_ in scope.get("headers", []):
        if name_ == b"host":
            host = value_.decode("latin-1").strip().lower()
            if host.startswith("["):  # an IPv6 address
                return host.split("]")[0] + "]"
            return host.split(":")[0]
    return ""


class ProjectDispatcher:
    def __init__(
        self,
        *,
        root_host: str,
        portal: ASGIApp,
        projects: Mapping[str, ASGIApp],
    ) -> None:
        self.root_host = root_host.lower()
        self.portal = portal
        self.projects: Dict[str, ASGIApp] = dict(projects)

    def app_for(self, host: str) -> Optional[ASGIApp]:
        if host == self.root_host:
            return self.portal
        suffix = "." + self.root_host
        if host.endswith(suffix):
            return self.projects.get(host[: -len(suffix)])
        return None

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return
        if scope["type"] == "http" and scope.get("path") == "/healthz":
            await self._respond(send, 200, b"ok")
            return
        app = self.app_for(host_of(scope))
        if app is None:
            if scope["type"] == "websocket":
                await receive()
                await send({"type": "websocket.close", "code": 1008})
            else:
                await self._respond(send, 404, b"Not found")
            return
        await app(scope, receive, send)

    @staticmethod
    async def _respond(send: Send, status: int, body: bytes) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"text/plain; charset=utf-8"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def _lifespan(self, receive: Receive, send: Send) -> None:
        """Starts the lifespan of every project and stops them in reverse."""
        await receive()  # lifespan.startup
        stack = AsyncExitStack()
        try:
            for app_ in self._lifespan_apps():
                await stack.enter_async_context(
                    app_.router.lifespan_context(app_)
                )
        except Exception as exception_:  # noqa: BLE001
            await stack.aclose()
            await send(
                {"type": "lifespan.startup.failed", "message": str(exception_)}
            )
            return
        await send({"type": "lifespan.startup.complete"})
        await receive()  # lifespan.shutdown
        await stack.aclose()
        await send({"type": "lifespan.shutdown.complete"})

    def _lifespan_apps(self) -> List[Any]:
        return [
            app_ for app_ in self.projects.values() if hasattr(app_, "router")
        ]
