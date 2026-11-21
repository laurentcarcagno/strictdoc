"""
The catalog of the projects of a GitLab group.

The catalog receives a python-gitlab client that is already authenticated, so
the GitLab queries run with the rights of the user. It lists the projects of
the root group and of its sub-groups.

@relation(SDOC-SRS-1227, scope=file)
@relation(SDOC-SRS-1228, scope=file)
"""

from typing import Any, Dict, List, Tuple

from gitlab.exceptions import GitlabError

from strictdoc.features.project_catalog.catalog import (
    CatalogError,
    CatalogProject,
    CatalogRole,
    DesktopIdentity,
)

# GitLab access levels: Reporter 20, Developer 30, Maintainer 40, Owner 50.
# The query with a minimum level returns the projects at that level or above.
# They are asked from the highest role to the lowest: a project takes the role
# of the first query that returns it. A Guest (10) is in none of them.
_ROLE_QUERIES: Tuple[Tuple[int, CatalogRole], ...] = (
    (40, CatalogRole.ADMINISTRATOR),
    (30, CatalogRole.AUTHOR),
    (20, CatalogRole.READER),
)


class GitLabCatalog:
    def __init__(self, client: Any, root_group_path: str) -> None:
        self.client: Any = client
        self.root_group_path: str = root_group_path.strip("/")

    def list_projects(self, identity: DesktopIdentity) -> List[CatalogProject]:
        del identity
        try:
            group = self.client.groups.get(self.root_group_path)
            roles: Dict[int, CatalogRole] = {}
            projects: Dict[int, Any] = {}
            for minimum_access_level_, role_ in _ROLE_QUERIES:
                # get_all: GitLab returns 20 projects per page by default.
                for project_ in group.projects.list(
                    include_subgroups=True,
                    archived=False,
                    min_access_level=minimum_access_level_,
                    get_all=True,
                ):
                    if project_.id not in roles:
                        roles[project_.id] = role_
                        projects[project_.id] = project_
        except GitlabError as exception_:
            raise CatalogError(
                "GitLab cannot list the projects of the group "
                f"{self.root_group_path}: {exception_}"
            ) from exception_
        return sorted(
            (
                self._project_to_catalog_project(project_, roles[id_])
                for id_, project_ in projects.items()
            ),
            key=lambda project_: project_.display_path,
        )

    def _project_to_catalog_project(
        self, project: Any, role: CatalogRole
    ) -> CatalogProject:
        return CatalogProject(
            identifier=str(project.id),
            title=project.name,
            display_path=self._get_display_path(project.path_with_namespace),
            description=project.description or "",
            clone_url=project.http_url_to_repo,
            role=role,
        )

    def _get_display_path(self, path_with_namespace: str) -> str:
        """The path of a project under the root group, without that group."""
        prefix = self.root_group_path + "/"
        if path_with_namespace.startswith(prefix):
            return path_with_namespace[len(prefix) :]
        return path_with_namespace
