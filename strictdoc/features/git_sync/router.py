"""
The synchronization of a project: pull, then push, and the view where the
conflicts of a merge are solved. See sync_service.py for the logic.
"""

import json
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
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
    MERGED,
    PULLED,
    SyncResult,
    SyncService,
)
from strictdoc.features.roles.roles import ROLE_ADMINISTRATOR
from strictdoc.features.roles.router import get_principal
from strictdoc.helpers.exception import StrictDocException
from strictdoc.server.project_context import ProjectContext

HTTP_BAD_REQUEST = 400
HTTP_PRECONDITION_FAILED = 412


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

    def stream(template: str, **values: Any) -> Response:
        output = context.env().render_template_as_markup(
            f"features/git_sync/{template}", **values
        )
        return HTMLResponse(
            content=output,
            headers={"Content-Type": "text/vnd.turbo-stream.html"},
        )

    def dialog(
        request: Request,
        message: str = "",
        result: Optional[SyncResult] = None,
    ) -> Response:
        """The synchronization as a modal."""
        service = sync_service()
        waiting = service.service.merge_in_progress(service.root)
        principal = get_principal(request)
        return stream(
            "stream_sync.jinja.html",
            message=message,
            result=result,
            waiting=waiting,
            conflicts=service.conflict_paths() if waiting else [],
            has_remote=service.service.has_remote(service.root),
            can_sync=principal.role in (None, ROLE_ADMINISTRATOR),
        )

    def conflict_url(relative: str) -> str:
        return f"/actions/git/sync_conflicts?file={quote(relative)}"

    @read_router.get("/actions/git/sync_dialog", response_class=Response)
    def sync_dialog(
        request: Request,
        merged: bool = False,
        pushed: bool = False,
        note: str = "",
    ) -> Response:
        """The dialog; after the end of a merge it says how it ended."""
        result = (
            SyncResult(MERGED, message=note, pushed=pushed) if merged else None
        )
        return dialog(request, result=result)

    @write_router.post("/actions/git/sync", response_class=Response)
    def sync(request: Request) -> Response:
        assert context.git_committer is not None
        context.git_committer.flush()
        service = sync_service()
        result = service.sync()
        if result.status in (PULLED, MERGED):
            problem = rebuild()
            if problem:
                result.message = (result.message + " " + problem).strip()
        if result.status == CONFLICTS and result.conflicts:
            return conflicts_view(request, result.conflicts[0])
        return dialog(request, result=result)

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

    @read_router.get("/actions/git/sync_conflicts", response_class=Response)
    def conflicts_view(request: Request, file: str = "") -> Response:
        service = sync_service()
        if not service.service.merge_in_progress(service.root):
            return dialog(request)
        paths = service.conflict_paths()
        if file not in paths:
            if not paths:
                return dialog(request)
            file = paths[0]
        try:
            loaded = service.conflict_file(file)
        except StrictDocException as error:
            return dialog(request, str(error))
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
        return stream(
            "stream_conflicts.jinja.html",
            file=file,
            files=paths,
            rows=rows,
            conflict_count=count_conflicts(rows),
            branch=service.service.current_branch(service.root),
            data_json=json.dumps(data).replace("</", "<\\/"),
        )

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
        note = quote(result.message or problem)
        return JSONResponse(
            {
                "ok": True,
                "next": "/actions/git/sync_dialog?merged=1"
                f"&pushed={int(result.pushed)}&note={note}",
            }
        )

    @write_router.post("/actions/git/sync/abort", response_class=Response)
    def abort(request: Request) -> Response:
        service = sync_service()
        try:
            service.abort()
        except GitServiceError as error:
            return dialog(request, str(error))
        rebuild()
        return dialog(request)

    return read_router, write_router
