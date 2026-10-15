import os
import subprocess
from pathlib import Path
from typing import List

import pytest
from git import Repo

from strictdoc.features.git_config.git_service import (
    Author,
    GitService,
    GitServiceError,
)

AUTHOR = Author("Alice Author", "alice@example.com")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _init(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "master")
    _git(path, "config", "user.name", "Init")
    _git(path, "config", "user.email", "init@example.com")
    _git(path, "config", "protocol.file.allow", "always")
    (path / "README").write_text("x")
    _git(path, "add", "README")
    _git(path, "commit", "-q", "-m", "init")
    return path


def _subjects(path: Path) -> List[str]:
    return _git(path, "log", "--format=%s").splitlines()


@pytest.fixture
def super_project(tmp_path: Path) -> Path:
    module = _init(tmp_path / "module_src")
    (module / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: A\n")
    _git(module, "add", "doc.sdoc")
    _git(module, "commit", "-q", "-m", "doc")
    project = _init(tmp_path / "project")
    _git(
        project,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(module),
        "modules/doc",
    )
    _git(project, "commit", "-q", "-m", "add module")
    return project


def test_commit_in_plain_repository(tmp_path: Path) -> None:
    repo = _init(tmp_path / "repo")
    (repo / "a.sdoc").write_text("one")
    (repo / "unrelated.txt").write_text("dirty")
    service = GitService(str(repo))
    committed = service.commit_paths(
        [str(repo / "a.sdoc")], "feat(doc): add a", AUTHOR
    )
    assert committed is True
    assert _subjects(repo)[0] == "feat(doc): add a"
    assert _git(repo, "log", "-1", "--format=%an <%ae>") == (
        "Alice Author <alice@example.com>"
    )
    # Only the saved path is committed.
    assert "unrelated.txt" in _git(repo, "status", "--porcelain")


def test_nothing_to_commit_is_not_an_error(tmp_path: Path) -> None:
    repo = _init(tmp_path / "repo")
    service = GitService(str(repo))
    assert service.commit_paths([str(repo / "README")], "m", AUTHOR) is False
    assert len(_subjects(repo)) == 1


def test_commit_in_submodule_then_parent_pointer(super_project: Path) -> None:
    doc = super_project / "modules" / "doc" / "doc.sdoc"
    doc.write_text("[DOCUMENT]\nTITLE: B\n")
    service = GitService(str(super_project))
    service.commit_paths([str(doc)], "feat(doc): update [REQ-042]", AUTHOR)

    assert _subjects(super_project / "modules" / "doc")[0] == (
        "feat(doc): update [REQ-042]"
    )
    sha = _git(
        super_project / "modules" / "doc", "rev-parse", "--short", "HEAD"
    )
    assert (
        _subjects(super_project)[0] == f"chore(submodule): update doc to {sha}"
    )
    assert _git(super_project, "status", "--porcelain") == ""


def test_paths_in_two_repositories(super_project: Path) -> None:
    doc = super_project / "modules" / "doc" / "doc.sdoc"
    doc.write_text("changed")
    toml = super_project / "strictdoc.toml"
    toml.write_text("[project]\n")
    GitService(str(super_project)).commit_paths(
        [str(doc), str(toml)], "m", AUTHOR
    )
    assert _git(super_project, "status", "--porcelain") == ""


def test_tags_and_next_versions(tmp_path: Path) -> None:
    repo = _init(tmp_path / "repo")
    service = GitService(str(repo))
    assert service.next_intermediate_tag(str(repo)) == "A1"
    service.create_tag(str(repo), "A1")
    assert service.next_intermediate_tag(str(repo)) == "A2"
    service.create_tag(str(repo), "A2")
    assert service.next_major_tag(str(repo)) == "A"
    with pytest.raises(GitServiceError):
        service.create_tag(str(repo), "A2")


def test_push_tag_refuses_existing_remote_tag(tmp_path: Path) -> None:
    repo = _init(tmp_path / "repo")
    bare = tmp_path / "remote.git"
    Repo.init(str(bare), bare=True)
    _git(repo, "remote", "add", "origin", str(bare))
    service = GitService(str(repo))
    service.create_tag(str(repo), "A1")
    service.push(str(repo), tag="A1")
    assert "A1" in _git(bare, "tag")
    # Same name, different commit.
    (repo / "b").write_text("b")
    service.commit_paths([str(repo / "b")], "m", AUTHOR)
    _git(repo, "tag", "-d", "A1")
    service.create_tag(str(repo), "A1")
    with pytest.raises(GitServiceError):
        service.push(str(repo), tag="A1")


def test_push_fast_forwards_but_never_merges(tmp_path: Path) -> None:
    repo = _init(tmp_path / "repo")
    bare = tmp_path / "remote.git"
    Repo.init(str(bare), bare=True)
    _git(repo, "remote", "add", "origin", str(bare))
    service = GitService(str(repo))
    service.push(str(repo))

    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", str(bare), str(other))
    _git(other, "config", "user.name", "o")
    _git(other, "config", "user.email", "o@example.com")
    (other / "o.txt").write_text("o")
    _git(other, "add", "o.txt")
    _git(other, "commit", "-q", "-m", "remote work")
    _git(other, "push", "-q", "origin", "master")

    # Remote ahead: fast-forward then push.
    service.push(str(repo))
    assert (repo / "o.txt").exists()

    # Diverged: refuse.
    (repo / "l.txt").write_text("l")
    service.commit_paths([str(repo / "l.txt")], "local", AUTHOR)
    (other / "o2.txt").write_text("o2")
    _git(other, "add", "o2.txt")
    _git(other, "commit", "-q", "-m", "remote work 2")
    _git(other, "push", "-q", "origin", "master")
    with pytest.raises(GitServiceError):
        service.push(str(repo))
    assert _subjects(repo)[0] == "local"


def test_push_submodule_before_parent(
    super_project: Path, tmp_path: Path
) -> None:
    sub = super_project / "modules" / "doc"
    sub_bare = tmp_path / "sub_remote.git"
    parent_bare = tmp_path / "parent_remote.git"
    Repo.init(str(sub_bare), bare=True)
    Repo.init(str(parent_bare), bare=True)
    _git(sub, "remote", "set-url", "origin", str(sub_bare))
    _git(super_project, "remote", "add", "origin", str(parent_bare))
    (sub / "doc.sdoc").write_text("new")
    service = GitService(str(super_project))
    service.commit_paths([str(sub / "doc.sdoc")], "m", AUTHOR)
    service.push_with_submodules(str(super_project))
    sub_sha = _git(sub, "rev-parse", "HEAD")
    assert _git(sub_bare, "rev-parse", "master") == sub_sha
    assert _git(parent_bare, "rev-parse", "master") == _git(
        super_project, "rev-parse", "HEAD"
    )


def test_owning_repository_of_a_path(super_project: Path) -> None:
    service = GitService(str(super_project))
    sub = super_project / "modules" / "doc"
    assert service.repository_root(str(sub / "doc.sdoc")) == str(sub)
    assert service.repository_root(str(super_project / "x.toml")) == str(
        super_project
    )


def test_path_outside_the_project_is_refused(
    tmp_path: Path, super_project: Path
) -> None:
    outside = _init(tmp_path / "outside")
    service = GitService(str(super_project))
    with pytest.raises(GitServiceError):
        service.commit_paths([str(outside / "README")], "m", AUTHOR)


def test_submodule_add_commits_gitmodules_and_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "protocol.file.allow")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "always")
    module = _init(tmp_path / "shared_can_bus")
    project = _init(tmp_path / "project")
    service = GitService(str(project), allowed_url_schemes=("file",))
    service.submodule_add(
        str(project), module.as_uri(), "modules/can_bus", AUTHOR
    )
    assert (project / "modules" / "can_bus" / "README").exists()
    assert _subjects(project)[0] == "chore(submodule): add modules/can_bus"
    assert _git(project, "status", "--porcelain") == ""


