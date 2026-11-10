"""
The versions of a document: the version tags of its repository at
/versions/{document_mid}, the items of the document as they were at a tag,
and the difference between two tags. The screens only read: nothing is
checked out and no file changes.

The routes need the project feature GIT (412 otherwise). The role each route
needs is in strictdoc/features/roles/route_roles.py.

@relation(SDOC-SRS-215, scope=file)
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from starlette.responses import Response

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.export.html.generators.view_objects.app_screen_view_object import (
    render_app_screen,
)
from strictdoc.features.document_versions.service import (
    compare_snapshots,
    read_snapshots,
)
from strictdoc.features.git_config.git_service import (
    GitService,
    GitServiceError,
)
from strictdoc.features.git_config.versioning import (
    InvalidVersionTag,
    parse_version_tag,
)
from strictdoc.features.i18n.i18n import gettext
from strictdoc.helpers.exception import StrictDocException
from strictdoc.helpers.mid import MID
from strictdoc.server.project_context import ProjectContext

HTTP_STATUS_PRECONDITION_FAILED = 412


def create_document_versions_router(*, context: ProjectContext) -> APIRouter:
    def require_feature() -> None:
        if (
            not context.project_config.is_activated_git()
            or context.git_committer is None
        ):
            raise HTTPException(
                status_code=HTTP_STATUS_PRECONDITION_FAILED,
                detail="Configuration management is not activated (project "
                "feature GIT and option git, inside a Git repository).",
            )

    router = APIRouter(dependencies=[Depends(require_feature)])

    def service() -> GitService:
        assert context.git_committer is not None
        return context.git_committer.service

    def find_document(document_mid: str) -> SDocDocument:
        index = context.export_action.traceability_index
        document = index.get_node_by_mid_weak(MID(document_mid))
        if not isinstance(document, SDocDocument):
            raise HTTPException(status_code=404, detail="Document not found.")
        return document

    def path_of(document: SDocDocument) -> str:
        assert document.meta is not None
        return document.meta.input_doc_full_path

    def check_tag(tag: str) -> str:
        try:
            parse_version_tag(tag)
        except InvalidVersionTag as error:
            raise HTTPException(
                status_code=404, detail="Version not found."
            ) from error
        return tag

    def snapshots_at(document: SDocDocument, tag: str) -> Dict[str, Any]:
        """The items at a tag, or the reason why they cannot be shown."""
        path = path_of(document)
        if not path.endswith(".sdoc"):
            return {
                "items": {},
                "error": gettext(
                    "Only the documents in the SDoc format can be shown at a "
                    "version."
                ),
            }
        try:
            text = service().text_at_tag(path, check_tag(tag))
        except GitServiceError as error:
            return {"items": {}, "error": str(error)}
        if text is None:
            return {
                "items": {},
                "error": gettext(
                    "The document does not exist at this version."
                ),
            }
        try:
            return {"items": read_snapshots(text), "error": ""}
        except StrictDocException as error:
            return {"items": {}, "error": str(error)}

    def screen(
        document: SDocDocument, template: str, **variables: object
    ) -> Response:
        output = render_app_screen(
            jinja_environment=context.env(),
            project_config=context.project_config,
            title=gettext("Versions"),
            viewtype="versions",
            content_template=f"features/document_versions/{template}",
            document=document,
            document_mid=document.reserved_mid.get_string_value(),
            **variables,
        )
        return HTMLResponse(content=output, status_code=200)

    @router.get("/versions/{document_mid}", response_class=Response)
    def versions_screen(document_mid: str) -> Response:
        document = find_document(document_mid)
        error = ""
        tags: List[Any] = []
        try:
            tags = service().version_tags_of(path_of(document))
        except GitServiceError as git_error:
            error = str(git_error)
        return screen(document, "versions.jinja.html", tags=tags, error=error)

    @router.get("/versions/{document_mid}/compare", response_class=Response)
    def compare_screen(
        document_mid: str, from_tag: str = "", to_tag: str = ""
    ) -> Response:
        document = find_document(document_mid)
        before = snapshots_at(document, from_tag)
        after = snapshots_at(document, to_tag)
        comparison: Optional[Any] = None
        error = before["error"] or after["error"]
        if error == "":
            comparison = compare_snapshots(before["items"], after["items"])
        return screen(
            document,
            "compare.jinja.html",
            from_tag=from_tag,
            to_tag=to_tag,
            comparison=comparison,
            error=error,
        )

    @router.get("/versions/{document_mid}/{tag}", response_class=Response)
    def version_screen(document_mid: str, tag: str) -> Response:
        document = find_document(document_mid)
        snapshot = snapshots_at(document, tag)
        return screen(
            document,
            "version.jinja.html",
            tag=tag,
            items=list(snapshot["items"].values()),
            error=snapshot["error"],
        )

    return router
