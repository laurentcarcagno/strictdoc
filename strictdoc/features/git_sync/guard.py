"""
While a merge waits for its conflicts to be solved, the files of the project
are the ones of the merge: a save from the document screens would end in the
merge commit. The write routes answer 423 until the merge is finished or
abandoned. The routes of the synchronization itself stay open.
"""

from typing import Awaitable, Callable

from fastapi import HTTPException, Request

from strictdoc.features.git_config.git_service import GitServiceError
from strictdoc.server.project_context import ProjectContext

HTTP_LOCKED = 423
SYNC_ROUTES = "/actions/git/"


def create_merge_guard(
    context: ProjectContext,
) -> Callable[[Request], Awaitable[None]]:
    async def guard(request: Request) -> None:
        committer = context.git_committer
        if committer is None or request.url.path.startswith(SYNC_ROUTES):
            return
        service = committer.service
        try:
            waiting = service.merge_in_progress(service.project_root)
        except GitServiceError:
            return
        if waiting:
            raise HTTPException(
                status_code=HTTP_LOCKED,
                detail=(
                    "A synchronization is waiting for its conflicts to be "
                    "solved (/git/sync): the project cannot be changed until "
                    "it is finished or abandoned."
                ),
            )

    return guard
