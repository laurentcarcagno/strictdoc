"""
Names the reviewers of a document. An author does it when creating the
document (the field of the form, see main_router) and here later on.

When the project has a member list, a reviewer must be a member.
"""

from html import escape
from typing import Optional, Tuple

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.features.reviewers.reviewers import (
    document_reviewers,
    parse_reviewers,
    set_document_reviewers,
    unknown_reviewers,
)
from strictdoc.helpers.mid import MID
from strictdoc.server.project_context import ProjectContext


def create_reviewers_routers(
    *, context: ProjectContext
) -> Tuple[APIRouter, APIRouter]:
    read_router = APIRouter()
    write_router = APIRouter()

    def find_document(document_mid: str) -> SDocDocument:
        node = context.export_action.traceability_index.get_node_by_mid_weak(
            MID(document_mid)
        )
        if not isinstance(node, SDocDocument):
            raise HTTPException(status_code=404, detail="Document not found.")
        return node

    def page(
        document: SDocDocument, text: str, error: Optional[str] = None
    ) -> HTMLResponse:
        members = context.project_config.members_admin
        hint = (
            "Members of the project: "
            + ", ".join(escape(name_) for name_ in members.listing())
            if members is not None
            else ""
        )
        message = (
            f"<p data-testid='reviewers-error' style='color:#b00020'>"
            f"{escape(error)}</p>"
            if error
            else ""
        )
        return HTMLResponse(
            "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'/>"
            "<title>Reviewers</title><style>body{font-family:sans-serif;"
            "margin:24px}</style></head><body>"
            f"<h1>Reviewers of {escape(document.title)}</h1>{message}"
            "<form method='post' action='/actions/reviewers/set' "
            "data-testid='reviewers-form'>"
            "<input type='hidden' name='document_mid' "
            f"value='{escape(document.reserved_mid.get_string_value())}'/>"
            f"<p><input name='reviewers' value='{escape(text)}' size='60' "
            "data-testid='reviewers-input'/></p>"
            "<p>User names, separated by commas. The reviewers may comment "
            f"on this document. {hint}</p>"
            "<button>Save</button></form>"
            "<p><a href='/'>Back to the documents</a></p></body></html>",
            status_code=200 if error is None else 422,
        )

    @read_router.get("/actions/reviewers/form", response_class=HTMLResponse)
    def form(document_mid: str) -> HTMLResponse:
        document = find_document(document_mid)
        return page(document, ", ".join(document_reviewers(document)))

    @write_router.post("/actions/reviewers/set", response_class=Response)
    def set_reviewers(
        document_mid: str = Form(...), reviewers: str = Form("")
    ) -> Response:
        document = find_document(document_mid)
        names = parse_reviewers(reviewers)
        members = context.project_config.members_admin
        unknown = unknown_reviewers(
            names, members.is_member if members is not None else None
        )
        if len(unknown) > 0:
            return page(
                document,
                reviewers,
                "Not members of the project: " + ", ".join(unknown) + ".",
            )
        set_document_reviewers(document, names)
        context.write_document_to_file(document)
        context.export_action.traceability_index.update_last_updated()
        assert document.meta is not None
        return RedirectResponse("/" + document.meta.get_html_doc_link(), 303)

    return read_router, write_router
