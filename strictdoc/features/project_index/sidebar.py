"""
The project tree of the sidebar: every screen of the server shows it under the
project picker, and its management (add a document or a folder, import and
export, edit the title) is in the menu of a right click on a node.

The tree is a fragment that the browser asks for (sidebar_tree.js), and that the
actions which change the tree (create a document or a folder, import) replace
in place, as they did for the tree of the Project index.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from starlette.responses import Response

from strictdoc.features.project_index.view_object import ProjectTreeViewObject
from strictdoc.server.project_context import ProjectContext


def create_sidebar_router(*, context: ProjectContext) -> APIRouter:
    router = APIRouter()

    @router.get("/fragments/project_tree", response_class=Response)
    def project_tree() -> Response:
        view_object = ProjectTreeViewObject(
            traceability_index=context.export_action.traceability_index,
            project_config=context.project_config,
        )
        output = context.env().render_template_as_markup(
            "features/project_index/sidebar_tree.jinja.html",
            view_object=view_object,
        )
        return HTMLResponse(content=output)

    return router
