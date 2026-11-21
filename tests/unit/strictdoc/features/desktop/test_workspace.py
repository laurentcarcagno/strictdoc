"""
@relation(SDOC-SRS-1230, scope=file)
"""

import os
from pathlib import Path
from typing import Iterator

import pytest
from git import Actor, GitCommandError, Repo

from strictdoc.features.desktop import workspace
from strictdoc.features.desktop.workspace import (
    FolderStatus,
    WorkspaceError,
    check_folder,
    clone_project,
    normalize_clone_url,
)
from strictdoc.features.i18n import i18n

CLONE_URL = "https://gitlab.example.org/team/project.git"


@pytest.fixture(name="restore_language", autouse=True)
def fixture_restore_language() -> Iterator[None]:
    yield
    i18n.set_language(i18n.DEFAULT_LANGUAGE)


def _create_bare_repository(tmp_path: Path) -> str:
    """A bare repository with one document, as the remote of a project."""
    work_path = tmp_path / "work"
    work_path.mkdir()
    (work_path / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: Doc\n")
    work_repo = Repo.init(work_path)
    work_repo.index.add(["doc.sdoc"])
    actor = Actor("Test", "test@example.org")
    work_repo.index.commit("Add the document", author=actor, committer=actor)
    bare_path = tmp_path / "remote.git"
    Repo.clone_from(str(work_path), str(bare_path), bare=True).close()
    work_repo.close()
    return f"file://{bare_path}"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://GitLab.Example.org/team/project.git",
            "https://gitlab.example.org/team/project",
        ),
        (
            "https://gitlab.example.org/team/project/",
            "https://gitlab.example.org/team/project",
        ),
        (
            "https://oauth2:secret@gitlab.example.org/team/project.git/",
            "https://gitlab.example.org/team/project",
        ),
        (
            "git@gitlab.example.org:team/project.git",
            "ssh://gitlab.example.org/team/project",
        ),
        (
            "ssh://git@gitlab.example.org/team/project.git",
            "ssh://gitlab.example.org/team/project",
        ),
        (
            "https://gitlab.example.org:8443/team/project.git",
            "https://gitlab.example.org:8443/team/project",
        ),
        ("file:///data/remote.git", "file:///data/remote"),
        ("/data/remote.git", "file:///data/remote"),
    ],
)
def test_001_urls_of_one_repository_are_normalized(
    url: str, expected: str
) -> None:
    assert normalize_clone_url(url) == expected


def test_002_empty_folder(tmp_path: Path) -> None:
    check = check_folder(str(tmp_path), CLONE_URL)

    assert check.status is FolderStatus.EMPTY
    assert check.reason == ""


@pytest.mark.parametrize(
    "origin_url",
    [
        CLONE_URL,
        "https://GITLAB.example.org/team/project",
        "https://token@gitlab.example.org/team/project.git/",
    ],
)
def test_003_folder_of_the_same_repository(
    tmp_path: Path, origin_url: str
) -> None:
    repo = Repo.init(tmp_path)
    repo.create_remote("origin", origin_url)
    repo.close()

    check = check_folder(str(tmp_path), CLONE_URL)

    assert check.status is FolderStatus.SAME_REPOSITORY


def test_004_folder_of_another_repository(tmp_path: Path) -> None:
    repo = Repo.init(tmp_path)
    repo.create_remote("origin", "https://gitlab.example.org/team/other.git")
    repo.close()

    check = check_folder(str(tmp_path), CLONE_URL)

    assert check.status is FolderStatus.REFUSED
    assert "another repository" in check.reason
    assert "team/other" in check.reason


def test_005_repository_without_origin_is_refused(tmp_path: Path) -> None:
    Repo.init(tmp_path).close()

    check = check_folder(str(tmp_path), CLONE_URL)

    assert check.status is FolderStatus.REFUSED
    assert "is not empty" in check.reason


