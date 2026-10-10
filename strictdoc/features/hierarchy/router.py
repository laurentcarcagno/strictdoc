"""
Routes of the suspect links: a screen that lists them, the action that clears
one after review, and the action that takes the current state of every link as
reviewed (it creates the baseline).

The routes need the project option ``suspect_links`` (412 otherwise). The role
each route needs is in strictdoc/features/roles/route_roles.py.
"""

import os
from typing import Any, Callable, Dict, Iterator, List, Tuple

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from markupsafe import Markup
from starlette.responses import Response

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.hierarchy.resolve_action import (
    resolve_project_references,
)
from strictdoc.features.hierarchy.stats import compute_hierarchy_stats
from strictdoc.features.hierarchy.suspect import (
    Baseline,
    baseline_all,
    baseline_path,
    clear_link,
    iter_links,
    load_cached,
    suspect_fields,
    suspect_links,
    sync_new_links,
    uid_of,
)
from strictdoc.features.roles.roles import ROLE_AUTHOR, role_allows
from strictdoc.features.roles.router import get_principal
from strictdoc.helpers.exception import StrictDocException

HTTP_STATUS_PRECONDITION_FAILED = 412


def create_baseline_sync(
    project_config: ProjectConfig, get_index: Callable[[], Any]
) -> Callable[[], Iterator[None]]:
    """
    A dependency of the write routes: once a change succeeded, the links that
    it created get their baseline entry, and the links it removed lose theirs.
    Nothing happens before the baseline exists.
    """

    def sync() -> Iterator[None]:
        yield
        if not project_config.suspect_links:
            return
        path = baseline_path(project_config)
        if not os.path.isfile(path):
            return
        baseline = Baseline.load(path)
        if sync_new_links(
            get_index(), baseline, suspect_fields(project_config)
        ):
            baseline.save(path)

    return sync


def create_hierarchy_routers(
    *,
    project_config: ProjectConfig,
    get_index: Callable[[], Any],
    env: Any,
    write_document: Callable[[SDocDocument], None],
    rebuild: Callable[[], None],
) -> Tuple[APIRouter, APIRouter]:
    def require_feature() -> None:
        if not project_config.suspect_links:
            raise HTTPException(
                status_code=HTTP_STATUS_PRECONDITION_FAILED,
                detail="The suspect links are not activated "
                "(project option suspect_links).",
            )

    def require_hierarchy() -> None:
        if len(project_config.document_hierarchy) == 0:
            raise HTTPException(
                status_code=HTTP_STATUS_PRECONDITION_FAILED,
                detail="The project declares no document hierarchy "
                "(project option document_hierarchy).",
            )

    read_router = APIRouter()
    write_router = APIRouter()

    def find_link(child_uid: str, parent_uid: str) -> Tuple[SDocNode, SDocNode]:
        for child_, parent_ in iter_links(get_index()):
            if child_.reserved_uid == child_uid and (
                parent_.reserved_uid == parent_uid
            ):
                return child_, parent_
        raise HTTPException(status_code=404, detail="This link does not exist.")

    @read_router.get(
        "/suspect_links",
        response_class=Response,
        dependencies=[Depends(require_feature)],
    )
    def suspect_links_screen(request: Request) -> Response:
        path = baseline_path(project_config)
        has_baseline = os.path.isfile(path)
        groups: Dict[str, Dict[str, Any]] = {}
        if has_baseline:
            baseline = load_cached(path)
            for link_ in suspect_links(
                get_index(), baseline, suspect_fields(project_config)
            ):
                parent_uid = uid_of(link_.parent)
                group = groups.setdefault(
                    parent_uid, {"parent": link_.parent, "children": []}
                )
                group["children"].append(link_.child)
        for group in groups.values():
            group["children"].sort(key=lambda node_: node_.reserved_uid)
        role = get_principal(request).role
        output = Markup(
            env()
            .get_template("features/hierarchy/suspect_links.jinja.html")
            .render(
                groups=[groups[key_] for key_ in sorted(groups)],
                has_baseline=has_baseline,
                can_clear=role_allows(role, ROLE_AUTHOR),
                can_baseline=role == "administrator",
                count=sum(len(g["children"]) for g in groups.values()),
            )
        )
        return HTMLResponse(content=output, status_code=200)

    @write_router.post(
        "/actions/suspect/clear",
        response_class=Response,
        dependencies=[Depends(require_feature)],
    )
    def clear(
        child_uid: str = Form(...), parent_uid: str = Form(...)
    ) -> Response:
        child, parent = find_link(child_uid, parent_uid)
        path = baseline_path(project_config)
        baseline = Baseline.load(path)
        clear_link(baseline, child, parent, suspect_fields(project_config))
        baseline.save(path)
        return RedirectResponse("/suspect_links", status_code=303)

    @write_router.post(
        "/actions/suspect/baseline",
        response_class=Response,
        dependencies=[Depends(require_feature)],
    )
    def baseline_everything() -> Response:
        path = baseline_path(project_config)
        baseline = Baseline()
        baseline_all(get_index(), baseline, suspect_fields(project_config))
        baseline.save(path)
        return RedirectResponse("/suspect_links", status_code=303)

    @read_router.get(
        "/hierarchy",
        response_class=Response,
        dependencies=[Depends(require_hierarchy)],
    )
    def hierarchy_screen() -> Response:
        suspect_children: List[str] = []
        if project_config.suspect_links:
            path = baseline_path(project_config)
            if os.path.isfile(path):
                suspect_children = [
                    uid_of(link_.child)
                    for link_ in suspect_links(
                        get_index(),
                        load_cached(path),
                        suspect_fields(project_config),
                    )
                ]
        stats = compute_hierarchy_stats(
            get_index(), project_config.hierarchy_levels, suspect_children
        )
        output = Markup(
            env()
            .get_template("features/hierarchy/hierarchy.jinja.html")
            .render(stats=stats, suspect_links=project_config.suspect_links)
        )
        return HTMLResponse(content=output, status_code=200)

    @write_router.post(
        "/actions/hierarchy/resolve_references", response_class=Response
    )
    def resolve_references(apply: bool = Form(False)) -> Response:
        try:
            report = resolve_project_references(
                traceability_index=get_index(),
                project_config=project_config,
                write_document=write_document,
                apply=apply,
            )
        except StrictDocException as exception_:
            raise HTTPException(
                status_code=400, detail=str(exception_)
            ) from exception_
        if apply and report.documents_changed:
            rebuild()
        return Response(
            content=report.format() + "\n",
            media_type="text/plain; charset=utf-8",
        )

    return read_router, write_router
