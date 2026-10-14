import pytest

from strictdoc.features.git_config.versioning import (
    InvalidVersionTag,
    NoMajorVersionToTag,
    next_intermediate_tag,
    next_major_tag,
    parse_version_tag,
)


def test_parse_draft_and_major() -> None:
    draft = parse_version_tag("B2")
    assert (draft.letters, draft.number) == ("B", 2)
    major = parse_version_tag("B")
    assert (major.letters, major.number) == ("B", None)


@pytest.mark.parametrize("tag", ["", "a1", "1", "A1B", "A01", "A-1", "v1.0"])
def test_parse_rejects_invalid(tag: str) -> None:
    with pytest.raises(InvalidVersionTag):
        parse_version_tag(tag)


def test_first_tags_of_an_untagged_repository() -> None:
    assert next_intermediate_tag([]) == "A1"
    with pytest.raises(NoMajorVersionToTag):
        next_major_tag([])


def test_cycle_a1_to_b2() -> None:
    tags = ["A1"]
    assert next_intermediate_tag(tags) == "A2"
    tags.append("A2")
    assert next_major_tag(tags) == "A"
    tags.append("A")
    assert next_intermediate_tag(tags) == "B1"
    tags.append("B1")
    assert next_intermediate_tag(tags) == "B2"
    tags.extend(["B2"])
    assert next_intermediate_tag(tags) == "B3"
    assert next_major_tag(tags) == "B"


def test_major_cannot_be_tagged_twice() -> None:
    with pytest.raises(NoMajorVersionToTag):
        next_major_tag(["A1", "A"])


def test_foreign_tags_are_ignored() -> None:
    tags = ["v1.0", "release-2", "A1", "junk"]
    assert next_intermediate_tag(tags) == "A2"


def test_latest_is_chosen_by_order_not_by_position() -> None:
    assert next_intermediate_tag(["B2", "A", "A1", "B1"]) == "B3"


def test_major_above_drafts_of_same_letter_is_latest() -> None:
    assert next_intermediate_tag(["B2", "B"]) == "C1"


def test_overflow_after_z() -> None:
    assert next_intermediate_tag(["Z"]) == "ZA1"
    assert next_intermediate_tag(["ZA1"]) == "ZA2"
    assert next_major_tag(["ZA2"]) == "ZA"
    assert next_intermediate_tag(["ZY"]) == "ZZ1"
    assert next_intermediate_tag(["ZZ"]) == "ZZA1"
    assert next_intermediate_tag(["Z", "ZA", "ZB1"]) == "ZB2"


def test_longer_letters_sort_above_shorter() -> None:
    assert next_intermediate_tag(["Z9", "ZA1"]) == "ZA2"
