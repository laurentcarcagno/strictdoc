"""
Who acts in the server of a project: the signed-in user, with the role that
the catalog gives on that project.

The role is read in the catalog each time the user opens the project and kept
here. The server of the project asks for the principal at each request, with
the function of create_provider().

@relation(SDOC-SRS-1236, scope=file)
@relation(SDOC-SRS-1237, scope=file)
@relation(SDOC-SRS-1238, scope=file)
"""

import threading
from typing import Dict, Optional

from strictdoc.features.desktop.commit_author import create_author_provider
from strictdoc.features.desktop.project_servers import ProjectIdentity
from strictdoc.features.desktop.token_store import TokenKeeper
from strictdoc.features.project_catalog.catalog import CatalogRole
from strictdoc.features.roles.principal import Principal, PrincipalProvider


class ProjectPrincipals:
    def __init__(self, keeper: TokenKeeper) -> None:
        self._keeper: TokenKeeper = keeper
        self._roles: Dict[str, CatalogRole] = {}
        self._lock: threading.Lock = threading.Lock()

    def set_role(self, identifier: str, role: Optional[CatalogRole]) -> None:
        """
        Remember the role that the catalog gives on the project. None when the
        user cannot see the project any more: its server then refuses every
        request.
        """
        with self._lock:
            if role is None:
                self._roles.pop(identifier, None)
            else:
                self._roles[identifier] = role

    def create_identity(self, identifier: str) -> ProjectIdentity:
        """The principal and the author of the commits of a project server."""
        return ProjectIdentity(
            principal_provider=self.create_provider(identifier),
            author_provider=create_author_provider(self._keeper),
        )

    def create_provider(self, identifier: str) -> PrincipalProvider:
        """
        The function that the server of the project calls: the principal of the
        user, or None when nobody is signed in or the user has no role on the
        project.
        """

        def provide() -> Optional[Principal]:
            session = self._keeper.session
            with self._lock:
                role = self._roles.get(identifier)
            if session is None or role is None:
                return None
            return Principal(
                user=session.user.username,
                subject=session.user.username,
                email=session.user.email,
                authenticated=True,
                role=role.value,
            )

        return provide
