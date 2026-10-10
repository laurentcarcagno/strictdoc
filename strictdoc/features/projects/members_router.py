"""
The members page of a project: the administrator of the project adds people
by their user name, gives them a role and removes them. Everything here needs
the administrator role (strictdoc/features/roles/route_roles.py).

The roles: reader (reads every document), reviewer (reads, and comments on
every document), author (writes documents and names the reviewers of the
ones they create), administrator (also manages the members).
"""

from html import escape
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response

from strictdoc.features.projects.directory import DirectoryError
from strictdoc.features.projects.manager import ProjectMembers
from strictdoc.features.projects.portal import same_origin
from strictdoc.features.roles.roles import ROLES
from strictdoc.helpers.exception import StrictDocException


def create_members_router(members: ProjectMembers, title: str) -> APIRouter:
    router = APIRouter()

    def page(error: Optional[str] = None, status: int = 200) -> HTMLResponse:
        options = "".join(f"<option>{role_}</option>" for role_ in ROLES)
        suggestions = ""
        directory_note = ""
        if members.directory is not None:
            try:
                suggestions = "".join(
                    f"<option value='{escape(user_.username)}'>"
                    f"{escape(user_.label())}</option>"
                    for user_ in members.directory.users()
                )
                directory_note = (
                    "Start typing: the accounts of the login server are "
                    "suggested, and only they are accepted."
                )
            except DirectoryError:
                directory_note = (
                    "The login server does not answer: type the user name "
                    "by hand, it is not checked."
                )
        rows = ""
        for user_, role_ in members.listing().items():
            selected = "".join(
                f"<option{' selected' if r_ == role_ else ''}>{r_}</option>"
                for r_ in ROLES
            )
            rows += (
                "<tr data-testid='member-row'>"
                f"<td>{escape(user_)}</td>"
                "<td><form method='post' action='/actions/members/set'>"
                f"<input type='hidden' name='user' value='{escape(user_)}'/>"
                f"<select name='role'>{selected}</select> "
                "<button>Change</button></form></td>"
                "<td><form method='post' action='/actions/members/remove'>"
                f"<input type='hidden' name='user' value='{escape(user_)}'/>"
                "<button>Remove</button></form></td></tr>"
            )
        message = (
            f"<p data-testid='members-error' style='color:#b00020'>"
            f"{escape(error)}</p>"
            if error
            else ""
        )
        body = (
            "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'/>"
            f"<title>Members of {escape(title)}</title>"
            "<style>body{font-family:sans-serif;margin:24px}"
            "td,th{border:1px solid #ccc;padding:4px 8px;text-align:left}"
            "table{border-collapse:collapse}</style></head><body>"
            f"<h1>Members of {escape(title)}</h1>{message}"
            "<table data-testid='members-table'><tr><th>User</th>"
            f"<th>Role</th><th></th></tr>{rows}</table>"
            "<h2>Add a member</h2>"
            "<form method='post' action='/actions/members/set' "
            "data-testid='members-add'>"
            "<label>User name <input name='user' required "
            "list='directory-users' autocomplete='off'/></label> "
            f"<datalist id='directory-users'>{suggestions}</datalist> "
            f"<select name='role'>{options}</select> "
            "<button>Add</button></form>"
            f"<p data-testid='directory-note'>{directory_note}</p>"
            "<p>The user name is the one shown after the login "
            "(see <a href='/whoami'>/whoami</a>). Every member reads all "
            "the documents. The author of a document names its reviewers."
            "</p><p><a href='/'>Back to the documents</a></p>"
            "</body></html>"
        )
        return HTMLResponse(body, status_code=status)

    @router.get("/members", response_class=HTMLResponse)
    def show() -> HTMLResponse:
        return page()

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
                        f"'{user.strip()}' is not an account of the login "
                        "server.",
                        422,
                    )
            members.set(user, role)
        except StrictDocException as exception_:
            return page(str(exception_), 422)
        return RedirectResponse("/members", 303)

    @router.post("/actions/members/remove", response_class=Response)
    def remove_member(request: Request, user: str = Form(...)) -> Response:
        if not same_origin(request):
            return HTMLResponse("<h1>403</h1>", status_code=403)
        members.remove(user)
        return RedirectResponse("/members", 303)

    return router
