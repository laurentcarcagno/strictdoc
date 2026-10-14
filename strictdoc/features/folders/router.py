"""
Creates folders from the project view: "New folder" in the menu of the project
index. The role each route needs is in strictdoc/features/roles/route_roles.py.
"""

import os
from typing import List, Optional, Tuple

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse
from starlette.responses import Response

from strictdoc.core.document_tree import DocumentTree
from strictdoc.features.folders.folders import (
    create_folder,
    folder_paths,
)
from strictdoc.features.project_index.view_object import ProjectTreeViewObject
from strictdoc.helpers.cast import assert_cast
from strictdoc.helpers.exception import StrictDocException
from strictdoc.server.error_object import ErrorObject
from strictdoc.server.project_context import ProjectContext

_STREAM = {"Content-Type": "text/vnd.turbo-stream.html"}


def create_folders_routers(
    *, context: ProjectContext
) -> Tuple[APIRouter, APIRouter]:
    read_router = APIRouter()
    write_router = APIRouter()

    def existing_folders() -> List[str]:
        tree = assert_cast(
            context.export_action.traceability_index.document_tree,
            DocumentTree,
        )
        found: List[str] = []
        for file_tree_ in tree.file_tree:
            root = file_tree_.root_folder_or_file
            if root.is_folder():
                found.extend(folder_paths(root))  # type: ignore[arg-type]
        return found

    def form(
        folder_path: str = "", error: Optional[str] = None
    ) -> HTMLResponse:
        error_object = ErrorObject()
        if error:
            error_object.add_error("folder_path", error)
        output = context.env().render_template_as_markup(
            "features/folders/stream_new_folder.jinja.html",
            error_object=error_object,
            folder_path=folder_path,
            folders=existing_folders(),
        )
        return HTMLResponse(content=output, headers=_STREAM)

    @read_router.get(
        "/actions/project_index/new_folder", response_class=Response
    )
    def new_folder(parent: str = "") -> Response:
        # A right click on a folder of the tree gives its path.
        return form(parent.strip().strip("/") + "/" if parent.strip() else "")

    @write_router.post(
        "/actions/project_index/create_folder", response_class=Response
    )
    def create(folder_path: str = Form("")) -> Response:
        config = context.project_config
        assert isinstance(config.input_paths, list)
        try:
            create_folder(os.path.abspath(config.input_paths[0]), folder_path)
        except StrictDocException as exception_:
            return form(folder_path, str(exception_))
        context.export_action.build_index()
        context.export_action.export()
        view_object = ProjectTreeViewObject(
            traceability_index=context.export_action.traceability_index,
            project_config=config,
        )
        output = context.env().render_template_as_markup(
            "features/folders/stream_create_folder.jinja.html",
            view_object=view_object,
        )
        return HTMLResponse(content=output, headers=_STREAM)

    return read_router, write_router
