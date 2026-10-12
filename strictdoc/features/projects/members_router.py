"""
The members page of a project: the administrator of the project adds people
by their user name, gives them a role and removes them. Everything here needs
the administrator role (strictdoc/features/roles/route_roles.py).

The roles: reader (reads every document), reviewer (reads, and comments on
every document), author (writes documents and names the reviewers of the
ones they create), administrator (also manages the members).
"""

from typing import List, Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response

from strictdoc.features.projects.directory import DirectoryError, DirectoryUser
from strictdoc.features.projects.manager import ProjectMembers
from strictdoc.features.projects.portal import (
    TEMPLATES,
    same_origin,
    shell_context,
)
from strictdoc.features.roles.roles import ROLES
from strictdoc.helpers.exception import StrictDocException


def create_members_router(
    members: ProjectMembers, title: str, assets_url: str = "/_static"
) -> APIRouter:
    router = APIRouter()

    def page(
        request: Request, error: Optional[str] = None, status: int = 200
    ) -> HTMLResponse:
        suggestions: List[DirectoryUser] = []
        directory_note = ""
        if members.directory is not None:
            try:
                suggestions = list(members.directory.users())
                directory_note = (
                    "Start typing: the accounts of the login server are "
                    "suggested, and only they are accepted."
                )
            except DirectoryError:
                directory_note = (
                    "The login server does not answer: type the user name "
                    "by hand, it is not checked."
                )
        output = TEMPLATES.get_template("members.jinja.html").render(
            title=title,
            rows=list(members.listing().items()),
            roles=ROLES,
            suggestions=suggestions,
            directory_note=directory_note,
            error=error,
            **shell_context(request, role="administrator", assets=assets_url),
        )
        return HTMLResponse(output, status_code=status)

    @router.get("/members", response_class=HTMLResponse)
    def show(request: Request) -> HTMLResponse:
        return page(request)

    @router.post("/actions/members/set", response_class=Response)
    def set_member(
        request: Request, user: str = Form(...), role: str = Form(...)
    ) -> Response:
        if not same_origin(request):
            return HTMLResponse("<h1>403</h1>", status_code=403)
        try:
            if members.directory is not None:
                try:
                    known = members.directory.has(user)
                except DirectoryError:
                    known = True  # Keycloak is down: the name is not checked.
                if not known:
                    return page(
                        request,
                        f"'{user.strip()}' is not an account of the login "
                        "server.",
                        422,
                    )
            members.set(user, role)
        except StrictDocException as exception_:
            return page(request, str(exception_), 422)
        return RedirectResponse("/members", 303)

    @router.post("/actions/members/remove", response_class=Response)
    def remove_member(request: Request, user: str = Form(...)) -> Response:
        if not same_origin(request):
            return HTMLResponse("<h1>403</h1>", status_code=403)
        members.remove(user)
        return RedirectResponse("/members", 303)

    return router