@pytest.mark.parametrize(
    "url,path",
    [
        ("file:///x", "modules/x"),
        ("--upload-pack=x", "modules/x"),
        ("https://gitlab.karka.lan/a.git", "../x"),
        ("https://gitlab.karka.lan/a.git", "/abs"),
        ("https://gitlab.karka.lan/a.git", "-x"),
        ("https://gitlab.karka.lan/a.git", ".git/hooks"),
    ],
)
def test_submodule_add_validates_url_and_path(
    tmp_path: Path, url: str, path: str
) -> None:
    project = _init(tmp_path / "project")
    with pytest.raises(GitServiceError):
        GitService(str(project)).submodule_add(str(project), url, path, AUTHOR)


def test_submodule_update_initialises_a_fresh_clone(
    super_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "protocol.file.allow")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "always")
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(super_project), str(clone))
    assert not (clone / "modules" / "doc" / "doc.sdoc").exists()
    GitService(str(clone)).submodule_update(str(clone))
    assert (clone / "modules" / "doc" / "doc.sdoc").exists()


def test_describe_lists_the_repositories(super_project: Path) -> None:
    service = GitService(str(super_project))
    service.create_tag(str(super_project / "modules" / "doc"), "A1")
    states = service.describe_repositories()
    by_name = {state.relative_path: state for state in states}
    assert set(by_name) == {".", "modules/doc"}
    sub = by_name["modules/doc"]
    assert sub.branch == "master"
    assert sub.latest_tag == "A1"
    assert sub.next_intermediate == "A2"
    assert sub.next_major == "A"
    assert by_name["."].next_major is None
    assert by_name["."].dirty is False


def _credential(repo: Path, service: GitService, host: str) -> str:
    environment = service._remote_environment(Repo(str(repo)))
    return subprocess.run(
        ["git", "-C", str(repo), "credential", "fill"],
        input=f"protocol=https\nhost={host}\n\n",
        capture_output=True,
        text=True,
        env={**os.environ, **environment, "GIT_TERMINAL_PROMPT": "0"},
        check=False,
    ).stdout


def test_remote_token_goes_to_the_host_of_the_remote_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init(tmp_path / "r")
    _git(repo, "remote", "add", "origin", "https://gitlab.example/g/p.git")
    monkeypatch.setenv("SDOC_TEST_TOKEN", "s3cret")
    service = GitService(
        str(repo), token_env="SDOC_TEST_TOKEN", ca_bundle="/etc/ca.pem"
    )
    asked = _credential(repo, service, "gitlab.example")
    assert "username=oauth2" in asked and "password=s3cret" in asked
    assert "s3cret" not in _credential(repo, service, "elsewhere.example")
    environment = service._remote_environment(Repo(str(repo)))
    assert environment["GIT_SSL_CAINFO"] == "/etc/ca.pem"
    assert "s3cret" not in " ".join(environment.values())


def test_no_token_means_no_credential_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init(tmp_path / "r")
    _git(repo, "remote", "add", "origin", "https://gitlab.example/g/p.git")
    monkeypatch.delenv("SDOC_TEST_TOKEN", raising=False)
    service = GitService(str(repo), token_env="SDOC_TEST_TOKEN")
    assert service._remote_environment(Repo(str(repo))) == {}
