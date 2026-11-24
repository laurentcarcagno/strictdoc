"""
Who acts in the server of a project: the signed-in user, with the role that
the catalog gives on that project.

The role is read in the catalog each time the user opens the project and kept
here. The server of the project asks for the principal at each request, with
the function of create_provider().

@relation(SDOC-SRS-1236, scope=file)
@relation(SDOC-SRS-1237, scope=file)
@relation(SDOC-SRS-1238, scope=file)
@relation(SDOC-SRS-1241, scope=file)
"""

import threading
from typing import Dict, Optional, Tuple

from strictdoc.features.desktop.commit_author import create_author_provider
from strictdoc.features.desktop.git_access import create_git_access
from strictdoc.features.desktop.project_servers import ProjectIdentity
from strictdoc.features.desktop.token_store import TokenKeeper
from strictdoc.features.project_catalog.catalog import CatalogRole
from strictdoc.features.roles.principal import Principal, PrincipalProvider


class ProjectPrincipals:
    """
    The roles of the signed-in user, per project. A role belongs to a user: it
    is kept under the user name and the project, and every change of the
    session (the end of it, a refusal of GitLab, a new sign-in) forgets all of
    them. A server of a project that stays open never gives the role of the
    user who left to the user who came.
    """

    def __init__(self, keeper: TokenKeeper) -> None:
        self._keeper: TokenKeeper = keeper
        self._roles: Dict[Tuple[str, str], CatalogRole] = {}
        self._lock: threading.Lock = threading.Lock()
        keeper.add_session_listener(self.clear)

    def clear(self) -> None:
        """Forget every role."""
        with self._lock:
            self._roles.clear()

    def set_role(self, identifier: str, role: Optional[CatalogRole]) -> None:
        """
        Remember the role that the catalog gives to the signed-in user on the
        project. None when the user cannot see the project any more: its server
        then refuses every request. Nothing is kept when nobody is signed in.
        """
        session = self._keeper.session
        if session is None:
            return
        key = (session.user.username, identifier)
        with self._lock:
            if role is None:
                self._roles.pop(key, None)
            else:
                self._roles[key] = role

    def get_role(self, identifier: str) -> Optional[str]:
        """
        The role of the signed-in user in the project, as a name ("reader",
        "author", "administrator"), or None when nobody is signed in or the
        role is not known: the project was not opened in this session.
        """
        session = self._keeper.session
        if session is None:
            return None
        with self._lock:
            role = self._roles.get((session.user.username, identifier))
        return role.value if role is not None else None

    def create_identity(self, identifier: str) -> ProjectIdentity:
        """The principal and the author of the commits of a project server."""
        return ProjectIdentity(
            principal_provider=self.create_provider(identifier),
            author_provider=create_author_provider(self._keeper),
            git_access=create_git_access(self._keeper),
        )

    def create_provider(self, identifier: str) -> PrincipalProvider:
        """
        The function that the server of the project calls: the principal of the
        user, or None when nobody is signed in or the user has no role on the
        project.
        """

        def provide() -> Optional[Principal]:
            session = self._keeper.session
            if session is None:
                return None
            with self._lock:
                role = self._roles.get((session.user.username, identifier))
            if role is None:
                return None
            return Principal(
                user=session.user.username,
                subject=session.user.username,
                email=session.user.email,
                authenticated=True,
                role=role.value,
            )

        return provide
