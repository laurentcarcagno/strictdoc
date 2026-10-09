import os
from typing import List, Tuple

from strictdoc.backend.docx.docx_profile import (
    DocxProfile,
    DocxRequirementTable,
)
from strictdoc.backend.docx.import_.docx_reader import (
    DocxReader,
    TrackedChangesMode,
)
from strictdoc.backend.docx.import_.docx_to_sdoc_converter import (
    DocxImportReport,
    DocxToSDocConverter,
)
from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from tests.unit.strictdoc.backend.docx.docx_builder import (
    cell,
    paragraph,
    row,
    run,
    table,
    write_docx,
)


def _requirement_table_profile(**overrides: object) -> DocxProfile:
    requirement_table = DocxRequirementTable(
        id_style="ReqId",
        title_style="ReqTitle",
        meta_rows={"Version:": "VERSION", "Linked Req:": "LINKED_REQ"},
        text_style="ReqText",
        note_label="Note",
        relation_fields=["LINKED_REQ"],
    )
    profile = DocxProfile(
        heading_styles={"Heading1": 1, "Heading2": 2, "Heading3": 3},
        requirement_table=requirement_table,
    )
    for name_, value_ in overrides.items():
        setattr(profile, name_, value_)
    return profile


def _requirement(
    uid: str,
    title: str = "A title",
    version: str = "V0",
    linked: str = "-",
    text: Tuple[str, ...] = ("The system shall work.",),
    note: str = "Note :",
) -> str:
    return table(
        row(cell(paragraph(uid, style="ReqId"))),
        row(cell(paragraph(title, style="ReqTitle"))),
        row(cell(paragraph("Version:")), cell(paragraph(version))),
        row(cell(paragraph("Linked Req:")), cell(paragraph(linked))),
        row(cell(*[paragraph(t, style="ReqText") for t in text])),
        row(cell(paragraph(note))),
    )


def _convert(
    tmp_path: object,
    blocks: List[str],
    profile: DocxProfile,
) -> Tuple[str, SDocDocument, DocxImportReport]:
    path = os.path.join(str(tmp_path), "input.docx")
    write_docx(path, blocks)
    docx_blocks = DocxReader.read(path, TrackedChangesMode.ACCEPT)
    sdoc_text, report = DocxToSDocConverter.build_sdoc_text(
        docx_blocks, profile, "My title"
    )
    document = DocxToSDocConverter.parse(sdoc_text)
    return sdoc_text, document, report


def _nodes(document: SDocDocument) -> List[SDocNode]:
    return [
        node_
        for node_ in document.iterate_nodes("REQUIREMENT")
        if isinstance(node_, SDocNode)
    ]


def test_001_headings_become_nested_sections(tmp_path):
    text, document, report = _convert(
        tmp_path,
        [
            paragraph("One", style="Heading1"),
            paragraph("One A", style="Heading2"),
            paragraph("Two", style="Heading1"),
        ],
        _requirement_table_profile(),
    )
    assert text.count("[[SECTION]]") == 3
    assert text.count("[[/SECTION]]") == 3
    assert text.index("TITLE: One A") < text.index("TITLE: Two")
    assert report.section_count == 3


def test_002_requirement_table_becomes_a_requirement(tmp_path):
    _, document, report = _convert(
        tmp_path,
        [
            paragraph("Chapter", style="Heading1"),
            _requirement("REQ-0001", text=("First.", "Second.")),
        ],
        _requirement_table_profile(),
    )
    assert report.requirement_count == 1
    node = _nodes(document)[0]
    assert node.reserved_uid == "REQ-0001"
    assert node.reserved_title == "A title"
    statement = node.get_content_field().get_text_value()
    assert "First." in statement and "Second." in statement


