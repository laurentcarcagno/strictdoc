from developer.tools import sdoc_to_markdown as script

GRAMMAR = """\
[GRAMMAR]
ELEMENTS:
- TAG: SECTION
  PROPERTIES:
    IS_COMPOSITE: True
    PREFIX: None
  FIELDS:
  - TITLE: MID
    TYPE: String
    REQUIRED: False
  - TITLE: TITLE
    TYPE: String
    REQUIRED: True
- TAG: TEXT
  FIELDS:
  - TITLE: STATEMENT
    TYPE: String
    REQUIRED: True
- TAG: REQUIREMENT
  FIELDS:
  - TITLE: UID
    TYPE: String
    REQUIRED: False
  - TITLE: VERSION
    TYPE: String
    REQUIRED: False
  - TITLE: TITLE
    TYPE: String
    REQUIRED: True
  - TITLE: STATEMENT
    TYPE: String
    REQUIRED: True
"""

DOCUMENT = (
    """\
[DOCUMENT]
TITLE: Document
OPTIONS:
  VIEW_STYLE: Table
  NODE_IN_TOC: False

"""
    + GRAMMAR
    + """
[TEXT]
STATEMENT: >>>
Cover page.
<<<

[TEXT]
STATEMENT: >>>
Second cover text.
<<<

[[SECTION]]
MID: 0a0a0a0a0a0a4a0a8a0a0a0a0a0a0a01
TITLE: Section

[TEXT]
STATEMENT: >>>
Intro.


Two blank lines above.
<<<

[REQUIREMENT]
UID: REQ-1
VERSION: V0
TITLE: Requirement
STATEMENT: >>>
The system shall do X.
<<<

[[/SECTION]]
"""
)


def test_001_a_document_with_a_grammar_gets_a_grammar_file():
    conversion = script.convert_text(DOCUMENT, "/project/document.sdoc")

    assert conversion.skipped_reason is None
    assert conversion.grammar_file_name == "document.gra.md"
    markdown = conversion.document_markdown
    assert markdown is not None
    assert "**Grammar**: document.gra.md" in markdown
    # The text nodes stay two nodes, and the section keeps its marker.
    assert "**Type**: TEXT\n\nSecond cover text." in markdown
    assert "**Type**: SECTION" in markdown
    # Two blank lines in a row are not valid Markdown.
    assert "\n\n\n" not in markdown


def test_002_the_order_of_the_fields_of_the_grammar_is_kept():
    conversion = script.convert_text(DOCUMENT, "/project/document.sdoc")

    grammar = conversion.grammar_markdown
    assert grammar is not None
    requirement = grammar.split("## Element: REQUIREMENT")[1]
    assert requirement.index("Field: UID") < requirement.index("Field: VERSION")
    assert requirement.index("Field: VERSION") < requirement.index(
        "Field: TITLE"
    )


def test_003_the_prefix_none_of_an_element_is_kept():
    conversion = script.convert_text(DOCUMENT, "/project/document.sdoc")

    assert "**Prefix**: None" in (conversion.grammar_markdown or "")


def test_004_the_options_of_the_document_become_metadata_keys():
    conversion = script.convert_text(DOCUMENT, "/project/document.sdoc")

    markdown = conversion.document_markdown
    assert markdown is not None
    assert "**View style**: Table" in markdown
    assert "**Node in TOC**: False" in markdown
    assert conversion.warnings == []


def test_004b_the_relation_field_option_is_reported_as_lost():
    text = DOCUMENT.replace(
        "OPTIONS:\n", "OPTIONS:\n  RELATION_FIELD: LINKED_REQ\n"
    )
    conversion = script.convert_text(text, "/project/document.sdoc")

    assert conversion.warnings == ["option RELATION_FIELD: LINKED_REQ is lost"]


def test_004c_a_document_in_html_is_not_converted():
    text = DOCUMENT.replace("OPTIONS:\n", "OPTIONS:\n  MARKUP: HTML\n")
    conversion = script.convert_text(text, "/project/document.sdoc")

    assert conversion.document_markdown is None
    assert conversion.skipped_reason is not None
    assert "HTML" in conversion.skipped_reason


def test_005_a_document_that_includes_another_is_skipped(tmp_path):
    (tmp_path / "part.sdoc").write_text(
        "[DOCUMENT]\nTITLE: Part\n", encoding="utf8"
    )
    conversion = script.convert_text(
        "[DOCUMENT]\nTITLE: D\n\n[DOCUMENT_FROM_FILE]\nFILE: part.sdoc\n",
        str(tmp_path / "document.sdoc"),
    )

    assert conversion.document_markdown is None
    assert conversion.skipped_reason is not None
    assert "DOCUMENT_FROM_FILE" in conversion.skipped_reason


def test_005b_an_include_in_a_code_block_is_not_an_include():
    text = (
        "[DOCUMENT]\nTITLE: D\n\n[TEXT]\nSTATEMENT: >>>\n```strictdoc\n"
        "[DOCUMENT_FROM_FILE]\nFILE: example.sdoc\n```\n<<<\n"
    )
    conversion = script.convert_text(text, "/project/document.sdoc")

    assert conversion.skipped_reason is None
    assert "FILE: example.sdoc" in (conversion.document_markdown or "")


