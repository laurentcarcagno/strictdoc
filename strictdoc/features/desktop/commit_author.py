"""
The author of the commits that the desktop application makes: the user who
signed in to GitLab.

The name is the name of the user in GitLab. The address is the first of these
that GitLab gave: the "email" of the user, then the "public_email", then the
"commit_email". A user who keeps every address private has none of them: the
author then takes the address that GitLab itself gives to such a user,
"<number>-<user name>@users.noreply.<host of GitLab>".

There is no default author in a project of the desktop application: the
author that the project configuration names (GitConfig) is never used there. A
commit, a tag or a merge asks the committer for its author, and the committer
holds one of these two functions: the one of the signed-in user, or the one
that refuses. Nobody signed in, or a server that was given no author function,
is a CommitAuthorError and nothing is committed.

@relation(SDOC-SRS-1238, scope=file)
"""

from typing import Callable
from urllib.parse import urlsplit

from fastapi import HTTPException

from strictdoc.features.desktop.oauth_gitlab import GitLabUser
from strictdoc.features.desktop.token_store import TokenKeeper
from strictdoc.features.git_config.git_service import Author, GitServiceError
from strictdoc.features.i18n.i18n import gettext


class CommitAuthorError(GitServiceError, HTTPException):
    """
    There is no author for the commit. It is a GitServiceError, which the
    committer and the Git routes report to the user; where a route does not
    catch it, it is also an HTTP 409 with the message.
    """

    def __init__(self, message: str) -> None:
        GitServiceError.__init__(self, message)
        HTTPException.__init__(self, status_code=409, detail=message)

    def __str__(self) -> str:
        return str(self.detail)


def get_commit_email(user: GitLabUser, gitlab_url: str) -> str:
    """The address of the user for the commits, never empty."""
    for address_ in (user.email, user.public_email, user.commit_email):
        if len(address_.strip()) > 0:
            return address_.strip()
    host = urlsplit(gitlab_url.strip()).hostname or "localhost"
    prefix = f"{user.user_id}-" if user.user_id > 0 else ""
    return f"{prefix}{user.username}@users.noreply.{host}"


def get_commit_author(user: GitLabUser, gitlab_url: str) -> Author:
    return Author(user.display_name, get_commit_email(user, gitlab_url))


def create_author_provider(keeper: TokenKeeper) -> Callable[[], Author]:
    """
    The function that gives the committer the author of a commit, at the time
    of the commit: the user who is signed in then.
    """

    def provide() -> Author:
        session = keeper.session
        if session is None:
            raise CommitAuthorError(
                gettext("Nobody is signed in: the commit has no author.")
            )
        return get_commit_author(session.user, keeper.gitlab_url)

    return provide


def create_missing_author_provider() -> Callable[[], Author]:
    """
    The function of a server of the desktop application that was given no
    author: it refuses, so that the author of the project configuration is
    never used.
    """

    def provide() -> Author:
        raise CommitAuthorError(
            gettext("The project has no author for its commits.")
        )

    return provide
