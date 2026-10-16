"""
The synchronization of a project: pull, then push, and the view where the
conflicts of a merge are solved. See sync_service.py for the logic.
"""

import json
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from markupsafe import Markup
from starlette.responses import Response

from strictdoc.export.html.document_type import DocumentType
from strictdoc.export.html.renderers.link_renderer import LinkRenderer
from strictdoc.export.html.renderers.markup_renderer import MarkupRenderer
from strictdoc.features.git_config.git_service import GitServiceError
from strictdoc.features.git_sync.blocks import split_blocks
from strictdoc.features.git_sync.fragments import (
    build_rows,
    count_conflicts,
    header_of,
)
from strictdoc.features.git_sync.sync_service import (
    CONFLICTS,
    ERROR,
    MERGED,
    PULLED,
    SyncResult,
    SyncService,
)
from strictdoc.helpers.exception import StrictDocException
from strictdoc.server.project_context import ProjectContext

HTTP_BAD_REQUEST = 400
HTTP_PRECONDITION_FAILED = 412
HTTP_SEE_OTHER = 303


def create_git_sync_routers(
    *, context: ProjectContext
) -> Tuple[APIRouter, APIRouter]:
    config = context.project_config

    def require_feature() -> None:
        if not config.is_activated_git() or context.git_committer is None:
            raise HTTPException(
                status_code=HTTP_PRECONDITION_FAILED,
                detail="Configuration management is not activated (project "
                "feature GIT and option git, inside a Git repository).",
            )

    read_router = APIRouter(dependencies=[Depends(require_feature)])
    write_router = APIRouter(dependencies=[Depends(require_feature)])

    def sync_service() -> SyncService:
        committer = context.git_committer
        assert committer is not None and config.git is not None
        return SyncService(
            committer.service, config.git, committer.author_provider()
        )

    def rebuild() -> str:
        """Reads the documents again; "" or why the project does not build."""
        try:
            context.export_action.build_index()
            context.export_action.export()
        except StrictDocException as error:
            return str(error)
        return ""

    def page(
        message: str = "",
        result: Optional[SyncResult] = None,
        status: int = 200,
    ) -> Response:
        service = sync_service()
        waiting = service.service.merge_in_progress(service.root)
        output = context.env().render_template_as_markup(
            "features/git_sync/status.jinja.html",
            message=message,
            result=result,
            waiting=waiting,
            conflicts=service.conflict_paths() if waiting else [],
            has_remote=service.service.has_remote(service.root),
        )
        return HTMLResponse(content=output, status_code=status)

    def conflict_url(relative: str) -> str:
        return f"/git/sync/conflicts?file={relative}"

    @read_router.get("/git/sync", response_class=HTMLResponse)
    def sync_page() -> Response:
        return page()

    @write_router.post("/actions/git/sync", response_class=HTMLResponse)
    def sync() -> Response:
        assert context.git_committer is not None
        context.git_committer.flush()
        service = sync_service()
        result = service.sync()
        if result.status == CONFLICTS and result.conflicts:
            return RedirectResponse(
                conflict_url(result.conflicts[0]), status_code=HTTP_SEE_OTHER
            )
        if result.status in (PULLED, MERGED):
            rebuild()
        return page(result=result)

    def field_renderer() -> Any:
        renderers: Dict[Optional[str], MarkupRenderer] = {}

        def render(markup: Optional[str], field: Any) -> Markup:
            if markup not in renderers:
                renderers[markup] = MarkupRenderer.create(
                    markup=markup,
                    traceability_index=context.export_action.traceability_index,
                    link_renderer=LinkRenderer(
                        root_path="", static_path=config.dir_for_sdoc_assets
                    ),
                    html_templates=context.html_templates,
                    config=config,
                    context_document=None,
                )
            return renderers[markup].render_node_field(
                DocumentType.DOCUMENT, field
            )

        return render

    @read_router.get("/git/sync/conflicts", response_class=HTMLResponse)
    def conflicts_view(file: str = "") -> Response:
        service = sync_service()
        if not service.service.merge_in_progress(service.root):
            return RedirectResponse("/git/sync", status_code=HTTP_SEE_OTHER)
        paths = service.conflict_paths()
        if file not in paths:
            if not paths:
                return RedirectResponse("/git/sync", status_code=HTTP_SEE_OTHER)
            return RedirectResponse(
                conflict_url(paths[0]), status_code=HTTP_SEE_OTHER
            )
        try:
            loaded = service.conflict_file(file)
        except StrictDocException as error:
            return page(str(error), status=HTTP_BAD_REQUEST)
        rows = build_rows(
            loaded.regions,
            header_of(split_blocks(loaded.local_text)),
            header_of(split_blocks(loaded.server_text)),
            field_renderer(),
        )
        data = {
            str(row_.index): {
                "local": row_.local_text,
                "server": row_.server_text,
                "both": row_.both_text,
            }
            for row_ in rows
            if row_.kind == "conflict"
        }
        output = context.env().render_template_as_markup(
            "features/git_sync/conflicts.jinja.html",
            file=file,
            files=paths,
            rows=rows,
            conflict_count=count_conflicts(rows),
            branch=service.service.current_branch(service.root),
            data_json=json.dumps(data),
            title=config.project_title,
        )
        return HTMLResponse(content=output)

    @write_router.post("/actions/git/sync/resolve")
    def resolve(file: str = Form(""), texts: str = Form("{}")) -> Response:
        """The text of each conflict of a document (JSON: region -> text)."""
        service = sync_service()
        try:
            chosen: Dict[int, str] = {
                int(key_): str(value_)
                for key_, value_ in json.loads(texts).items()
            }
            service.resolve(file, chosen)
            remaining = service.conflict_paths()
            if remaining:
                return JSONResponse(
                    {"ok": True, "next": conflict_url(remaining[0])}
                )
            result = service.complete()
        except (StrictDocException, GitServiceError, ValueError) as error:
            return JSONResponse({"error": str(error)}, status_code=422)
        problem = rebuild()
        if result.status == ERROR or problem:
            return JSONResponse(
                {
                    "ok": True,
                    "next": "/git/sync",
                    "warning": result.message or problem,
                }
            )
        return JSONResponse({"ok": True, "next": "/git/sync"})

    @write_router.post("/actions/git/sync/abort")
    def abort() -> Response:
        service = sync_service()
        try:
            service.abort()
        except GitServiceError as error:
            return page(str(error), status=HTTP_BAD_REQUEST)
        rebuild()
        return RedirectResponse("/git/sync", status_code=HTTP_SEE_OTHER)

    return read_router, write_router
