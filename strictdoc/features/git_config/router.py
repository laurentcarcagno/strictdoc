"""
The page and the actions of the configuration management.

The repositories that an action works on are chosen by their path in the list
that the server builds, never by a path from the browser. A tag creates the
baseline: pending assets are committed first, then the tag is made, and pushed
when the option push_on_tag is on.
"""

import os
from typing import Tuple

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from markupsafe import Markup
from starlette.responses import Response

from strictdoc.features.git_config.config import GitConfig
from strictdoc.features.git_config.git_service import (
    Author,
    GitService,
    GitServiceError,
)
from strictdoc.features.git_config.gitlab_service import (
    GitLabService,
    GitLabServiceError,
)
from strictdoc.features.roles.roles import ROLE_ADMINISTRATOR
from strictdoc.features.roles.router import get_principal
from strictdoc.server.project_context import ProjectContext

HTTP_BAD_REQUEST = 400
HTTP_PRECONDITION_FAILED = 412
HTTP_SEE_OTHER = 303


def create_git_routers(
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

    def git_config() -> GitConfig:
        assert config.git is not None
        return config.git

    def service() -> GitService:
        assert context.git_committer is not None
        return context.git_committer.service

    def render(
        request: Request, message: str = "", status: int = 200
    ) -> Response:
        committer = context.git_committer
        assert committer is not None
        principal = get_principal(request)
        page = (
            context.env()
            .get_template("features/git_config/status.jinja.html")
            .render(
                repositories=service().describe_repositories(),
                pending=committer.pending_paths,
                warnings=committer.warnings,
                last_error=committer.last_error,
                message=message,
                can_administrate=principal.role in (None, ROLE_ADMINISTRATOR),
            )
        )
        return HTMLResponse(content=Markup(page), status_code=status)

    def repository_path(relative_path: str) -> str:
        known = [
            state.relative_path for state in service().describe_repositories()
        ]
        if relative_path not in known:
            raise HTTPException(
                status_code=HTTP_BAD_REQUEST, detail="Unknown repository."
            )
        return os.path.normpath(
            os.path.join(service().project_root, relative_path)
        )

    def author_of() -> Author:
        assert context.git_committer is not None
        return context.git_committer.author_provider()

    def redirect() -> Response:
        return RedirectResponse("/git", status_code=HTTP_SEE_OTHER)

    @read_router.get("/git", response_class=HTMLResponse)
    def git_page(request: Request) -> Response:
        return render(request)

    @write_router.post("/actions/git/commit_pending")
    def commit_pending() -> Response:
        assert context.git_committer is not None
        context.git_committer.flush()
        return redirect()

    @write_router.post("/actions/git/tag")
    def create_tag(
        request: Request,
        repository: str = Form(...),
        kind: str = Form(...),
    ) -> Response:
        assert context.git_committer is not None
        path = repository_path(repository)
        author = author_of()
        try:
            context.git_committer.flush()
            if kind == "draft":
                name = service().next_intermediate_tag(path)
            elif kind == "major":
                name = service().next_major_tag(path)
            else:
                raise HTTPException(
                    status_code=HTTP_BAD_REQUEST, detail="Unknown kind of tag."
                )
            service().create_tag(path, name, author)
            if git_config().push_on_tag:
                service().push(path, tag=name)
        except GitServiceError as error:
            return render(request, str(error), HTTP_BAD_REQUEST)
        return redirect()

    @write_router.post("/actions/git/push")
    def push(request: Request, repository: str = Form(...)) -> Response:
        path = repository_path(repository)
        try:
            service().push_with_submodules(path)
        except GitServiceError as error:
            return render(request, str(error), HTTP_BAD_REQUEST)
        return redirect()

    @write_router.post("/actions/git/create_repository")
    def create_repository(
        request: Request,
        group_path: str = Form(...),
        name: str = Form(...),
    ) -> Response:
        try:
            url = GitLabService(git_config()).create_repository(
                group_path, name
            )
        except GitLabServiceError as error:
            return render(request, str(error), HTTP_BAD_REQUEST)
        return render(request, f"Created: {url}")

    @write_router.post("/actions/git/submodule_add")
    def submodule_add(
        request: Request,
        url: str = Form(...),
        path: str = Form(...),
    ) -> Response:
        try:
            service().submodule_add(
                service().project_root, url, path, author_of()
            )
        except GitServiceError as error:
            return render(request, str(error), HTTP_BAD_REQUEST)
        return redirect()

    @write_router.post("/actions/git/submodule_update")
    def submodule_update(request: Request) -> Response:
        try:
            service().submodule_update(service().project_root)
        except GitServiceError as error:
            return render(request, str(error), HTTP_BAD_REQUEST)
        return redirect()

    return read_router, write_router
