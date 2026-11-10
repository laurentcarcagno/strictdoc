"""
A small route that tells a user who the server thinks they are.
"""

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from strictdoc.core.project_config import ProjectConfig
from strictdoc.export.html.generators.view_objects.app_screen_view_object import (
    render_app_screen,
)
from strictdoc.export.html.html_templates import JinjaEnvironment
from strictdoc.features.i18n.i18n import gettext
from strictdoc.features.roles.audit import AuditLog
from strictdoc.features.roles.principal import Principal

COLUMNS = ("time", "user", "role", "method", "path", "mid", "status")


def get_principal(request: Request) -> Principal:
    """The principal that the middleware set for this request."""
    principal = request.state.principal
    assert isinstance(principal, Principal)
    return principal


def create_roles_router(
    *,
    project_config: ProjectConfig,
    env: Callable[[], JinjaEnvironment],
    audit_log: Optional[AuditLog] = None,
) -> APIRouter:
    """
    env: the templates of the project, asked for when a page is rendered.
    """
    auth_mode = project_config.auth_mode
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
    def audit() -> HTMLResponse:
        """The last changes, for administrators (see route_roles.py)."""
        output = render_app_screen(
            jinja_environment=env(),
            project_config=project_config,
            title=gettext("Audit log"),
            viewtype="audit",
            content_template="features/roles/audit.jinja.html",
            has_log=audit_log is not None,
            columns=COLUMNS,
            entries=audit_log.tail(200) if audit_log is not None else [],
        )
        return HTMLResponse(content=output, status_code=200)

    return router
