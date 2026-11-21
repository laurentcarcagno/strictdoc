"""
@relation(SDOC-SRS-1229, scope=file)
"""

import json
from pathlib import Path
from typing import Iterator

import pytest

from strictdoc.features.desktop.home_app import (
    build_catalog_tree,
    render_home,
    set_language_from_environment,
)
from strictdoc.features.desktop.settings import DesktopSettings
from strictdoc.features.i18n import i18n
from strictdoc.features.project_catalog.catalog import (
    CatalogProject,
    CatalogRole,
)

CATALOG = [
    {
        "identifier": "demo/isis",
        "title": "ISIS",
        "display_path": "Satellites/ISIS",
        "description": "Instrument de bord",
        "clone_url": "file:///unused/isis.git",
        "role": "administrator",
    },
    {
        "identifier": "demo/ariane",
        "title": "Ariane",
        "display_path": "Lanceurs/Ariane",
        "description": "",
        "clone_url": "file:///unused/ariane.git",
        "role": "reader",
    },
]


def _create_project(display_path: str, title: str) -> CatalogProject:
    return CatalogProject(
        identifier=display_path,
        title=title,
        display_path=display_path,
        description="",
        clone_url="file:///unused.git",
        role=CatalogRole.READER,
    )


@pytest.fixture(name="catalog_path")
def fixture_catalog_path(tmp_path: Path) -> str:
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(CATALOG), encoding="utf-8")
    return str(path)


@pytest.fixture(name="restore_language", autouse=True)
def fixture_restore_language() -> Iterator[None]:
    yield
    i18n.set_language(i18n.DEFAULT_LANGUAGE)


def test_001_projects_are_grouped_by_the_folders_of_their_path() -> None:
    root = build_catalog_tree(
        [
            _create_project("Satellites/ISIS", "ISIS"),
            _create_project("Satellites/Orion/Payload", "Payload"),
            _create_project("Lanceurs/Ariane", "Ariane"),
            _create_project("Tools", "Tools"),
            _create_project("Satellites/Pleiades", "Pleiades"),
        ]
    )

    assert [folder_.name for folder_ in root.folders] == [
        "Lanceurs",
        "Satellites",
    ]
    assert [project_.title for project_ in root.projects] == ["Tools"]
    satellites = root.folders[1]
    assert [folder_.name for folder_ in satellites.folders] == ["Orion"]
    assert [project_.title for project_ in satellites.projects] == [
        "ISIS",
        "Pleiades",
    ]
    assert [project_.title for project_ in satellites.folders[0].projects] == [
        "Payload"
    ]


def test_002_empty_catalog_gives_an_empty_tree() -> None:
    root = build_catalog_tree([])

    assert root.folders == []
    assert root.projects == []


def test_003_page_of_the_first_launch(catalog_path: str) -> None:
    settings = DesktopSettings(
        catalog_provider="fake", fake_catalog_path=catalog_path
    )

    page = render_home(settings).body.decode("utf-8")

    assert 'data-testid="home-welcome"' in page
    assert page.count('data-testid="catalog-project"') == 2
    assert page.count('data-testid="catalog-folder"') == 2
    assert 'lang="en"' in page


def test_004_no_welcome_message_once_a_project_was_opened(
    catalog_path: str,
) -> None:
    settings = DesktopSettings(
        catalog_provider="fake",
        fake_catalog_path=catalog_path,
        project_folders={"demo/isis": "/data/isis"},
    )

    page = render_home(settings).body.decode("utf-8")

    assert 'data-testid="home-welcome"' not in page
    assert 'data-testid="catalog-project"' in page


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        (
            DesktopSettings(catalog_provider="ldap"),
            "Unknown catalog provider",
        ),
        (
            DesktopSettings(
                catalog_provider="fake", fake_catalog_path="/missing.json"
            ),
            "/missing.json",
        ),
        (DesktopSettings(catalog_provider="fake"), "fake_catalog_path"),
    ],
)
def test_005_catalog_error_is_a_message_in_the_page(
    settings: DesktopSettings, message: str
) -> None:
    page = render_home(settings).body.decode("utf-8")

    assert 'data-testid="catalog-error"' in page
    assert message in page
    assert "Traceback" not in page
    assert 'data-testid="catalog-search"' not in page


def test_006_page_is_in_french_when_the_language_is_french(
    catalog_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STRICTDOC_LANGUAGE", "fr")
    set_language_from_environment()
    settings = DesktopSettings(
        catalog_provider="fake", fake_catalog_path=catalog_path
    )

    page = render_home(settings).body.decode("utf-8")

    assert 'lang="fr"' in page
    assert "Bienvenue dans StrictDoc" in page
    assert "administrateur" in page
    assert "Rechercher un projet par nom" in page


def test_007_language_is_english_without_the_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("STRICTDOC_LANGUAGE", raising=False)
    i18n.set_language("fr")

    set_language_from_environment()

    assert i18n.get_language() == "en"


def test_008_unknown_language_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRICTDOC_LANGUAGE", "de")

    with pytest.raises(ValueError, match="expected one of"):
        set_language_from_environment()
