"""
A small route that tells a user who the server thinks they are.
"""

from typing import Any, Dict

from fastapi import APIRouter, Request

from strictdoc.features.roles.principal import Principal


def get_principal(request: Request) -> Principal:
    """The principal that the middleware set for this request."""
    principal = request.state.principal
    assert isinstance(principal, Principal)
    return principal


def create_roles_router(auth_mode: str) -> APIRouter:
    router = APIRouter()

    @router.get("/whoami")
    def whoami(request: Request) -> Dict[str, Any]:
        principal = get_principal(request)
        return {
            "user": principal.user,
            "subject": principal.subject,
            "email": principal.email,
            "groups": list(principal.groups),
            "authenticated": principal.authenticated,
            "auth_mode": auth_mode,
        }

    return router
