"""
A small route that tells a user who the server thinks they are.
"""

from html import escape
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from strictdoc.features.roles.audit import AuditLog
from strictdoc.features.roles.principal import Principal

COLUMNS = ("time", "user", "role", "method", "path", "mid", "status")


def get_principal(request: Request) -> Principal:
    """The principal that the middleware set for this request."""
    principal = request.state.principal
    assert isinstance(principal, Principal)
    return principal


def create_roles_router(
    auth_mode: str, audit_log: Optional[AuditLog] = None
) -> APIRouter:
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
            "role": principal.role,
            "auth_mode": auth_mode,
        }

    @router.get("/audit", response_class=HTMLResponse)
    def audit() -> str:
        """The last changes, for administrators (see route_roles.py)."""
        if audit_log is None:
            return (
                "<!DOCTYPE html><html><body><h1>Audit log</h1>"
                "<p>The audit log is written only behind a login proxy "
                "(auth_mode proxy).</p></body></html>"
            )
        rows = "".join(
            "<tr>"
            + "".join(
                f"<td>{escape(str(entry_.get(column_) or ''))}</td>"
                for column_ in COLUMNS
            )
            + "</tr>"
            for entry_ in audit_log.tail(200)
        )
        header = "".join(f"<th>{column_}</th>" for column_ in COLUMNS)
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>Audit log</title></head><body><h1>Audit log</h1>"
            "<p>The last 200 changes, newest first.</p>"
            f"<table border='1' cellpadding='4'><tr>{header}</tr>{rows}"
            "</table></body></html>"
        )

    return router
