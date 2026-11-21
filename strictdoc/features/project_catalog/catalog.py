"""
The interface of a catalog of projects.

A catalog lists the projects that the user can open, with the role that the
user has on each of them. The screens depend on this interface only: a new
provider implements ProjectCatalog and registers itself under a name.

@relation(SDOC-SRS-1226, scope=file)
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Protocol


class CatalogRole(str, Enum):
    READER = "reader"
    AUTHOR = "author"
    ADMINISTRATOR = "administrator"


class CatalogError(Exception):
    """A catalog cannot list the projects. The message is for the user."""


@dataclass(frozen=True)
class CatalogProject:
    # Stable key of the project: the settings use it to remember the folder.
    identifier: str
    title: str
    # Path shown in the tree of the catalog, for example "Satellites/ISIS".
    display_path: str
    description: str
    clone_url: str
    role: CatalogRole


@dataclass(frozen=True)
class DesktopIdentity:
    username: str
    display_name: str


class ProjectCatalog(Protocol):
    def list_projects(
        self, identity: DesktopIdentity
    ) -> List[CatalogProject]: ...
