from typing import Any, Dict, List

import pytest
from gitlab.exceptions import GitlabGetError

from strictdoc.features.git_config.config import GitConfig
from strictdoc.features.git_config.gitlab_service import (
    GitLabService,
    GitLabServiceError,
)


class FakeObject:
    def __init__(self, **attributes: Any) -> None:
        self.__dict__.update(attributes)


class FakeGroups:
    def __init__(self) -> None:
        self.existing: Dict[str, FakeObject] = {}
        self.created: List[Dict[str, Any]] = []

    def get(self, path: str) -> FakeObject:
        if path not in self.existing:
            raise GitlabGetError("404 Not Found", 404)
        return self.existing[path]

    def create(self, data: Dict[str, Any]) -> FakeObject:
        self.created.append(data)
        group = FakeObject(id=100 + len(self.created))
        parent = next(
            (
                p
                for p, g in self.existing.items()
                if g.id == data.get("parent_id")
            ),
            "",
        )
        full_path = f"{parent}/{data['path']}" if parent else data["path"]
        self.existing[full_path] = group
        return group


class FakeProjects:
    def __init__(self) -> None:
        self.created: List[Dict[str, Any]] = []
        self.existing: Dict[str, FakeObject] = {}

    def get(self, path: str) -> FakeObject:
        if path not in self.existing:
            raise GitlabGetError("404 Project Not Found", 404)
        return self.existing[path]

    def create(self, data: Dict[str, Any]) -> FakeObject:
        self.created.append(data)
        return FakeObject(
            http_url_to_repo=f"https://gitlab.karka.lan/x/{data['path']}.git",
            ssh_url_to_repo=f"git@gitlab.karka.lan:x/{data['path']}.git",
        )


class FakeClient:
    def __init__(self) -> None:
        self.groups = FakeGroups()
        self.projects = FakeProjects()
        self.auth_called = False

    def auth(self) -> None:
        self.auth_called = True


def test_creates_missing_groups_then_the_project() -> None:
    client = FakeClient()
    service = GitLabService(GitConfig(), client=client)
    url = service.create_repository(
        "referentiel-documentaire/modules/logiciel", "interface-telemesure"
    )
    assert [g["path"] for g in client.groups.created] == [
        "referentiel-documentaire",
        "modules",
        "logiciel",
    ]
    assert client.projects.created[0]["path"] == "interface-telemesure"
    assert client.projects.created[0]["namespace_id"] == 103
    assert url == "https://gitlab.karka.lan/x/interface-telemesure.git"


def test_existing_groups_are_reused() -> None:
    client = FakeClient()
    client.groups.existing["a"] = FakeObject(id=7)
    GitLabService(GitConfig(), client=client).create_repository("a", "doc")
    assert client.groups.created == []
    assert client.projects.created[0]["namespace_id"] == 7


@pytest.mark.parametrize("name", ["", "a b", "../x", "x/y", "-x", "x.git"])
def test_rejects_bad_repository_names(name: str) -> None:
    with pytest.raises(GitLabServiceError):
        GitLabService(GitConfig(), client=FakeClient()).create_repository(
            "a", name
        )


def test_missing_token_is_reported_without_its_value(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    with pytest.raises(GitLabServiceError, match="GITLAB_TOKEN"):
        GitLabService(GitConfig()).create_repository("a", "doc")


def test_ensure_repository_creates_only_a_missing_project() -> None:
    client = FakeClient()
    client.groups.existing["a"] = FakeObject(id=7)
    service = GitLabService(GitConfig(), client=client)
    assert service.ensure_repository("a", "doc") is True
    assert [p["path"] for p in client.projects.created] == ["doc"]
    client.projects.existing["a/doc"] = FakeObject()
    assert service.ensure_repository("a", "doc") is False
    assert len(client.projects.created) == 1
