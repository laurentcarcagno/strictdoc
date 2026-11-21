"""
@relation(SDOC-SRS-1227, scope=file)
@relation(SDOC-SRS-1228, scope=file)
"""

import copy
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
from gitlab.exceptions import GitlabGetError

from strictdoc.features.project_catalog.catalog import (
    CatalogError,
    CatalogProject,
    CatalogRole,
    DesktopIdentity,
)
from strictdoc.features.project_catalog.gitlab_catalog import GitLabCatalog
from strictdoc.helpers.file_system import file_open_read_utf8

ROOT_GROUP_PATH = "HERMES/DOCUMENTATION/PROJETS"
DATA_PATH = Path(__file__).parent / "data" / "gitlab_group_projects.json"
IDENTITY = DesktopIdentity(username="jdoe", display_name="Jane Doe")

# The default page size of the GitLab API.
GITLAB_PAGE_SIZE = 20


class FakeObject:
    def __init__(self, **attributes: Any) -> None:
        self.__dict__.update(attributes)


class FakeGroupProjects:
    """The projects of a group, as the GitLab API answers a list query."""

    def __init__(self, records: List[Dict[str, Any]]) -> None:
        self.records = records
        self.calls: List[Dict[str, Any]] = []

    def list(self, **query: Any) -> List[FakeObject]:
        self.calls.append(query)
        records = self.records
        if query.get("include_subgroups") is not True:
            records = [
                record_
                for record_ in records
                if record_["namespace"]["full_path"] == ROOT_GROUP_PATH
            ]
        if query.get("archived") is False:
            records = [
                record_ for record_ in records if not record_["archived"]
            ]
        minimum_access_level = query.get("min_access_level", 0)
        records = [
            record_
            for record_ in records
            if self._get_access_level(record_) >= minimum_access_level
        ]
        if query.get("get_all") is not True:
            records = records[:GITLAB_PAGE_SIZE]
        return [FakeObject(**record_) for record_ in records]

    @staticmethod
    def _get_access_level(record: Dict[str, Any]) -> int:
        permissions = record["permissions"]
        return max(
            access_["access_level"]
            for access_ in (
                permissions["project_access"],
                permissions["group_access"],
            )
            if access_ is not None
        )


class FakeGroups:
    def __init__(self, group_projects: FakeGroupProjects) -> None:
        self.group = FakeObject(projects=group_projects)

    def get(self, path: str) -> FakeObject:
        if path != ROOT_GROUP_PATH:
            raise GitlabGetError("404 Group Not Found", 404)
        return self.group


class FakeClient:
    def __init__(self, records: List[Dict[str, Any]]) -> None:
        self.group_projects = FakeGroupProjects(records)
        self.groups = FakeGroups(self.group_projects)


def _read_records() -> List[Dict[str, Any]]:
    with file_open_read_utf8(str(DATA_PATH)) as file_:
        records: List[Dict[str, Any]] = json.load(file_)
    return records


def _list_projects(
    records: List[Dict[str, Any]],
) -> Dict[str, CatalogProject]:
    catalog = GitLabCatalog(FakeClient(records), ROOT_GROUP_PATH)
    return {
        project_.display_path: project_
        for project_ in catalog.list_projects(IDENTITY)
    }


def test_001_roles_follow_the_access_level() -> None:
    projects = _list_projects(_read_records())

    assert {path_: project_.role for path_, project_ in projects.items()} == {
        # Owner through the group.
        "Satellites/ISIS": CatalogRole.ADMINISTRATOR,
        # Maintainer on the project, Developer on the group.
        "Satellites/Pleiades": CatalogRole.ADMINISTRATOR,
        "Satellites/Orion/Payload": CatalogRole.AUTHOR,
        "Lanceurs/Ariane": CatalogRole.READER,
        "Outils": CatalogRole.AUTHOR,
    }


def test_002_guest_does_not_see_the_project() -> None:
    projects = _list_projects(_read_records())

    assert "Lanceurs/Secret" not in projects


def test_003_archived_project_is_left_out() -> None:
    client = FakeClient(_read_records())
    catalog = GitLabCatalog(client, ROOT_GROUP_PATH)

    projects = catalog.list_projects(IDENTITY)

    assert "Satellites/Legacy" not in [
        project_.display_path for project_ in projects
    ]
    assert all(
        call_["archived"] is False and call_["include_subgroups"] is True
        for call_ in client.group_projects.calls
    )


def test_004_fields_of_a_project() -> None:
    projects = _list_projects(_read_records())

    assert projects["Satellites/ISIS"] == CatalogProject(
        identifier="101",
        title="ISIS",
        display_path="Satellites/ISIS",
        description="Instrument de bord ISIS",
        clone_url=(
            "https://gitlab.example.org/HERMES/DOCUMENTATION/PROJETS/"
            "Satellites/ISIS.git"
        ),
        role=CatalogRole.ADMINISTRATOR,
    )


def test_005_project_of_the_root_group_has_no_description() -> None:
    projects = _list_projects(_read_records())

    assert projects["Outils"].description == ""
    assert projects["Outils"].title == "Outils"


def test_006_projects_are_sorted_by_display_path() -> None:
    catalog = GitLabCatalog(FakeClient(_read_records()), ROOT_GROUP_PATH)

    paths = [
        project_.display_path for project_ in catalog.list_projects(IDENTITY)
    ]

    assert paths == sorted(paths)


def test_007_all_the_pages_are_read() -> None:
    reader_record = next(
        record_ for record_ in _read_records() if record_["id"] == 104
    )
    records = []
    for index_ in range(25):
        record = copy.deepcopy(reader_record)
        record["id"] = 1000 + index_
        record["path_with_namespace"] = (
            f"{ROOT_GROUP_PATH}/Lanceurs/Projet{index_:02d}"
        )
        records.append(record)

    projects = _list_projects(records)

    assert len(projects) == 25


def test_008_root_group_path_may_have_slashes_around() -> None:
    catalog = GitLabCatalog(FakeClient(_read_records()), f"/{ROOT_GROUP_PATH}/")

    assert len(catalog.list_projects(IDENTITY)) == 5


def test_009_gitlab_error_becomes_a_catalog_error() -> None:
    catalog = GitLabCatalog(FakeClient(_read_records()), "OTHER/GROUP")

    with pytest.raises(CatalogError, match="OTHER/GROUP"):
        catalog.list_projects(IDENTITY)
