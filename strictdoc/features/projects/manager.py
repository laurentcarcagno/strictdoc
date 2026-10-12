"""
The projects of a running server: the ones of the registry file plus the ones
that administrators create from the portal, and the members of each.

A project that an administrator creates is a folder under the data root with
a small strictdoc.toml; its application is built at once, added to the
dispatcher and its lifespan started, so no restart is needed.

Who is administrator of the whole server: the platform administrator groups
(STRICTDOC_PLATFORM_ADMINS; default: the groups that are administrators of
every project of the registry). They may create projects and are
administrator in each one. Anybody else has the
role that the member list of a project gives them, or that the groups of the
project give them (registry projects).
"""

import datetime as dt
import os
from typing import Any, Callable, Dict, List, Optional, Sequence

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from strictdoc.features.i18n.i18n import gettext
from strictdoc.features.projects.directory import KeycloakDirectory
from strictdoc.features.projects.dispatcher import ProjectDispatcher
from strictdoc.features.projects.registry import (
    SLUG_PATTERN,
    ProjectSpec,
    build_project_config,
)
from strictdoc.features.projects.store import ProjectStore
from strictdoc.features.roles.principal import Principal
from strictdoc.features.roles.roles import (
    ROLE_ADMINISTRATOR,
    ROLE_READER,
    ROLES,
    resolve_role,
    role_rank,
)
from strictdoc.helpers.exception import StrictDocException

DEFAULT_FEATURES = (
    "TABLE_SCREEN",
    "TRACEABILITY_SCREEN",
    "DEEP_TRACEABILITY_SCREEN",
    "SEARCH",
    "DOCX",
    "COMMENTS",
)

# A group that nobody has: a project with no groups of its own still needs one
# role entry behind a login proxy.
NO_GROUP = "__members_only__"


class ProjectMembers:
    """The member list of one project, as the project application sees it."""

    def __init__(
        self,
        store: ProjectStore,
        slug: str,
        directory: Optional[KeycloakDirectory] = None,
    ) -> None:
        self._store = store
        self.slug = slug
        # The users of the login server, when the deployment gives access.
        self.directory = directory

    def role_of(self, user: str) -> Optional[str]:
        return self._store.role_of(self.slug, user)

    def is_member(self, user: str) -> bool:
        return self.role_of(user) is not None

    def listing(self) -> Dict[str, str]:
        return dict(sorted(self._store.members(self.slug).items()))

    def set(self, user: str, role: str) -> None:
        self._store.set_member(self.slug, user, role)

    def remove(self, user: str) -> bool:
        return self._store.remove_member(self.slug, user)


