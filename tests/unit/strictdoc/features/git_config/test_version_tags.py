"""
@relation(SDOC-SRS-215, scope=file)
"""

import subprocess
from pathlib import Path

from strictdoc.features.git_config.git_service import GitService
from strictdoc.features.git_config.versioning import sorted_version_tags


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_001_version_tags_are_sorted_by_version() -> None:
    tags = ["B1", "A", "A2", "release-1", "A1", "ZA1", "Z"]

    assert sorted_version_tags(tags) == ["A1", "A2", "A", "B1", "Z", "ZA1"]
    assert sorted_version_tags(tags, reverse=True) == [
        "ZA1",
        "Z",
        "B1",
        "A",
        "A2",
        "A1",
    ]


def test_002_the_service_lists_the_tags_and_reads_a_file_at_a_tag(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init", "-q", "-b", "master")
    _git(tmp_path, "config", "user.name", "Init")
    _git(tmp_path, "config", "user.email", "init@example.com")
    document = tmp_path / "doc.sdoc"
    document.write_text("first\n", encoding="utf8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "first version")
    _git(tmp_path, "tag", "A1")
    document.write_text("second\n", encoding="utf8")
    _git(tmp_path, "commit", "-q", "-am", "second version")
    _git(tmp_path, "tag", "A2")
    _git(tmp_path, "tag", "not-a-version")

    service = GitService(str(tmp_path))
    tags = service.version_tags_of(str(document))

    assert [tag_.name for tag_ in tags] == ["A2", "A1"]
    assert tags[0].subject == "second version"
    assert len(tags[0].date) == 10
    assert service.text_at_tag(str(document), "A1") == "first\n"
    assert service.text_at_tag(str(document), "A2") == "second\n"
    assert service.text_at_tag(str(tmp_path / "other.sdoc"), "A1") is None