def test_003_meta_rows_become_fields_in_profile_order(tmp_path):
    text, _, _ = _convert(
        tmp_path,
        [_requirement("REQ-0001", version="V7")],
        _requirement_table_profile(),
    )
    lines = text.splitlines()
    requirement_start = lines.index("[REQUIREMENT]")
    field_names = [
        line_.split(":")[0]
        for line_ in lines[requirement_start + 1 :]
        if line_[:1].isupper() and ":" in line_
    ]
    assert field_names[:5] == [
        "UID",
        "VERSION",
        "LINKED_REQ",
        "TITLE",
        "STATEMENT",
    ]
    assert "VERSION: V7" in text


def test_004_empty_note_is_omitted_and_filled_note_is_kept(tmp_path):
    text_empty, _, _ = _convert(
        tmp_path, [_requirement("REQ-0001")], _requirement_table_profile()
    )
    assert "NOTE:" not in text_empty
    text_filled, _, _ = _convert(
        tmp_path,
        [_requirement("REQ-0001", note="Note : see annex")],
        _requirement_table_profile(),
    )
    assert "NOTE:" in text_filled and "see annex" in text_filled


def test_005_linked_requirements_that_exist_become_parent_relations(tmp_path):
    text, document, report = _convert(
        tmp_path,
        [
            _requirement("REQ-0001"),
            _requirement("REQ-0002", linked="REQ-0001, [DA2] X-7, REQ-0999"),
        ],
        _requirement_table_profile(),
    )
    child = _nodes(document)[1]
    parent_uids = [
        relation_.ref_uid  # type: ignore[attr-defined]
        for relation_ in child.relations
    ]
    assert parent_uids == ["REQ-0001"]
    assert "LINKED_REQ: REQ-0001, [DA2] X-7, REQ-0999" in text
    assert report.unresolved_links == [("REQ-0002", "REQ-0999")]


def test_006_a_requirement_does_not_link_to_itself(tmp_path):
    text, _, report = _convert(
        tmp_path,
        [_requirement("REQ-0001", linked="REQ-0001")],
        _requirement_table_profile(),
    )
    assert "VALUE:" not in text
    assert report.unresolved_links == []


def test_007_free_paragraphs_become_one_text_node(tmp_path):
    text, _, report = _convert(
        tmp_path,
        [
            paragraph("First paragraph."),
            paragraph("Second paragraph."),
            paragraph("Chapter", style="Heading1"),
        ],
        _requirement_table_profile(),
    )
    assert text.count("[TEXT]") == 1
    assert "First paragraph.\n\nSecond paragraph." in text
    assert report.free_paragraph_count == 2


def test_008_list_items_stay_in_one_rst_list(tmp_path):
    text, _, _ = _convert(
        tmp_path,
        [
            paragraph("Intro:"),
            paragraph("one", list_item=True),
            paragraph("two", list_item=True),
        ],
        _requirement_table_profile(),
    )
    assert "Intro:\n\n- one\n- two" in text


def test_009_free_text_can_be_dropped_and_is_still_counted(tmp_path):
    text, _, report = _convert(
        tmp_path,
        [paragraph("Ignored."), paragraph("Chapter", style="Heading1")],
        _requirement_table_profile(free_text="drop"),
    )
    assert "[TEXT]" not in text
    assert report.free_paragraph_count == 1
    assert report.dropped_paragraph_count == 1


def test_010_other_tables_become_rst_list_tables(tmp_path):
    text, _, report = _convert(
        tmp_path,
        [table(row(cell(paragraph("a")), cell(paragraph("b"))))],
        _requirement_table_profile(),
    )
    assert ".. list-table::" in text
    assert "* - a" in text and "- b" in text
    assert report.free_table_count == 1


def test_011_duplicate_uid_is_reported_and_dropped(tmp_path):
    text, document, report = _convert(
        tmp_path,
        [_requirement("REQ-0001"), _requirement("REQ-0001")],
        _requirement_table_profile(),
    )
    assert report.duplicate_uids == ["REQ-0001"]
    assert text.count("UID: REQ-0001") == 1
    assert len(_nodes(document)) == 2


