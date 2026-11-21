"""
@relation(SDOC-SRS-1226, scope=file)
"""

from pathlib import Path
from typing import Any, List, Optional

import pytest

from strictdoc.features.desktop.settings import DesktopSettings
from strictdoc.features.project_catalog import registry
from strictdoc.features.project_catalog.catalog import (
    CatalogError,
    CatalogProject,
    DesktopIdentity,
    ProjectCatalog,
)
from strictdoc.features.project_catalog.fake_catalog import FakeCatalog
from strictdoc.features.project_catalog.gitlab_catalog import GitLabCatalog
from strictdoc.features.project_catalog.registry import (
    UnknownCatalogProviderError,
    create_catalog,
    get_catalog_provider_names,
    register_catalog_provider,
)

DATA_PATH = Path(__file__).parent / "data" / "fake_catalog.json"


class EmptyCatalog:
    def list_projects(self, identity: DesktopIdentity) -> List[CatalogProject]:
        del identity
        return []


def test_001_built_in_providers() -> None:
    assert get_catalog_provider_names() == ["fake", "gitlab"]


def test_002_gitlab_catalog_from_the_settings() -> None:
    settings = DesktopSettings(
        catalog_provider="gitlab", gitlab_projects_root="TEAM/PROJECTS"
    )
    client = object()

    catalog = create_catalog(settings, client)

    assert isinstance(catalog, GitLabCatalog)
    assert catalog.client is client
    assert catalog.root_group_path == "TEAM/PROJECTS"


def test_003_gitlab_catalog_needs_a_connection() -> None:
    with pytest.raises(CatalogError, match="GitLab connection"):
        create_catalog(DesktopSettings(catalog_provider="gitlab"))


def test_004_fake_catalog_from_the_settings() -> None:
    settings = DesktopSettings(
        catalog_provider="fake", fake_catalog_path=str(DATA_PATH)
    )

    catalog = create_catalog(settings)

    assert isinstance(catalog, FakeCatalog)
    assert catalog.path == str(DATA_PATH)


def test_005_fake_catalog_needs_a_path() -> None:
    with pytest.raises(CatalogError, match="fake_catalog_path"):
        create_catalog(DesktopSettings(catalog_provider="fake"))


def test_006_unknown_provider_names_the_available_ones() -> None:
    with pytest.raises(UnknownCatalogProviderError) as exception_info:
        create_catalog(DesktopSettings(catalog_provider="ldap"))

    message = str(exception_info.value)
    assert "ldap" in message
    assert "fake, gitlab" in message


def test_007_new_provider_registers_under_a_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "_FACTORIES", dict(registry._FACTORIES))

    def create_empty_catalog(
        settings: DesktopSettings, gitlab_client: Optional[Any]
    ) -> ProjectCatalog:
        del settings, gitlab_client
        return EmptyCatalog()

    register_catalog_provider("empty", create_empty_catalog)

    catalog = create_catalog(DesktopSettings(catalog_provider="empty"))

    assert isinstance(catalog, EmptyCatalog)
    assert get_catalog_provider_names() == ["empty", "fake", "gitlab"]
