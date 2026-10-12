"""
Refuses a request whose user has not the role that the route needs.

It runs inside PrincipalMiddleware (which has set the principal and its role)
and looks up the route that Starlette would call, in the table of
route_roles.py. With ``auth_mode="none"`` everybody is administrator and
nothing is refused.
"""

import json
from typing import Any, Awaitable, Callable, Dict, Optional

from strictdoc.features.i18n.i18n import gettext
from strictdoc.features.roles.middleware import AUTH_MODE_NONE
from strictdoc.features.roles.principal import Principal
from strictdoc.features.roles.roles import role_allows
from strictdoc.features.roles.route_roles import (
    ROUTE_ROLES,
    RouteKey,
    match_route_key,
)

Scope = Dict[str, Any]
Receive = Callable[[], Awaitable[Dict[str, Any]]]
Send = Callable[[Dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class RoleMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        auth_mode: str = AUTH_MODE_NONE,
    ) -> None:
        self.app = app
        self.auth_mode = auth_mode

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] not in ("http", "websocket") or (
            self.auth_mode == AUTH_MODE_NONE
        ):
            await self.app(scope, receive, send)
            return

        key = self._route_key(scope)
        if key is None:
            # No route matches: the application answers 404.
            await self.app(scope, receive, send)
            return

        principal: Principal = scope["state"]["principal"]
        required = ROUTE_ROLES.get(key)
        if required is None or not role_allows(principal.role, required):
            await self._refuse(scope, send, principal, required)
            return
        await self.app(scope, receive, send)

    @staticmethod
    def _route_key(scope: Scope) -> Optional[RouteKey]:
        if scope["type"] == "websocket":
            method = "WS"
        else:
            method = scope["method"].upper()
            if method == "HEAD":
                method = "GET"
            if method == "OPTIONS":
                # Answered by the CORS layer; it reveals nothing.
                return None
        return match_route_key(method, scope["path"])

    @staticmethod
    async def _refuse(
        scope: Scope,
        send: Send,
        principal: Principal,
        required: Optional[str],
    ) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4403})
            return
        if principal.role is None:
            detail = gettext("Your account is not a member of this project.")
        elif required is None:
            detail = gettext("This route has no role: it is refused.")
        else:
            detail = gettext(
                "Your role (%(role)s) does not allow this. "
                "The role '%(required)s' is needed."
            ) % {
                "role": gettext(principal.role),
                "required": gettext(required),
            }
        accepts_html = any(
            name_ == b"accept" and b"text/html" in value_
            for name_, value_ in scope.get("headers", [])
        )
        if accepts_html:
            body = (
                "<!DOCTYPE html><html><body><h1>403</h1><p>"
                + detail
                + "</p></body></html>"
            ).encode("utf8")
            content_type = b"text/html; charset=utf-8"
        else:
            body = json.dumps({"detail": detail}).encode("utf8")
            content_type = b"application/json"
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", content_type),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
