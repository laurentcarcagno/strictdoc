import pytest

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.features.projects.store import ProjectStore, clean_user
from strictdoc.features.reviewers.reviewers import (
    can_comment,
    document_reviewers,
    parse_reviewers,
    set_document_reviewers,
    set_metadata,
    unknown_reviewers,
)
from strictdoc.helpers.exception import StrictDocException


def test_001_the_store_keeps_projects_and_members(tmp_path):
    path = str(tmp_path / "state" / "projects.json")
    store = ProjectStore(path)
    assert store.projects() == {} and store.members("x") == {}

    store.add_project("x", "The X", "ann", "2026-01-01T00:00:00+00:00")
    store.set_member("x", " Bob ", "author")
    store.set_member("x", "ann", "administrator")
    again = ProjectStore(path)
    assert again.projects()["x"]["title"] == "The X"
    assert again.role_of("x", "BOB") == "author"
    assert again.slugs_of("ann") == ["x"]
    assert again.remove_member("x", "bob") is True
    assert again.remove_member("x", "bob") is False
    assert again.role_of("x", "bob") is None


def test_002_the_store_refuses_a_bad_user_or_role(tmp_path):
    store = ProjectStore(str(tmp_path / "projects.json"))
    with pytest.raises(StrictDocException):
        store.set_member("x", "bob", "owner")
    for name in ("", "a b", "../x", "<script>"):
        with pytest.raises(StrictDocException):
            clean_user(name)


def test_003_reviewers_are_parsed_and_checked():
    assert parse_reviewers(" Ann, bob;ann  carol ") == ["ann", "bob", "carol"]
    assert parse_reviewers("") == []
    members = {"ann", "bob"}
    assert unknown_reviewers(["ann", "zoe"], members.__contains__) == ["zoe"]
    assert unknown_reviewers(["zoe"], None) == []


def test_004_reviewers_live_in_the_metadata_of_the_document():
    document = SDocDocument(
        mid=None,
        title="D",
        config=None,
        view=None,
        grammar=None,
        section_contents=[],
    )
    assert document_reviewers(document) == []
    set_document_reviewers(document, ["ann", "bob"])
    assert document_reviewers(document) == ["ann", "bob"]
    set_metadata(document, "OTHER", "x")
    set_document_reviewers(document, ["carol"])
    assert document_reviewers(document) == ["carol"]
    set_document_reviewers(document, [])
    assert document_reviewers(document) == []
    assert document.config.custom_metadata is not None
    set_metadata(document, "OTHER", "")
    assert document.config.custom_metadata is None


def test_005_who_may_comment():
    document = SDocDocument(
        mid=None,
        title="D",
        config=None,
        view=None,
        grammar=None,
        section_contents=[],
    )
    set_document_reviewers(document, ["carol"])
    assert can_comment("author", "eric", document)
    assert can_comment("reviewer", "eric", document)
    assert can_comment("reader", "Carol", document)
    assert not can_comment("reader", "dan", document)
    assert not can_comment(None, "dan", document)
