"""
Creates folders from the project view: "New folder" in the menu of the project
index. The role each route needs is in strictdoc/features/roles/route_roles.py.
"""

import os
from typing import List, Optional, Tuple

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.responses import Response

from strictdoc.core.document_tree import DocumentTree
from strictdoc.features.folders.folders import (
    blocking_files,
    create_folder,
    delete_folder,
    folder_paths,
    move_document,
    move_folder,
    rename_folder,
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

    def root_path() -> str:
        config = context.project_config
        assert isinstance(config.input_paths, list)
        return os.path.abspath(config.input_paths[0])

    def output_files_under(relative_path: str) -> List[str]:
        """The generated pages of the documents that are in a path."""
        base = os.path.realpath(os.path.join(root_path(), relative_path))
        tree = assert_cast(
            context.export_action.traceability_index.document_tree,
            DocumentTree,
        )
        found: List[str] = []
        for document_ in tree.document_list:
            meta = document_.meta
            assert meta is not None
            full = os.path.realpath(meta.input_doc_full_path)
            if full == base or full.startswith(base + os.sep):
                found.extend(
                    [
                        meta.get_html_doc_path(),
                        meta.get_html_table_path(),
                        meta.get_html_traceability_path(),
                        meta.get_html_deep_traceability_path(),
                        meta.get_html_pdf_path(),
                    ]
                )
        return found

    def rebuild(stale: List[str]) -> None:
        for path_ in stale:
            try:
                if os.path.exists(path_):
                    os.remove(path_)
            except OSError:
                continue
        context.export_action.build_index()
        context.export_action.export()

    def changed(moved_from: str = "", moved_to: str = "") -> HTMLResponse:
        output = context.env().render_template_as_markup(
            "features/folders/stream_folder_changed.jinja.html",
            moved_from=moved_from,
            moved_to=moved_to,
        )
        return HTMLResponse(content=output, headers=_STREAM)

    def rename_form(path: str, new_name: str, error: Optional[str] = None):
        error_object = ErrorObject()
        if error:
            error_object.add_error("new_name", error)
        output = context.env().render_template_as_markup(
            "features/folders/stream_rename_folder.jinja.html",
            error_object=error_object,
            path=path,
            new_name=new_name,
        )
        return HTMLResponse(content=output, headers=_STREAM)

    @read_router.get(
        "/actions/project_index/rename_folder", response_class=Response
    )
    def rename_folder_form(path: str = "") -> Response:
        return rename_form(path, os.path.basename(path.strip("/")))

    @write_router.post(
        "/actions/project_index/rename_folder", response_class=Response
    )
    def rename(path: str = Form(""), new_name: str = Form("")) -> Response:
        try:
            stale = output_files_under(path.strip("/"))
            new_path = rename_folder(root_path(), path, new_name)
        except StrictDocException as exception_:
            return rename_form(path, new_name, str(exception_))
        rebuild(stale)
        return changed(path.strip("/"), new_path)

    @write_router.post("/actions/project_index/move", response_class=Response)
    def move(source: str = Form(""), destination: str = Form("")) -> Response:
        """A document or a folder dragged to a folder of the tree."""
        try:
            stale = output_files_under(source.strip("/"))
            if source.strip("/").endswith(".sdoc"):
                new_path = move_document(root_path(), source, destination)
            else:
                new_path = move_folder(root_path(), source, destination)
        except StrictDocException as exception_:
            return JSONResponse({"error": str(exception_)}, status_code=422)
        rebuild(stale)
        return JSONResponse(
            {"ok": True, "from": source.strip("/"), "to": new_path}
        )

    @write_router.delete(
        "/actions/project_index/delete_folder", response_class=Response
    )
    def delete(path: str = "", confirmed: bool = False) -> Response:
        errors: List[str] = []
        try:
            errors = [
                f"{path.strip('/')}/{file_}"
                for file_ in blocking_files(root_path(), path)
            ]
            if confirmed and not errors:
                delete_folder(root_path(), path)
        except StrictDocException as exception_:
            errors = [str(exception_)]
        if confirmed and not errors:
            rebuild([])
            return changed()
        output = context.env().render_template_as_markup(
            "features/folders/stream_confirm_delete_folder.jinja.html",
            path=path.strip("/"),
            errors=errors,
        )
        return HTMLResponse(
            content=output,
            status_code=200 if not errors else 422,
            headers=_STREAM,
        )

    return read_router, write_router