def test_006_a_grammar_in_an_sgra_file_is_skipped():
    conversion = script.convert_text(
        "[DOCUMENT]\nTITLE: D\n\n[GRAMMAR]\nIMPORT_FROM_FILE: grammar.sgra\n",
        "/project/document.sdoc",
    )

    assert conversion.skipped_reason is not None
    assert "grammar.sgra" in conversion.skipped_reason


def test_007_blank_lines_in_fenced_code_are_kept():
    markdown = "a\n\n\nb\n\n```\nc\n\n\nd\n```\n"

    assert script.collapse_blank_lines(markdown) == (
        "a\n\nb\n\n```\nc\n\n\nd\n```\n"
    )


def test_008_the_output_folder_is_checked_and_written(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "document.sdoc").write_text(DOCUMENT, encoding="utf8")
    output = tmp_path / "output"

    exit_code = script.main(
        [str(source), "--output-dir", str(output), "--check"]
    )

    assert exit_code == 0
    assert (output / "document.md").is_file()
    assert (output / "document.gra.md").is_file()
    assert (source / "document.sdoc").is_file()


def test_009_in_place_renames_then_converts(tmp_path):
    (tmp_path / "document.sdoc").write_text(DOCUMENT, encoding="utf8")

    assert script.main([str(tmp_path), "--in-place", "--rename-only"]) == 0
    assert not (tmp_path / "document.sdoc").exists()
    assert (
        (tmp_path / "document.md")
        .read_text(encoding="utf8")
        .startswith("[DOCUMENT]")
    )

    assert script.main([str(tmp_path), "--in-place", "--check"]) == 0
    markdown = (tmp_path / "document.md").read_text(encoding="utf8")
    assert markdown.startswith("# Document")
    assert (tmp_path / "document.gra.md").is_file()


def test_010_a_document_that_does_not_read_back_the_same_writes_nothing(
    tmp_path, monkeypatch
):
    source = tmp_path / "source"
    source.mkdir()
    (source / "document.sdoc").write_text(DOCUMENT, encoding="utf8")
    output = tmp_path / "output"
    monkeypatch.setattr(
        script,
        "check_conversion",
        lambda *_arguments: ["Document: REQ-1: the field(s) STATEMENT differ"],
    )

    exit_code = script.main(
        [str(source), "--output-dir", str(output), "--check"]
    )

    assert exit_code == 1
    assert not output.exists()


LINKED_DOCUMENT = """\
[DOCUMENT]
TITLE: Linked

[REQUIREMENT]
UID: PARENT-1
TITLE: Parent
STATEMENT: >>>
The system shall do X.
<<<

[REQUIREMENT]
UID: PARENT-2
TITLE: Other parent
STATEMENT: >>>
The system shall do Y.
<<<

[REQUIREMENT]
UID: CHILD-1
TITLE: Child
STATEMENT: >>>
The software shall do X.
<<<
RELATIONS:
- TYPE: Parent
  VALUE: PARENT-1
- TYPE: Parent
  VALUE: PARENT-2
"""


def test_011_the_reviewed_links_take_the_hash_of_the_converted_parent(
    tmp_path,
):
    (tmp_path / "linked.sdoc").write_text(LINKED_DOCUMENT, encoding="utf8")
    fields = ["TITLE", "STATEMENT"]
    old = script.convert_text(
        LINKED_DOCUMENT, str(tmp_path / "linked.sdoc"), fields
    )
    # The text of a Markdown field has not the line end of an SDoc field.
    assert old.old_hashes["PARENT-1"] != old.new_hashes["PARENT-1"]
    baseline = script.Baseline(
        {
            "CHILD-1 < PARENT-1": old.old_hashes["PARENT-1"],
            # The link to PARENT-2 was suspect before the conversion.
            "CHILD-1 < PARENT-2": "0" * 40,
        }
    )

    updated, suspect = script.rebaseline(
        baseline, old.old_hashes, old.new_hashes
    )

    assert (updated, suspect) == (1, 1)
    assert baseline.entries["CHILD-1 < PARENT-1"] == old.new_hashes["PARENT-1"]
    assert baseline.entries["CHILD-1 < PARENT-2"] == "0" * 40


def test_012_main_rewrites_the_baseline_next_to_the_converted_documents(
    tmp_path,
):
    source = tmp_path / "source"
    source.mkdir()
    (source / "linked.sdoc").write_text(LINKED_DOCUMENT, encoding="utf8")
    old = script.convert_text(
        LINKED_DOCUMENT, "linked.sdoc", ["TITLE", "STATEMENT"]
    )
    baseline = script.Baseline(
        {"CHILD-1 < PARENT-1": old.old_hashes["PARENT-1"]}
    )
    baseline.save(str(source / "trace_baseline.json"))
    output = tmp_path / "output"

    assert script.main([str(source), "--output-dir", str(output)]) == 0

    converted = script.Baseline.load(str(output / "trace_baseline.json"))
    assert converted.entries == {
        "CHILD-1 < PARENT-1": old.new_hashes["PARENT-1"]
    }
