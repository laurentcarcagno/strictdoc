"""
@relation(SDOC-SRS-1226, scope=file)
"""

from pathlib import Path

import pytest

from strictdoc.features.project_catalog.catalog import (
    CatalogError,
    CatalogProject,
    CatalogRole,
    DesktopIdentity,
)
from strictdoc.features.project_catalog.fake_catalog import FakeCatalog

IDENTITY = DesktopIdentity(username="jdoe", display_name="Jane Doe")
DATA_PATH = Path(__file__).parent / "data" / "fake_catalog.json"


def test_001_projects_come_from_the_file() -> None:
    projects = FakeCatalog(str(DATA_PATH)).list_projects(IDENTITY)

    assert projects == [
        CatalogProject(
            identifier="demo/isis",
            title="ISIS",
            display_path="Satellites/ISIS",
            description="Instrument de bord",
            clone_url="file:///data/isis.git",
            role=CatalogRole.ADMINISTRATOR,
        ),
        CatalogProject(
            identifier="demo/ariane",
            title="Ariane",
            display_path="Lanceurs/Ariane",
            description="",
            clone_url="file:///data/ariane.git",
            role=CatalogRole.READER,
        ),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        '{"identifier": "a"}',
        "[3]",
        '[{"identifier": "a", "title": "A"}]',
        (
            '[{"identifier": "a", "title": "A", "display_path": "A", '
            '"description": "", "clone_url": "file:///a.git", '
            '"role": "owner"}]'
        ),
    ],
)
def test_002_invalid_file_is_a_catalog_error(tmp_path: Path, text: str) -> None:
    path = tmp_path / "catalog.json"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(CatalogError, match="catalog file"):
        FakeCatalog(str(path)).list_projects(IDENTITY)


def test_003_missing_file_is_a_catalog_error(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="cannot be read"):
        FakeCatalog(str(tmp_path / "missing.json")).list_projects(IDENTITY)
