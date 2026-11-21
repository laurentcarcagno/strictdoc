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


def test_004_the_lost_options_are_reported():
    conversion = script.convert_text(DOCUMENT, "/project/document.sdoc")

    assert "option NODE_IN_TOC: False is lost" in conversion.warnings
    assert "option VIEW_STYLE: Table is lost" in conversion.warnings


def test_005_a_document_that_includes_another_is_skipped():
    conversion = script.convert_text(
        "[DOCUMENT]\nTITLE: D\n\n[DOCUMENT_FROM_FILE]\nFILE: part.sdoc\n",
        "/project/document.sdoc",
    )

    assert conversion.document_markdown is None
    assert conversion.skipped_reason is not None
    assert "DOCUMENT_FROM_FILE" in conversion.skipped_reason


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
