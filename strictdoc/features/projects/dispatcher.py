"""
An ASGI application in front of the applications of the projects: one address
for every project. It runs the lifespan of each project and picks the
application of a request:

    /_projects...   -> the portal (list, creation, selection of the project)
    anything else   -> the application of the current project, named by the
                       cookie sdoc_project; without a known project, a
                       redirection to the portal
    another host    -> 404, with no information

Each project keeps its own application as it is, so every absolute URL of its
pages (/actions/..., /_static/...) stays valid. The cookie only chooses the
application: the project still checks the role of the user on every request.
"""

from contextlib import AsyncExitStack
from http.cookies import CookieError, SimpleCookie
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

Scope = Dict[str, Any]
Receive = Callable[[], Awaitable[Dict[str, Any]]]
Send = Callable[[Dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

PORTAL_PREFIX = "/_projects"
PROJECT_COOKIE = "sdoc_project"


def host_of(scope: Scope) -> str:
    """The host name of the request, lower case, without the port."""
    for name_, value_ in scope.get("headers", []):
        if name_ == b"host":
            host = value_.decode("latin-1").strip().lower()
            if host.startswith("["):  # an IPv6 address
                return host.split("]")[0] + "]"
            return host.split(":")[0]
    return ""


def cookie_of(scope: Scope, name: str) -> Optional[str]:
    """The value of a cookie of the request, or None."""
    for name_, value_ in scope.get("headers", []):
        if name_ == b"cookie":
            jar: SimpleCookie = SimpleCookie()
            try:
                jar.load(value_.decode("latin-1"))
            except CookieError:
                return None
            if name in jar:
                return jar[name].value
    return None


def is_portal_path(path: str) -> bool:
    return path == PORTAL_PREFIX or path.startswith(PORTAL_PREFIX + "/")


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
        # Open while the lifespan runs: a project added then is started too.
        self._stack: Optional[AsyncExitStack] = None

    async def add_project(self, slug: str, app: ASGIApp) -> None:
        """Serves a new project from now on, starting its lifespan."""
        if self._stack is not None and hasattr(app, "router"):
            await self._stack.enter_async_context(
                app.router.lifespan_context(app)  # type: ignore[attr-defined]
            )
        self.projects[slug] = app

    def app_for(self, scope: Scope) -> Optional[ASGIApp]:
        """
        The portal or the current project; None for another host or for
        a request with no known project.
        """
        if host_of(scope) != self.root_host:
            return None
        if is_portal_path(scope.get("path", "")):
            return self.portal
        slug = cookie_of(scope, PROJECT_COOKIE)
        return self.projects.get(slug) if slug else None

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] == "lifespan":
            await self._lifespan(receive, send)
            return
        if scope["type"] == "http" and scope.get("path") == "/healthz":
            await self._respond(send, 200, b"ok")
            return
        app = self.app_for(scope)
        if app is None:
            if scope["type"] == "websocket":
                await receive()
                await send({"type": "websocket.close", "code": 1008})
            elif host_of(scope) != self.root_host:
                await self._respond(send, 404, b"Not found")
            else:
                # No project chosen yet, or one that does not exist (any
                # more): the list of the projects.
                await self._redirect(send, PORTAL_PREFIX)
            return
        await app(scope, receive, send)

    @staticmethod
    async def _redirect(send: Send, location: str) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 303,
                "headers": [
                    (b"location", location.encode()),
                    (b"content-length", b"0"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b""})

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
        self._stack = stack
        try:
            for app_ in self._lifespan_apps():
                await stack.enter_async_context(
                    app_.router.lifespan_context(app_)
                )
        except Exception as exception_:  # noqa: BLE001
            self._stack = None
            await stack.aclose()
            await send(
                {"type": "lifespan.startup.failed", "message": str(exception_)}
            )
            return
        await send({"type": "lifespan.startup.complete"})
        await receive()  # lifespan.shutdown
        self._stack = None
        await stack.aclose()
        await send({"type": "lifespan.shutdown.complete"})

    def _lifespan_apps(self) -> List[Any]:
        return [
            app_ for app_ in self.projects.values() if hasattr(app_, "router")
        ]
