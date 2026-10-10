"""
Word import and export dialogs of the web interface.

The routes are only reachable when the DOCX project feature is activated.
The dialogs are modals in the style of the ReqIF import. A preview shows
the same report as the command line and writes nothing.
"""

import os
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from starlette.responses import HTMLResponse, Response

from strictdoc.backend.docx.docx_web_service import (
    DOCX_MEDIA_TYPE,
    attach_meta,
    export_fresh,
    export_update,
    import_upload,
    safe_stem,
)
from strictdoc.backend.docx.import_.docx_reader import TrackedChangesMode
from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.core.project_config import ProjectConfig
from strictdoc.export.html.html_templates import JinjaEnvironment
from strictdoc.features.export.export_action import ExportAction
from strictdoc.features.project_index.view_object import (
    ProjectTreeViewObject,
)
from strictdoc.helpers.exception import StrictDocException

HTTP_STATUS_PRECONDITION_FAILED = 412
HTTP_STATUS_UNPROCESSABLE = 422
TURBO_STREAM_HEADERS = {"Content-Type": "text/vnd.turbo-stream.html"}


def create_docx_routers(
    *,
    project_config: ProjectConfig,
    export_action: ExportAction,
    env: Callable[[], JinjaEnvironment],
    write_document_to_file: Callable[[SDocDocument], None],
) -> Tuple[APIRouter, APIRouter]:
    """
    Returns the routes that only read and the routes that write. The caller
    includes them in its own read and write routers, which take the locks.
    """

    def require_feature() -> None:
        if not project_config.is_activated_docx():
            raise HTTPException(status_code=HTTP_STATUS_PRECONDITION_FAILED)

    read_router = APIRouter(dependencies=[Depends(require_feature)])
    write_router = APIRouter(dependencies=[Depends(require_feature)])

    def stream(
        template: str, status_code: int = 200, **context: object
    ) -> Response:
        output = env().render_template_as_markup(
            "features/docx/" + template, **context
        )
        return HTMLResponse(
            content=output,
            status_code=status_code,
            headers=TURBO_STREAM_HEADERS,
        )

    def report_stream(report_text: str) -> Response:
        return stream("stream_report.jinja.html", report_text=report_text)

    def error_stream(message: str) -> Response:
        return stream(
            "stream_report.jinja.html",
            status_code=HTTP_STATUS_UNPROCESSABLE,
            error=message,
        )

    def input_dir() -> str:
        assert isinstance(project_config.input_paths, list)
        return os.path.abspath(project_config.input_paths[0])

    def documents() -> List[SDocDocument]:
        return list(
            export_action.traceability_index.document_tree.document_list
        )

    def find_document(document_mid: str) -> Optional[SDocDocument]:
        for document_ in documents():
            if document_.reserved_mid == document_mid:
                return document_
        return None

    @read_router.get(
        "/actions/project_index/import_docx_form", response_class=Response
    )
    def get_import_docx_form() -> Response:
        return stream("stream_form_import_docx.jinja.html")

    @read_router.get(
        "/actions/project_index/export_docx_form", response_class=Response
    )
    def get_export_docx_form() -> Response:
        return stream(
            "stream_form_export_docx.jinja.html", documents=documents()
        )

    @read_router.post(
        "/actions/project_index/import_docx_preview", response_class=Response
    )
    def import_docx_preview(
        docx_file: UploadFile,
        tracked_changes: str = Form("accept"),
        overwrite: bool = Form(False),
    ) -> Response:
        try:
            result = import_upload(
                docx_file.file.read(),
                docx_file.filename,
                project_config,
                input_dir(),
                TrackedChangesMode(tracked_changes),
                overwrite,
            )
        except (StrictDocException, ValueError) as exception_:
            return error_stream(str(exception_))
        return report_stream(
            result.report.format() + "\n\nNothing was written."
        )

    @write_router.post(
        "/actions/project_index/import_docx", response_class=Response
    )
    def import_docx(
        docx_file: UploadFile,
        tracked_changes: str = Form("accept"),
        overwrite: bool = Form(False),
    ) -> Response:
        try:
            result = import_upload(
                docx_file.file.read(),
                docx_file.filename,
                project_config,
                input_dir(),
                TrackedChangesMode(tracked_changes),
                overwrite,
            )
        except (StrictDocException, ValueError) as exception_:
            return error_stream(str(exception_))

        Path(input_dir()).mkdir(parents=True, exist_ok=True)
        attach_meta(result.document, input_dir(), result.stem)
        write_document_to_file(result.document)

        export_action.build_index()
        export_action.export()

        view_object = ProjectTreeViewObject(
            traceability_index=export_action.traceability_index,
            project_config=project_config,
        )
        return stream(
            "stream_refresh_with_imported_docx.jinja.html",
            view_object=view_object,
        )

    async def read_base(base_file: Optional[UploadFile]) -> bytes:
        if base_file is None:
            return b""
        return await base_file.read()

    @read_router.post(
        "/actions/project_index/export_docx_preview", response_class=Response
    )
    async def export_docx_preview(
        document_mid: str = Form(""),
        base_file: Optional[UploadFile] = None,
    ) -> Response:
        document = find_document(document_mid)
        if document is None:
            return error_stream("Select a document.")
        base = await read_base(base_file)
        if len(base) == 0:
            return report_stream(
                "A new Word document will be built from the profile "
                "template.\nSelect a Word document to see what an update "
                "would change."
            )
        try:
            _, report = export_update(document, base, project_config)
        except StrictDocException as exception_:
            return error_stream(str(exception_))
        return report_stream(report.format() + "\n\nNothing was written.")

    @read_router.post("/docx/export", response_class=Response)
    async def export_docx(
        document_mid: str = Form(""),
        base_file: Optional[UploadFile] = None,
    ) -> Response:
        document = find_document(document_mid)
        if document is None:
            raise HTTPException(status_code=404)
        base = await read_base(base_file)
        assert document.meta is not None
        name = safe_stem(document.meta.document_filename_base)
        try:
            if len(base) == 0:
                content = export_fresh(document, project_config)
                file_name = f"{name}.docx"
            else:
                content, _ = export_update(document, base, project_config)
                file_name = f"{name}_updated.docx"
        except StrictDocException as exception_:
            return Response(
                content=str(exception_),
                status_code=HTTP_STATUS_UNPROCESSABLE,
                media_type="text/plain",
            )
        return Response(
            content=content,
            status_code=200,
            media_type=DOCX_MEDIA_TYPE,
            headers={
                "Content-Disposition": f'attachment; filename="{file_name}"',
            },
        )

    return read_router, write_router
