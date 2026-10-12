"""
The portal: the page at the root host that lists the projects the user can
open, with the role the user has in each one. A platform administrator also
creates projects here; the administrator of a project reaches its members
page from the list.
"""

import datetime as dt
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from strictdoc.features.projects.manager import ProjectManager
from strictdoc.features.roles.principal import Principal
from strictdoc.helpers.exception import StrictDocException

TEMPLATES = Environment(
    loader=FileSystemLoader(
        os.path.join(os.path.dirname(__file__), "templates")
    ),
    autoescape=select_autoescape(["html"]),
)


# The static files of StrictDoc (styles, fonts, nav.js): the portal serves
# them at /assets, the path that the projects use for theirs.
STATIC_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "export", "html", "_static"
)
ASSETS_URL = "/assets"
# Logs out of oauth2-proxy, which also ends the session of the login server
# (its --backend-logout-url).
LOGOUT_URL = "/oauth2/sign_out"


def portal_url(request: Request) -> str:
    """The portal, seen from a project host: <slug>.<root> gives <root>."""
    scheme = request.headers.get("x-forwarded-proto", "http")
    host = request.headers.get("host", "")
    root = host.partition(".")[2] or host
    return f"{scheme}://{root}/"


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
        "portal_url": portal_url(request),
    }


def same_origin(request: Request) -> bool:
    """False for a form posted from another site (the Origin header)."""
    origin = request.headers.get("origin")
    if origin is None:
        return True
    return urlsplit(origin).netloc == request.headers.get("host", "")


def create_portal(
    *,
    manager: ProjectManager,
    root_host: str,
) -> Starlette:
    def project_url(request: Request, slug: str) -> str:
        scheme = request.headers.get("x-forwarded-proto", "http")
        port = request.headers.get("host", "").partition(":")[2]
        return f"{scheme}://{slug}.{root_host}" + (f":{port}" if port else "")

    def page(
        request: Request,
        error: Optional[str] = None,
        slug: str = "",
        title: str = "",
        status_code: int = 200,
    ) -> HTMLResponse:
        principal: Principal = request.scope["state"]["principal"]
        rows: List[Dict[str, Any]] = []
        for slug_, spec_ in manager.specs.items():
            role = manager.role_in(slug_, principal)
            if role is None:
                continue
            index = manager.contexts[slug_].export_action.traceability_index
            rows.append(
                {
                    "title": spec_.title,
                    "slug": slug_,
                    "role": role,
                    "archived": spec_.archived,
                    "documents": len(index.document_tree.document_list),
                    "last_change": _format_time(index.index_last_updated),
                    "url": project_url(request, slug_) + "/",
                    "members_url": project_url(request, slug_) + "/members",
                }
            )
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
        return RedirectResponse(project_url(request, slug) + "/", 303)

    return Starlette(
        routes=[
            Route("/", home),
            Route("/projects/create", create, methods=["POST"]),
            Mount(ASSETS_URL, app=StaticFiles(directory=STATIC_DIR)),
        ]
    )


def _format_time(moment: dt.datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M")
