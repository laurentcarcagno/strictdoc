"""
The portal, at /_projects of the one address of the server: the list of the
projects the user can open, with the role the user has in each one. Choosing a
project sets the cookie that the dispatcher reads (dispatcher.py), so the same
address then shows that project. A platform administrator also creates
projects here; the administrator of a project reaches its members page from
the list.
"""

import datetime as dt
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from strictdoc.features.i18n import i18n
from strictdoc.features.projects.dispatcher import (
    PORTAL_PREFIX,
    PROJECT_COOKIE,
)
from strictdoc.features.projects.manager import ProjectManager
from strictdoc.features.roles.principal import Principal
from strictdoc.helpers.exception import StrictDocException

TEMPLATES = Environment(
    loader=FileSystemLoader(
        os.path.join(os.path.dirname(__file__), "templates")
    ),
    autoescape=select_autoescape(["html"]),
)
i18n.install(TEMPLATES)


# The static files of StrictDoc (styles, fonts, nav.js), served by the portal
# under its own prefix: the paths of the projects belong to the projects.
STATIC_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "export", "html", "_static"
)
ASSETS_URL = PORTAL_PREFIX + "/assets"
# Logs out of oauth2-proxy, which also ends the session of the login server
# (its --backend-logout-url).
LOGOUT_URL = "/oauth2/sign_out"
# The choice of the project lasts one year.
COOKIE_MAX_AGE = 365 * 24 * 3600


def select_url(slug: str, next_path: str = "/") -> str:
    """
    The address that makes `slug` the current project, then opens
    `next_path` in it.
    """
    url = f"{PORTAL_PREFIX}/select/{slug}"
    return url if next_path == "/" else f"{url}?next={next_path}"


def shell_context(
    request: Request,
    role: Optional[str] = None,
    assets: str = ASSETS_URL,
) -> Dict[str, Any]:
    """What the frame of the pages (shell.jinja.html) shows of the user."""
    principal: Optional[Principal] = request.scope.get("state", {}).get(
        "principal"
    )
    user = principal.user if principal is not None else None
    signed_in = user is not None and user != "anonymous"
    return {
        "assets": assets,
        "user": user,
        "role": role,
        "logout_url": LOGOUT_URL if signed_in else None,
        "portal_url": PORTAL_PREFIX,
    }


def same_origin(request: Request) -> bool:
    """False for a form posted from another site (the Origin header)."""
    origin = request.headers.get("origin")
    if origin is None:
        return True
    return bool(urlsplit(origin).netloc == request.headers.get("host", ""))


def safe_next(value: Optional[str]) -> str:
    """
    A path of this server to open after the selection, never another
    site.
    """
    if (
        value is None
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
    ):
        return "/"
    return value


def create_portal(
    *,
    manager: ProjectManager,
    root_host: str,  # noqa: ARG001 (the dispatcher checks the host)
) -> Starlette:
    def projects_of(request: Request) -> List[Dict[str, Any]]:
        """The projects that the user may open, with the role in each."""
        principal: Principal = request.scope["state"]["principal"]
        current = request.cookies.get(PROJECT_COOKIE)
        rows: List[Dict[str, Any]] = []
        for slug_, spec_ in manager.specs.items():
            role = manager.role_in(slug_, principal)
            if role is None:
                continue
            rows.append(
                {
                    "title": spec_.title,
                    "slug": slug_,
                    "role": role,
                    "archived": spec_.archived,
                    "current": slug_ == current,
                }
            )
        return rows

    def page(
        request: Request,
        error: Optional[str] = None,
        slug: str = "",
        title: str = "",
        status_code: int = 200,
    ) -> HTMLResponse:
        principal: Principal = request.scope["state"]["principal"]
        rows = projects_of(request)
        for row_ in rows:
            index = manager.contexts[
                row_["slug"]
            ].export_action.traceability_index
            row_["documents"] = len(index.document_tree.document_list)
            row_["last_change"] = _format_time(index.index_last_updated)
            row_["url"] = select_url(row_["slug"])
            row_["members_url"] = select_url(row_["slug"], "/members")
        output = TEMPLATES.get_template("portal.jinja.html").render(
            **shell_context(request),
            rows=rows,
            can_create=manager.is_platform_admin(principal)
            and manager.data_root is not None,
            error=error,
            slug=slug,
            title=title,
        )
        return HTMLResponse(output, status_code=status_code)

    def home(request: Request) -> HTMLResponse:
        return page(request)

    def mine(request: Request) -> JSONResponse:
        """The projects of the user, for the project picker of the sidebar."""
        return JSONResponse(
            [
                {
                    "slug": row_["slug"],
                    "title": row_["title"],
                    "role": row_["role"],
                    "current": row_["current"],
                    "url": select_url(row_["slug"]),
                }
                for row_ in projects_of(request)
            ]
        )

    def select(request: Request) -> Response:
        """Makes a project the current one (a cookie), then opens it."""
        principal: Principal = request.scope["state"]["principal"]
        slug = request.path_params["slug"]
        if (
            slug not in manager.specs
            or manager.role_in(slug, principal) is None
        ):
            return RedirectResponse(PORTAL_PREFIX, 303)
        response = RedirectResponse(
            safe_next(request.query_params.get("next")), 303
        )
        response.set_cookie(
            PROJECT_COOKIE,
            slug,
            max_age=COOKIE_MAX_AGE,
            path="/",
            httponly=True,
            samesite="lax",
            secure=request.headers.get("x-forwarded-proto") == "https",
        )
        return response

    async def create(request: Request) -> Response:
        principal: Principal = request.scope["state"]["principal"]
        if not manager.is_platform_admin(principal):
            return HTMLResponse(
                "<h1>403</h1><p>Only an administrator creates projects.</p>",
                status_code=403,
            )
        if not same_origin(request):
            return HTMLResponse("<h1>403</h1>", status_code=403)
        form = await request.form()
        slug = str(form.get("slug", "")).strip().lower()
        title = str(form.get("title", ""))
        try:
            await manager.create_project(slug, title, principal.user.lower())
        except StrictDocException as exception_:
            return page(request, str(exception_), slug, title, 422)
        return RedirectResponse(select_url(slug), 303)

    return Starlette(
        routes=[
            Route(PORTAL_PREFIX, home),
            Route(PORTAL_PREFIX + "/mine.json", mine),
            Route(PORTAL_PREFIX + "/select/{slug}", select),
            Route(PORTAL_PREFIX + "/create", create, methods=["POST"]),
            Mount(ASSETS_URL, app=StaticFiles(directory=STATIC_DIR)),
        ]
    )


def _format_time(moment: dt.datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M")
