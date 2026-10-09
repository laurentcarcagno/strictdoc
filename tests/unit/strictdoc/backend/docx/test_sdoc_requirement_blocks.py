from strictdoc.backend.docx.import_.sdoc_requirement_blocks import (
    parse_grammar_extra_fields,
    parse_requirement_blocks,
)

SDOC = """[DOCUMENT]
TITLE: Doc

[GRAMMAR]
ELEMENTS:
- TAG: REQUIREMENT
  FIELDS:
  - TITLE: UID
    TYPE: String
    REQUIRED: False
  - TITLE: TITLE
    TYPE: String
    REQUIRED: True
  - TITLE: STATEMENT
    TYPE: String
    REQUIRED: True
  - TITLE: OWNER
    TYPE: String
    REQUIRED: False
  - TITLE: ASIL
    TYPE: SingleChoice(A, B)
    REQUIRED: False
  RELATIONS:
  - TYPE: Parent
  - TYPE: File

[[SECTION]]
TITLE: Chapter

[REQUIREMENT]
UID: REQ-1
TITLE: First
STATEMENT: >>>
Line one.

[REQUIREMENT] is not a new block inside a multiline field.
<<<
OWNER: Alice
RELATIONS:
- TYPE: Parent
  VALUE: REQ-0
- TYPE: File
  VALUE: src/a.c
  ROLE: Implementation

[TEXT]
STATEMENT: >>>
Free text.
<<<

[REQUIREMENT]
TITLE: No uid
STATEMENT: Single line.

[[/SECTION]]
"""


def test_001_blocks_are_indexed_by_uid_and_blocks_without_uid_are_skipped():
    blocks = parse_requirement_blocks(SDOC)
    assert list(blocks) == ["REQ-1"]


def test_002_fields_keep_their_raw_value_in_order():
    block = parse_requirement_blocks(SDOC)["REQ-1"]
    assert [name_ for name_, _ in block.fields] == [
        "UID",
        "TITLE",
        "STATEMENT",
        "OWNER",
    ]
    statement = dict(block.fields)["STATEMENT"]
    assert statement.startswith(">>>\nLine one.")
    assert "[REQUIREMENT] is not a new block" in statement
    assert statement.endswith("<<<")
    assert dict(block.fields)["OWNER"] == "Alice"


def test_003_only_file_relations_are_kept():
    block = parse_requirement_blocks(SDOC)["REQ-1"]
    assert block.file_relations == [
        ["- TYPE: File", "  VALUE: src/a.c", "  ROLE: Implementation"]
    ]


def test_004_extra_grammar_fields_are_the_unowned_string_ones():
    extras = parse_grammar_extra_fields(
        SDOC, owned_names=["UID", "TITLE", "STATEMENT"]
    )
    assert [name_ for name_, _ in extras] == ["OWNER"]
    assert extras[0][1] == [
        "  - TITLE: OWNER",
        "    TYPE: String",
        "    REQUIRED: False",
    ]


def test_005_a_document_without_a_requirement_grammar_has_no_extras():
    assert parse_grammar_extra_fields("[DOCUMENT]\nTITLE: x\n", []) == []
