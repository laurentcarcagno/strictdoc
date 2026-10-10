"""
The portal: the page at the root host that lists the projects the user can
open, with the role the user has in each one.
"""

import datetime as dt
import os
from typing import Any, Dict, List, Mapping, Optional, Sequence

from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route

from strictdoc.features.projects.registry import ProjectSpec
from strictdoc.features.roles.principal import Principal
from strictdoc.features.roles.roles import ROLE_ADMINISTRATOR, resolve_role

_TEMPLATES = Environment(
    loader=FileSystemLoader(
        os.path.join(os.path.dirname(__file__), "templates")
    ),
    autoescape=select_autoescape(["html"]),
)


def role_in(
    spec: ProjectSpec, principal: Principal, proxy: bool
) -> Optional[str]:
    """The role of the user in a project. None: the project is not for them."""
    if not proxy:
        return ROLE_ADMINISTRATOR
    return resolve_role(principal.groups, spec.roles)


def create_portal(
    *,
    specs: Sequence[ProjectSpec],
    contexts: Mapping[str, Any],
    root_host: str,
    proxy: bool,
) -> Starlette:
    def home(request: Request) -> HTMLResponse:
        principal: Principal = request.scope["state"]["principal"]
        scheme = request.headers.get("x-forwarded-proto", "http")
        port = request.headers.get("host", "").partition(":")[2]
        rows: List[Dict[str, Any]] = []
        for spec_ in specs:
            role = role_in(spec_, principal, proxy)
            if role is None:
                continue
            context = contexts[spec_.slug]
            index = context.export_action.traceability_index
            rows.append(
                {
                    "title": spec_.title,
                    "slug": spec_.slug,
                    "role": role,
                    "archived": spec_.archived,
                    "documents": len(index.document_tree.document_list),
                    "last_change": _format_time(index.index_last_updated),
                    "url": f"{scheme}://{spec_.slug}.{root_host}"
                    + (f":{port}" if port else "")
                    + "/",
                }
            )
        page = _TEMPLATES.get_template("portal.jinja.html").render(
            rows=rows, user=principal.user
        )
        return HTMLResponse(page)

    return Starlette(routes=[Route("/", home)])


def _format_time(moment: dt.datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M")