def test_006_folder_with_files_and_no_git_is_refused(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("notes")

    check = check_folder(str(tmp_path), CLONE_URL)

    assert check.status is FolderStatus.REFUSED
    assert "is not empty" in check.reason
    assert str(tmp_path) in check.reason


def test_007_folder_inside_a_repository_is_not_a_clone(
    tmp_path: Path,
) -> None:
    repo = Repo.init(tmp_path)
    repo.create_remote("origin", CLONE_URL)
    repo.close()
    sub_folder = tmp_path / "sub"
    sub_folder.mkdir()
    (sub_folder / "file.txt").write_text("x")

    check = check_folder(str(sub_folder), CLONE_URL)

    assert check.status is FolderStatus.REFUSED


def test_008_missing_folder_and_file_are_refused(tmp_path: Path) -> None:
    missing_check = check_folder(str(tmp_path / "missing"), CLONE_URL)
    file_path = tmp_path / "file.txt"
    file_path.write_text("x")
    file_check = check_folder(str(file_path), CLONE_URL)

    assert missing_check.status is FolderStatus.REFUSED
    assert "does not exist" in missing_check.reason
    assert file_check.status is FolderStatus.REFUSED
    assert "is not a folder" in file_check.reason


def test_009_path_that_is_too_long_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / ("long_name_" * 5)
    folder.mkdir()

    check = check_folder(str(folder), CLONE_URL, max_path_length=30)
    without_limit = check_folder(str(folder), CLONE_URL)

    assert check.status is FolderStatus.REFUSED
    assert "too long" in check.reason
    assert "30" in check.reason
    assert without_limit.status is FolderStatus.EMPTY


def test_010_reasons_are_in_french_when_the_language_is_french(
    tmp_path: Path,
) -> None:
    i18n.set_language("fr")

    check = check_folder(str(tmp_path / "missing"), CLONE_URL)

    assert check.reason.startswith("Le dossier")
    assert "n'existe pas" in check.reason


def test_011_clone_into_an_empty_folder(tmp_path: Path) -> None:
    clone_url = _create_bare_repository(tmp_path)
    folder = tmp_path / "workspace"
    folder.mkdir()

    clone_project(clone_url, str(folder))

    assert (folder / "doc.sdoc").is_file()
    assert check_folder(str(folder), clone_url).status is (
        FolderStatus.SAME_REPOSITORY
    )


def test_012_failed_clone_leaves_the_folder_empty(tmp_path: Path) -> None:
    folder = tmp_path / "workspace"
    folder.mkdir()

    with pytest.raises(WorkspaceError) as exception_info:
        clone_project(f"file://{tmp_path}/missing.git", str(folder))

    assert "The clone of the project failed" in str(exception_info.value)
    assert os.listdir(folder) == []
    assert folder.is_dir()


def test_013_failed_clone_removes_what_it_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "workspace"
    folder.mkdir()

    def failing_clone(clone_url: str, target_folder: str) -> None:
        # What a clone that stops half way leaves: Git objects are read-only.
        del clone_url
        pack_folder = Path(target_folder) / ".git" / "objects" / "pack"
        pack_folder.mkdir(parents=True)
        pack_file = pack_folder / "partial.pack"
        pack_file.write_text("partial")
        pack_file.chmod(0o444)
        (Path(target_folder) / "README.md").write_text("partial")
        raise GitCommandError("clone", 128, stderr="\nfatal: connection lost\n")

    monkeypatch.setattr(workspace, "_clone", failing_clone)

    with pytest.raises(WorkspaceError) as exception_info:
        clone_project(CLONE_URL, str(folder))

    assert str(exception_info.value) == (
        "The clone of the project failed: fatal: connection lost"
    )
    assert os.listdir(folder) == []


def test_014_url_that_looks_like_an_option_is_refused(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError):
        clone_project("--upload-pack=touch evil", str(tmp_path))

    assert os.listdir(tmp_path) == []
