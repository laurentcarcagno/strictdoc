import subprocess

import pytest

from strictdoc.backend.sdoc.reader import SDReader
from strictdoc.features.html2pdf.changes import changed_nodes_since_last_tag

DOCUMENT = """\
[DOCUMENT]
TITLE: Spec

[[SECTION]]
UID: SEC-1
TITLE: Section one

[REQUIREMENT]
UID: REQ-1
TITLE: First
STATEMENT: The system shall start.

[REQUIREMENT]
UID: REQ-2
TITLE: Second
STATEMENT: The system shall stop.

[TEXT]
STATEMENT: Free text.

[[/SECTION]]
"""


def _git(root, *args):
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            *args,
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "a.sdoc").write_text(DOCUMENT, encoding="utf8")
    _git(tmp_path, "add", "a.sdoc")
    _git(tmp_path, "commit", "-q", "-m", "one")
    return tmp_path


def _changed_uids(path):
    text = path.read_text(encoding="utf8")
    document = SDReader.read(text, file_path=str(path))
    changed = changed_nodes_since_last_tag(document, str(path))
    if changed is None:
        return None
    found = set()
    stack = list(document.section_contents)
    while stack:
        node = stack.pop()
        stack.extend(getattr(node, "section_contents", []) or [])
        if id(node) in changed:
            uid = node.reserved_uid
            found.add(uid or node.node_type)
    return found


def test_001_no_tag_means_nothing_to_compare(repo):
    assert _changed_uids(repo / "a.sdoc") is None


def test_002_an_unchanged_document_has_no_change(repo):
    _git(repo, "tag", "A1")
    assert _changed_uids(repo / "a.sdoc") == set()


def test_003_a_modified_and_a_new_node_are_marked(repo):
    _git(repo, "tag", "A1")
    text = DOCUMENT.replace("shall stop.", "shall stop at once.")
    text = text.replace(
        "[TEXT]",
        "[REQUIREMENT]\nUID: REQ-3\nTITLE: Third\nSTATEMENT: New.\n\n[TEXT]",
    )
    (repo / "a.sdoc").write_text(text, encoding="utf8")
    assert _changed_uids(repo / "a.sdoc") == {"REQ-2", "REQ-3"}


def test_004_a_comment_is_not_a_change(repo):
    _git(repo, "tag", "A1")
    text = DOCUMENT.replace(
        "STATEMENT: The system shall start.",
        "STATEMENT: The system shall start.\nCOMMENT: Why not.",
    )
    (repo / "a.sdoc").write_text(text, encoding="utf8")
    assert _changed_uids(repo / "a.sdoc") == set()


def test_005_the_latest_tag_is_the_reference(repo):
    _git(repo, "tag", "A1")
    (repo / "a.sdoc").write_text(
        DOCUMENT.replace("shall start.", "shall start now."), encoding="utf8"
    )
    _git(repo, "commit", "-q", "-am", "two")
    _git(repo, "tag", "A2")
    assert _changed_uids(repo / "a.sdoc") == set()


def test_006_a_document_that_is_new_since_the_tag_is_all_new(repo):
    _git(repo, "tag", "A1")
    (repo / "b.sdoc").write_text(DOCUMENT, encoding="utf8")
    assert _changed_uids(repo / "b.sdoc") >= {"REQ-1", "REQ-2", "SEC-1"}
