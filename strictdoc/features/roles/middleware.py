"""
The ASGI middleware that decides who is acting for every request and every
WebSocket connection, before any route runs.

Two modes (project option ``auth_mode``):

- ``none`` (default): no login in front of the server; every request gets the
  anonymous principal. This is how the server behaves without this feature.
- ``proxy``: the server runs behind oauth2-proxy. A request is served only if
  it comes from a trusted proxy network and carries the identity headers;
  anything else is refused with 401, including static files and the page
  routes.
"""

import ipaddress
import json
from dataclasses import replace
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
)

from strictdoc.features.roles.principal import (
    CURRENT_ROLE,
    Principal,
    principal_from_headers,
)
from strictdoc.features.roles.roles import (
    resolve_role,
    role_rank,
    validate_roles,
)

AUTH_MODE_NONE = "none"
AUTH_MODE_PROXY = "proxy"
AUTH_MODES = (AUTH_MODE_NONE, AUTH_MODE_PROXY)

Scope = Dict[str, Any]
Receive = Callable[[], Awaitable[Dict[str, Any]]]
Send = Callable[[Dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_ANY_NETWORK = Sequence[ipaddress.IPv4Network | ipaddress.IPv6Network]


def parse_networks(cidrs: Sequence[str]) -> List[Any]:
    """The networks of a list of CIDR strings; raises ValueError on a bad one."""
    return [ipaddress.ip_network(cidr_, strict=False) for cidr_ in cidrs]


class PrincipalMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        auth_mode: str = AUTH_MODE_NONE,
        trusted_proxies: Sequence[str] = (),
        roles: Optional[Mapping[str, Sequence[str]]] = None,
        member_role: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        if auth_mode not in AUTH_MODES:
            raise ValueError(
                f"Invalid auth_mode '{auth_mode}'. Use one of {AUTH_MODES}."
            )
        networks = parse_networks(trusted_proxies)
        if auth_mode == AUTH_MODE_PROXY and len(networks) == 0:
            raise ValueError(
                "auth_mode 'proxy' needs trusted_proxies, the networks that "
                "oauth2-proxy connects from."
            )
        self._roles = validate_roles(roles or {})
        if (
            auth_mode == AUTH_MODE_PROXY
            and len(self._roles) == 0
            and member_role is None
        ):
            raise ValueError(
                "auth_mode 'proxy' needs roles: the groups of each role."
            )
        self.app = app
        self.auth_mode = auth_mode
        self._networks = networks
        # The role that the member list of the project gives to a user name.
        self._member_role = member_role

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        principal = self._principal(scope)
        if principal is None:
            await self._refuse(scope, send)
            return
        scope.setdefault("state", {})["principal"] = principal
        token = CURRENT_ROLE.set(principal.role)
        try:
            await self.app(scope, receive, send)
        finally:
            CURRENT_ROLE.reset(token)

    def _principal(self, scope: Scope) -> Optional[Principal]:
        if self.auth_mode == AUTH_MODE_NONE:
            return Principal.anonymous()
        if not self._is_trusted_peer(scope.get("client")):
            return None
        headers = {
            name_.decode("latin-1").lower(): value_.decode("latin-1")
            for name_, value_ in scope.get("headers", [])
        }
        principal = principal_from_headers(headers)
        if principal is None:
            return None
        role = resolve_role(principal.groups, self._roles)
        if self._member_role is not None:
            member = self._member_role(principal.user.lower())
            if member is not None and (
                role is None or role_rank(member) > role_rank(role)
            ):
                role = member
        return replace(principal, role=role)

    def _is_trusted_peer(self, client: Optional[Any]) -> bool:
        if client is None:
            return False
        try:
            address = ipaddress.ip_address(client[0])
        except ValueError:
            return False
        if address.version == 6 and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        return any(address in network_ for network_ in self._networks)

    @staticmethod
    async def _refuse(scope: Scope, send: Send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4401})
            return
        body = json.dumps({"detail": "Authentication required."}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
