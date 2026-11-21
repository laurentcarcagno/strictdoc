"""
The providers of a catalog, registered by name.

The settings of the desktop application name the provider. A new provider
registers a factory under a name and the rest of the application stays as it
is.

@relation(SDOC-SRS-1226, scope=file)
"""

from typing import Any, Callable, Dict, List, Optional

from strictdoc.features.desktop.settings import DesktopSettings
from strictdoc.features.project_catalog.catalog import (
    CatalogError,
    ProjectCatalog,
)
from strictdoc.features.project_catalog.fake_catalog import FakeCatalog
from strictdoc.features.project_catalog.gitlab_catalog import GitLabCatalog

# A factory receives the settings and the GitLab client, if there is one yet.
CatalogFactory = Callable[[DesktopSettings, Optional[Any]], ProjectCatalog]

FAKE_PROVIDER_NAME = "fake"
GITLAB_PROVIDER_NAME = "gitlab"


class UnknownCatalogProviderError(CatalogError):
    pass


def register_catalog_provider(name: str, factory: CatalogFactory) -> None:
    _FACTORIES[name] = factory


def get_catalog_provider_names() -> List[str]:
    return sorted(_FACTORIES)


def create_catalog(
    settings: DesktopSettings, gitlab_client: Optional[Any] = None
) -> ProjectCatalog:
    """Create the catalog that the settings name."""
    factory = _FACTORIES.get(settings.catalog_provider)
    if factory is None:
        raise UnknownCatalogProviderError(
            f"Unknown catalog provider '{settings.catalog_provider}'. "
            f"Available providers: {', '.join(get_catalog_provider_names())}."
        )
    return factory(settings, gitlab_client)


def _create_fake_catalog(
    settings: DesktopSettings, gitlab_client: Optional[Any]
) -> ProjectCatalog:
    del gitlab_client
    if len(settings.fake_catalog_path) == 0:
        raise CatalogError(
            "The provider 'fake' needs the setting fake_catalog_path."
        )
    return FakeCatalog(settings.fake_catalog_path)


def _create_gitlab_catalog(
    settings: DesktopSettings, gitlab_client: Optional[Any]
) -> ProjectCatalog:
    if gitlab_client is None:
        raise CatalogError("The provider 'gitlab' needs a GitLab connection.")
    return GitLabCatalog(gitlab_client, settings.gitlab_projects_root)


_FACTORIES: Dict[str, CatalogFactory] = {
    FAKE_PROVIDER_NAME: _create_fake_catalog,
    GITLAB_PROVIDER_NAME: _create_gitlab_catalog,
}