class ProjectManager:
    def __init__(
        self,
        *,
        create_app: Callable[..., FastAPI],
        store: ProjectStore,
        specs: Sequence[ProjectSpec],
        output_root: str,
        audit_root: Optional[str],
        data_root: Optional[str],
        proxy: bool,
        features: Sequence[str] = DEFAULT_FEATURES,
        platform_admin_groups: Optional[Sequence[str]] = None,
        directory: Optional[KeycloakDirectory] = None,
    ) -> None:
        self._create_app = create_app
        self.store = store
        self.output_root = output_root
        self.audit_root = audit_root
        self.data_root = data_root
        self.proxy = proxy
        self.directory = directory
        self.features = list(features)
        self.specs: Dict[str, ProjectSpec] = {s_.slug: s_ for s_ in specs}
        self.static_slugs = set(self.specs)
        self.apps: Dict[str, FastAPI] = {}
        self.contexts: Dict[str, Any] = {}
        self.dispatcher: Optional[ProjectDispatcher] = None
        # Default: the groups that are administrators of every project of
        # the registry (one group per project does not make a platform
        # administrator).
        if platform_admin_groups is None:
            common = [
                set(spec_.roles.get(ROLE_ADMINISTRATOR, [])) for spec_ in specs
            ]
            platform_admin_groups = (
                sorted(set.intersection(*common)) if common else []
            )
        self.admin_groups: List[str] = list(platform_admin_groups)

    # -- roles --------------------------------------------------------------

    def is_platform_admin(self, principal: Principal) -> bool:
        if not self.proxy:
            return True
        return any(group_ in self.admin_groups for group_ in principal.groups)

    def role_in(self, slug: str, principal: Principal) -> Optional[str]:
        """The role of a user in a project. None: it is not for them."""
        if not self.proxy:
            return ROLE_ADMINISTRATOR
        spec = self.specs[slug]
        best = resolve_role(principal.groups, spec.roles)
        member = self.store.role_of(slug, principal.user)
        if member is not None and (
            best is None or role_rank(member) > role_rank(best)
        ):
            best = member
        if self.is_platform_admin(principal):
            best = ROLE_ADMINISTRATOR
        return best

    # -- projects -----------------------------------------------------------

    def spec_for_dynamic(self, slug: str, title: str) -> ProjectSpec:
        assert self.data_root is not None
        roles = (
            {ROLE_ADMINISTRATOR: list(self.admin_groups)}
            if len(self.admin_groups) > 0
            else {ROLE_READER: [NO_GROUP]}
        )
        return ProjectSpec(
            slug=slug,
            title=title,
            path=os.path.join(self.data_root, slug),
            roles=roles,
        )

    def build(self, spec: ProjectSpec) -> FastAPI:
        """The application of a project, with its member list."""
        config = build_project_config(
            spec,
            output_root=self.output_root,
            audit_root=self.audit_root,
            proxy=self.proxy,
        )
        members = ProjectMembers(self.store, spec.slug, self.directory)
        config.member_role = members.role_of
        config.members_admin = members
        app = self._create_app(project_config=config)
        self.specs[spec.slug] = spec
        self.apps[spec.slug] = app
        self.contexts[spec.slug] = app.state.project_context
        return app

    def load_stored_projects(self) -> None:
        """Builds the projects that administrators created earlier."""
        for slug_, info_ in sorted(self.store.projects().items()):
            if slug_ in self.specs:
                continue
            spec = self.spec_for_dynamic(slug_, info_.get("title", slug_))
            if os.path.isdir(spec.path):
                self.build(spec)

    def validate_new(self, slug: str, title: str) -> str:
        """The clean title of a new project. Raises StrictDocException."""
        if self.data_root is None:
            raise StrictDocException(
                gettext(
                    "Projects cannot be created: the server has no data root."
                )
            )
        if SLUG_PATTERN.match(slug) is None:
            raise StrictDocException(
                gettext(
                    "Invalid project name '%(name)s': use 1 to 32 characters "
                    "among lower case letters, digits and '-', not starting "
                    "or ending with '-'."
                )
                % {"name": slug}
            )
        if slug in self.specs or os.path.exists(
            os.path.join(self.data_root, slug)
        ):
            raise StrictDocException(
                gettext("The project '%(name)s' already exists.")
                % {"name": slug}
            )
        clean_title = " ".join(title.split())
        if len(clean_title) == 0 or len(clean_title) > 120:
            raise StrictDocException(
                gettext("The title of a project has 1 to 120 characters.")
            )
        if '"' in clean_title or "\\" in clean_title:
            raise StrictDocException(
                gettext("The title of a project has no quote or backslash.")
            )
        return clean_title

    async def create_project(
        self, slug: str, title: str, creator: str
    ) -> ProjectSpec:
        """
        Creates the folder, the application and the first member (the
        creator, as administrator) of a project and starts it.
        """
        clean_title = self.validate_new(slug, title)
        assert self.data_root is not None
        folder = os.path.join(self.data_root, slug)
        os.makedirs(folder)
        features = ", ".join(f'"{name_}"' for name_ in self.features)
        with open(
            os.path.join(folder, "strictdoc.toml"), "w", encoding="utf8"
        ) as file_:
            file_.write(
                f'[project]\ntitle = "{clean_title}"\nfeatures = [{features}]\n'
            )
        spec = self.spec_for_dynamic(slug, clean_title)
        self.store.add_project(
            slug,
            clean_title,
            creator,
            dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        )
        if creator and creator != "anonymous":
            self.store.set_member(slug, creator, ROLE_ADMINISTRATOR)
        app = await run_in_threadpool(self.build, spec)
        if self.dispatcher is not None:
            await self.dispatcher.add_project(slug, app)
        return spec


def role_names() -> Sequence[str]:
    return ROLES
