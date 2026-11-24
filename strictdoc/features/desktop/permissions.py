"""
What a role may do with the sharing of a project, in the desktop application.

This is the one place that says it. A service of roles will replace it: the
rest of the application asks these functions and never reads a role itself.

@relation(SDOC-SRS-1242, scope=file)
@relation(SDOC-SRS-1243, scope=file)
@relation(SDOC-SRS-1250, scope=file)
"""

from typing import Dict, Optional, Tuple

from strictdoc.features.roles.roles import (
    ROLE_ADMINISTRATOR,
    ROLE_AUTHOR,
    ROLE_READER,
    role_allows,
)

RouteKey = Tuple[str, str]


def can_send(role: Optional[str]) -> bool:
    """
    True when a user with this role sends the changes of a project to the
    server: an author and an administrator do, a reader does not (a reader
    receives the updates and sends nothing).

    A role that is not known, for a project that is not open, does not stop
    the sending: the server of the project decides, and its refusal is shown.
    """
    if role is None:
        return True
    return role_allows(role, ROLE_AUTHOR)


def can_commit(role: Optional[str]) -> bool:
    """
    True when the changes of a request that this role made go in a commit: the
    role of an author and above. A user who cannot send the commit and cannot
    move forward from it (a reader, a reviewer) makes none. A project of the
    simulated catalog has no role: its commits are made.
    """
    if role is None:
        return True
    return role_allows(role, ROLE_AUTHOR)


def can_update(role: Optional[str]) -> bool:
    """
    True when the user receives the changes of the others. Every role does: a
    reader follows the work of the others. What a reader does with a change
    that his own comments overlap is in project_sync.py.
    """
    del role
    return True


def can_resolve(role: Optional[str]) -> bool:
    """
    True when the user chooses between the versions of a document that two
    people changed, and when he puts the choice off for good (abandons it).
    For now an author does it too, and so does an administrator; a service of
    roles will decide.
    """
    if role is None:
        return True
    return role_allows(role, ROLE_AUTHOR)


def can_abandon(role: Optional[str]) -> bool:
    """True when the user abandons a merge that waits: as can_resolve."""
    return can_resolve(role)


def can_publish(role: Optional[str]) -> bool:
    """
    True when the user publishes a version of a document (the tag that every
    user then sees): an administrator.
    """
    if role is None:
        return True
    return role_allows(role, ROLE_ADMINISTRATOR)


def get_resolve_role() -> str:
    """The lowest role that can_resolve and can_abandon accept."""
    return ROLE_AUTHOR


def get_route_role_overrides() -> Dict[RouteKey, str]:
    """
    The roles that the routes of the synchronization need in the desktop
    application, where the table of the roles of the web server says
    "administrator". The server of the application gives them to its role
    middleware; the web server never reads them, so its rules do not change.
    """
    resolve_role = get_resolve_role()
    return {
        ("POST", "/actions/git/sync"): ROLE_READER,
        ("POST", "/actions/git/sync/resolve"): resolve_role,
        ("POST", "/actions/git/sync/abort"): resolve_role,
        ("GET", "/actions/git/sync_conflicts"): resolve_role,
    }
