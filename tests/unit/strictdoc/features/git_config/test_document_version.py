"""
@relation(SDOC-SRS-210, scope=file)
"""

import subprocess
from pathlib import Path

from strictdoc.features.git_config.document_version import (
    latest_version_of_file,
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repository_with_document(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "master")
    _git(path, "config", "user.name", "Init")
    _git(path, "config", "user.email", "init@example.com")
    document = path / "specs" / "doc.sdoc"
    document.parent.mkdir()
    document.write_text("[DOCUMENT]\nTITLE: A\n")
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "doc")
    return document


def test_01_no_repository_has_no_version(tmp_path: Path) -> None:
    document = tmp_path / "doc.sdoc"
    document.write_text("[DOCUMENT]\nTITLE: A\n")

    assert latest_version_of_file(str(document)) is None


def test_02_repository_without_version_tag_has_no_version(
    tmp_path: Path,
) -> None:
    document = _repository_with_document(tmp_path / "repository")
    _git(tmp_path / "repository", "tag", "release-1")

    assert latest_version_of_file(str(document)) is None


def test_03_latest_version_tag_is_the_version(tmp_path: Path) -> None:
    document = _repository_with_document(tmp_path / "repository")
    for tag_ in ("A1", "A2", "A", "B1", "not-a-version"):
        _git(tmp_path / "repository", "tag", tag_)

    assert latest_version_of_file(str(document)) == "B1"


def test_04_major_tag_is_above_its_drafts(tmp_path: Path) -> None:
    document = _repository_with_document(tmp_path / "repository")
    for tag_ in ("A1", "A2", "A"):
        _git(tmp_path / "repository", "tag", tag_)

    assert latest_version_of_file(str(document)) == "A"