def test_012_invalid_uid_is_reported_and_dropped(tmp_path):
    text, _, report = _convert(
        tmp_path,
        [_requirement("not a uid!")],
        _requirement_table_profile(),
    )
    assert report.invalid_uids == ["not a uid!"]
    assert "UID:" not in text


def test_013_statement_cannot_close_the_multiline_field_early(tmp_path):
    text, document, _ = _convert(
        tmp_path,
        [_requirement("REQ-0001", text=("&lt;&lt;&lt;",))],
        _requirement_table_profile(),
    )
    assert len(_nodes(document)) == 1


def test_014_toc_paragraphs_are_ignored(tmp_path):
    text, _, report = _convert(
        tmp_path,
        [paragraph("1 Intro .... 3", style="TOC1"), paragraph("Body")],
        _requirement_table_profile(),
    )
    assert "Intro ...." not in text
    assert report.free_paragraph_count == 1


def test_015_grammar_lists_profile_fields_and_relations(tmp_path):
    text, _, _ = _convert(
        tmp_path, [_requirement("REQ-0001")], _requirement_table_profile()
    )
    assert "[GRAMMAR]" in text
    assert "TITLE: VERSION" in text and "TITLE: LINKED_REQ" in text
    assert "TITLE: NOTE" in text
    assert "- TYPE: Parent" in text and "- TYPE: File" in text


def test_016_without_a_requirement_table_profile_tables_are_plain(tmp_path):
    text, _, report = _convert(
        tmp_path,
        [_requirement("REQ-0001")],
        _requirement_table_profile(requirement_table=None),
    )
    assert "[REQUIREMENT]" not in text
    assert "[GRAMMAR]" not in text
    assert report.requirement_count == 0
    assert report.free_table_count == 1


def test_017_document_title_comes_from_the_profile_or_the_argument(tmp_path):
    text, _, _ = _convert(tmp_path, [], _requirement_table_profile())
    assert "TITLE: My title" in text
    text, _, _ = _convert(
        tmp_path,
        [],
        _requirement_table_profile(document_title="From profile"),
    )
    assert "TITLE: From profile" in text


def test_018_report_summary_names_the_problems(tmp_path):
    _, _, report = _convert(
        tmp_path,
        [_requirement("REQ-0001", linked="REQ-0009")],
        _requirement_table_profile(),
    )
    summary = report.format()
    assert "1 requirement" in summary
    assert "REQ-0001 -> REQ-0009" in summary


def test_019_the_note_label_is_stripped_even_inside_italic_markup(tmp_path):
    path = os.path.join(str(tmp_path), "input.docx")
    note_cell = cell(
        paragraph(run("Note : see annex.", italic=True)),
    )
    write_docx(
        path,
        [
            table(
                row(cell(paragraph("REQ-1", style="ReqId"))),
                row(cell(paragraph("T", style="ReqTitle"))),
                row(cell(paragraph("Version:")), cell(paragraph("V0"))),
                row(cell(paragraph("Linked Req:")), cell(paragraph("-"))),
                row(cell(paragraph("Shall.", style="ReqText"))),
                row(note_cell),
            )
        ],
    )
    blocks = DocxReader.read(path, TrackedChangesMode.ACCEPT)
    text, _ = DocxToSDocConverter.build_sdoc_text(
        blocks, _requirement_table_profile(), "Doc"
    )
    assert "NOTE: >>>\n*see annex.*\n<<<" in text


def test_020_a_table_without_rows_is_ignored(tmp_path):
    rows_all_inserted = table(
        row(cell(paragraph("x")), row_change="ins"),
    )
    path = os.path.join(str(tmp_path), "input.docx")
    write_docx(path, [rows_all_inserted, paragraph("After.")])
    blocks = DocxReader.read(path, TrackedChangesMode.REJECT)
    text, report = DocxToSDocConverter.build_sdoc_text(
        blocks, _requirement_table_profile(), "Doc"
    )
    assert report.free_table_count == 0
    assert text.count("\n\n\n") == 0
    DocxToSDocConverter.parse(text)
