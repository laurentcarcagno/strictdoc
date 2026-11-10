"""
@relation(SDOC-SRS-213, scope=file)
"""

import subprocess
from pathlib import Path

from strictdoc.features.git_config.git_service import GitService
from strictdoc.features.item_page.service import block_lines_of_uid

DOCUMENT = """[DOCUMENT]
TITLE: Item page

[REQUIREMENT]
UID: REQ-1
STATEMENT: First version.

[REQUIREMENT]
UID: REQ-2
STATEMENT: Other item.
"""


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _commit(repository: Path, text: str, message: str) -> Path:
    document = repository / "doc.sdoc"
    document.write_text(text, encoding="utf8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-q", "-m", message)
    return document


def test_001_block_lines_of_a_uid(tmp_path: Path) -> None:
    document = tmp_path / "doc.sdoc"
    document.write_text(DOCUMENT, encoding="utf8")

    assert block_lines_of_uid(str(document), "REQ-1") == (4, 6)
    assert block_lines_of_uid(str(document), "REQ-2") == (8, 10)
    assert block_lines_of_uid(str(document), "REQ-3") is None


def test_002_history_follows_the_lines_of_one_item(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q", "-b", "master")
    _git(repository, "config", "user.name", "Init")
    _git(repository, "config", "user.email", "init@example.com")
    _commit(repository, DOCUMENT, "create")
    _commit(
        repository,
        DOCUMENT.replace("First version.", "Second version."),
        "change REQ-1",
    )
    document = _commit(
        repository,
        DOCUMENT.replace("First version.", "Second version.").replace(
            "Other item.", "Another item."
        ),
        "change REQ-2",
    )

    service = GitService(str(repository))
    first, last = block_lines_of_uid(str(document), "REQ-1") or (0, 0)
    revisions = service.history_of_lines(str(document), first, last)

    assert [revision_.subject for revision_ in revisions] == [
        "change REQ-1",
        "create",
    ]
    assert "+STATEMENT: Second version." in revisions[0].patch
