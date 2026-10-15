import subprocess
from pathlib import Path
from typing import Any, List, Tuple

import pytest

from strictdoc.features.git_config import setup
from strictdoc.features.git_config.config import GitConfig


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


class FakeGitLab:
    calls: List[Tuple[str, str]] = []

    def __init__(self, config: GitConfig) -> None:
        pass

    def ensure_repository(self, group: str, name: str) -> bool:
        FakeGitLab.calls.append((group, name))
        return True


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> List[Any]:
    FakeGitLab.calls = []
    pushed: List[Any] = []
    monkeypatch.setattr(setup, "GitLabService", FakeGitLab)
    monkeypatch.setattr(
        setup.GitService,
        "push",
        lambda _self, path, _tag=None: pushed.append(path),
    )
    return pushed


def test_a_new_project_gets_a_repository_a_remote_and_a_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fakes: List[Any]
) -> None:
    monkeypatch.setenv("GITLAB_TOKEN", "t")
    folder = tmp_path / "alpha"
    folder.mkdir()
    (folder / "strictdoc.toml").write_text("[project]\n")
    assert setup.provision_repository(str(folder), "alpha", GitConfig()) == ""
    assert _git(folder, "branch", "--show-current") == "main"
    assert _git(folder, "remote", "get-url", "origin") == (
        "https://gitlab.karka.lan/documentation/projects/alpha.git"
    )
    assert "Create the project alpha" in _git(folder, "log", "--format=%s")
    assert FakeGitLab.calls == [("documentation/projects", "alpha")]
    assert fakes == [str(folder)]


@pytest.mark.usefixtures("fakes")
def test_without_a_token_nothing_is_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    folder = tmp_path / "alpha"
    folder.mkdir()
    assert setup.provision_repository(str(folder), "alpha", GitConfig()) == ""
    assert not (folder / ".git").exists()
    assert FakeGitLab.calls == []


@pytest.mark.usefixtures("fakes")
def test_an_existing_remote_gets_its_project_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITLAB_TOKEN", "t")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(
        tmp_path,
        "remote",
        "add",
        "origin",
        "https://gitlab.karka.lan/documentation/projects/ISIS.git",
    )
    service = setup.GitService(str(tmp_path))
    assert (
        setup.ensure_remote_repository(service, str(tmp_path), GitConfig())
        == ""
    )
    assert FakeGitLab.calls == [("documentation/projects", "ISIS")]
    # A remote on another server is left alone.
    FakeGitLab.calls = []
    _git(
        tmp_path, "remote", "set-url", "origin", "https://other.example/a/b.git"
    )
    setup.ensure_remote_repository(service, str(tmp_path), GitConfig())
    assert FakeGitLab.calls == []
