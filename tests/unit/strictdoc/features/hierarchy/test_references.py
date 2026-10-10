from pathlib import Path

import pytest

from strictdoc.features.hierarchy.references import (
    KIND_SECTION,
    KIND_UID,
    DictSource,
    Reference,
    ReferenceResolver,
    parse_references,
)

VALUES = (
    (Path(__file__).parent / "req02_linked_req_values.txt")
    .read_text(encoding="utf-8")
    .splitlines()
)


def test_001_all_the_real_values_of_req02_are_parsed():
    assert len(VALUES) == 131
    parsed = [parse_references(value_) for value_ in VALUES]
    # "-" is the only value without any reference.
    assert {v for v, p in zip(VALUES, parsed) if not p} == {"-"}
    total = sum(len(refs_) for refs_ in parsed)
    assert total > 150


def test_002_a_section_and_a_list_of_uids():
    assert parse_references(
        "[DA1] §5.14.1 ; [DA2] REQ-106005, REQ-106006, REQ-0280"
    ) == [
        Reference("DA1", KIND_SECTION, "5.14.1"),
        Reference("DA2", KIND_UID, "REQ-106005"),
        Reference("DA2", KIND_UID, "REQ-106006"),
        Reference("DA2", KIND_UID, "REQ-0280"),
    ]


def test_003_a_group_without_a_tag_continues_the_previous_one():
    assert parse_references("[DA2] REQ-1 ; REQ-2") == [
        Reference("DA2", KIND_UID, "REQ-1"),
        Reference("DA2", KIND_UID, "REQ-2"),
    ]


def test_004_several_sections_and_an_empty_tag():
    assert parse_references("[DA2] §1, §4.3") == [
        Reference("DA2", KIND_SECTION, "1"),
        Reference("DA2", KIND_SECTION, "4.3"),
    ]
    assert parse_references("[DA2] REQ-106011, REQ-0280 ; [DA4]") == [
        Reference("DA2", KIND_UID, "REQ-106011"),
        Reference("DA2", KIND_UID, "REQ-0280"),
    ]


@pytest.mark.parametrize("text", ["", "-", "  ", ";", "[DA1]", "[]", "§"])
def test_005_no_reference(text):
    assert parse_references(text) == []


@pytest.mark.parametrize(
    "text", ["[", "]]", ";;;", "[DA1] §", "\x00", "[DA1" * 1000]
)
def test_006_the_parser_never_fails(text):
    parse_references(text)


def test_007_a_value_without_a_tag_has_no_document():
    assert parse_references("REQ-1") == [Reference(None, KIND_UID, "REQ-1")]


SOURCE = DictSource(
    uids={
        "DA1": ["ISIS-PUS-REQ-1420", "ISIS-PUS-REQ-1430"],
        "DA2": [
            "ISIS-OBCPB-E70-01-REQ-106005",
            "ISIS-OBCPB-E70-01-REQ-106006",
            "REQ-0280",
            "X-REQ-0280",
        ],
    },
    sections={"DA1": {"5.14.1": "SEC-5-14-1", "5.14": None}, "DA2": {}},
)


def test_008_uids_resolve_exactly_or_by_their_short_form():
    result = ReferenceResolver(SOURCE).resolve(
        "[DA2] REQ-106005, REQ-106006 ; [DA1] ISIS-PUS-REQ-1420"
    )
    assert result.uids == [
        "ISIS-OBCPB-E70-01-REQ-106005",
        "ISIS-OBCPB-E70-01-REQ-106006",
        "ISIS-PUS-REQ-1420",
    ]
    assert result.unresolved == []


def test_009_an_exact_uid_wins_over_a_short_form_match():
    result = ReferenceResolver(SOURCE).resolve("[DA2] REQ-0280")
    assert result.uids == ["REQ-0280"]


def test_010_an_ambiguous_short_form_is_reported_not_guessed():
    source = DictSource(uids={"DA2": ["A-REQ-1", "B-REQ-1"]})
    result = ReferenceResolver(source).resolve("[DA2] REQ-1")
    assert result.uids == []
    assert "ambiguous" in result.unresolved[0]


def test_011_a_section_resolves_to_the_uid_of_the_section():
    result = ReferenceResolver(SOURCE).resolve("[DA1] §5.14.1")
    assert result.uids == ["SEC-5-14-1"]


def test_012_a_section_without_uid_or_that_does_not_exist_is_reported():
    result = ReferenceResolver(SOURCE).resolve("[DA1] §5.14 ; [DA1] §9")
    assert result.uids == []
    assert "has no UID" in result.unresolved[0]
    assert "no section 9" in result.unresolved[1]


def test_013_unknown_documents_and_requirements_are_reported():
    result = ReferenceResolver(SOURCE).resolve("[DA9] REQ-1 ; [DA2] REQ-404")
    result.unresolved += ReferenceResolver(SOURCE).resolve("REQ-5").unresolved
    assert result.uids == []
    assert len(result.unresolved) == 3
    assert "not an applicable document" in result.unresolved[0]
    assert "no such requirement" in result.unresolved[1]
    assert "no applicable document named" in result.unresolved[2]


def test_014_a_uid_is_listed_once():
    result = ReferenceResolver(SOURCE).resolve("[DA2] REQ-0280, REQ-0280")
    assert result.uids == ["REQ-0280"]
