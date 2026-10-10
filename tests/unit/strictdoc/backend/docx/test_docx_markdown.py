import os
from typing import List, Tuple

from strictdoc.backend.docx.docx_profile import (
    DocxProfile,
    DocxRequirementTable,
)
from strictdoc.backend.docx.export.docx_template import DocxTemplate
from strictdoc.backend.docx.export.docx_tracked_update import DocxUpdater
from strictdoc.backend.docx.export.markdown_to_paragraphs import (
    ExportTable,
    markdown_to_blocks,
    markdown_to_paragraphs,
)
from strictdoc.backend.docx.export.sdoc_to_docx_generator import (
    DocxGenerator,
    items_from_document,
)
from strictdoc.backend.docx.import_.docx_reader import (
    DocxReader,
    TrackedChangesMode,
)
from strictdoc.backend.docx.import_.docx_to_sdoc_converter import (
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

PROFILE = DocxProfile(
    heading_styles={"Heading1": 1},
    requirement_table=DocxRequirementTable(
        id_style="ReqId",
        title_style="ReqTitle",
        meta_rows={"Version:": "VERSION"},
        text_style="ReqText",
        note_label="Note",
    ),
    markup="Markdown",
)


def _texts(markdown: str) -> List[str]:
    return [
        "".join(run_.text for run_ in paragraph_.runs)
        for paragraph_ in markdown_to_paragraphs(markdown)
    ]


def test_001_paragraphs_formats_and_line_breaks():
    paragraphs = markdown_to_paragraphs(
        "A **bold**, an *italic*, `code` and ***both***.\\\nNext line.\n\n"
        "Second paragraph."
    )
    assert len(paragraphs) == 2
    runs = paragraphs[0].runs
    assert [(r.text, r.bold, r.italic, r.monospace) for r in runs] == [
        ("A ", False, False, False),
        ("bold", True, False, False),
        (", an ", False, False, False),
        ("italic", False, True, False),
        (", ", False, False, False),
        ("code", False, False, True),
        (" and ", False, False, False),
        ("both", True, True, False),
        (".\nNext line.", False, False, False),
    ]


def test_002_lists_keep_their_markers_and_nesting():
    assert _texts("- one\n  - nested\n- two\n\n3. c\n4. d\n") == [
        "- one",
        "  - nested",
        "- two",
        "3. c",
        "4. d",
    ]


def test_003_headings_code_links_images_and_html():
    assert _texts(
        "# Title\n\n```python\nx = 1\ny = 2\n```\n\n"
        "[site](http://x.org) and [same](same)\n\n"
        "![pic](./_assets/p.png)\n\n<br />\n\nSee [LINK: R-1].\n"
    ) == [
        "Title",
        "x = 1",
        "y = 2",
        "site (http://x.org) and same (same)",
        "[image: p.png]",
        "See [LINK: R-1].",
    ]
    heading, code = markdown_to_paragraphs("# T\n\n```\nx\n```\n")
    assert heading.runs[0].bold
    assert code.runs[0].monospace


def test_004_a_table_is_a_table_block_or_one_paragraph_per_row():
    markdown = "| a | b |\n| --- | --- |\n| 1 | **2** |\n"
    blocks = markdown_to_blocks(markdown)
    assert blocks == [ExportTable([["a", "b"], ["1", "2"]])]
    assert _texts(markdown) == ["a | b", "1 | 2"]


def _requirement_table(uid: str, *texts: str, note: str = "Note :") -> str:
    return table(
        row(cell(paragraph(uid, style="ReqId"))),
        row(cell(paragraph("Title " + uid, style="ReqTitle"))),
        row(cell(paragraph("Version:")), cell(paragraph("V1"))),
        row(cell(*texts)),
        row(cell(paragraph(note))),
    )


def _import(tmp_path, blocks: List[str]) -> Tuple[str, SDocDocument]:
    path = os.path.join(str(tmp_path), "input.docx")
    write_docx(path, blocks)
    sdoc_text, _ = DocxToSDocConverter.build_sdoc_text(
        DocxReader.read(path, TrackedChangesMode.ACCEPT), PROFILE, "Spec"
    )
    return sdoc_text, DocxToSDocConverter.parse(sdoc_text)


def _export(tmp_path, document: SDocDocument, name: str = "out.docx") -> str:
    items = items_from_document(document, PROFILE.requirement_table)  # type: ignore[arg-type]
    package = DocxGenerator.generate(
        items, PROFILE, DocxTemplate.minimal(PROFILE)
    )
    path = os.path.join(str(tmp_path), name)
    DocxGenerator.write(package, path)
    return path


def _statement(document: SDocDocument, index: int = 0) -> str:
    nodes = [
        node_
        for node_ in document.section_contents
        if isinstance(node_, SDocNode) and node_.node_type == "REQUIREMENT"
    ]
    return nodes[index].get_content_field().get_text_value()


RICH = (
    paragraph(
        run("Use ")
        + run("bold", bold=True)
        + run(" and ")
        + run("italic", italic=True)
        + run(" and ")
        + run("a_b", font="Courier New")
        + run(", snake_case and 1 &lt; 2."),
        style="ReqText",
    ),
    paragraph("one", style="ReqText", list_item=True),
    paragraph("two", style="ReqText", list_item=True),
    paragraph("1. first", style="ReqText"),
    paragraph("2. second", style="ReqText"),
)


def test_005_word_to_markdown_to_word_to_markdown_is_stable(tmp_path):
    sdoc_text, document = _import(tmp_path, [_requirement_table("R-1", *RICH)])
    assert document.config.markup == "Markdown"
    exported = _export(tmp_path, document)

    blocks = DocxReader.read(exported, TrackedChangesMode.ACCEPT)
    again, _ = DocxToSDocConverter.build_sdoc_text(blocks, PROFILE, "Spec")
    assert _statement(DocxToSDocConverter.parse(again)) == _statement(document)
    assert again == sdoc_text


def test_006_the_exported_word_text_has_the_formats(tmp_path):
    _, document = _import(tmp_path, [_requirement_table("R-1", *RICH)])
    exported = _export(tmp_path, document)
    (reqs,) = [
        b
        for b in DocxReader.read(exported, TrackedChangesMode.ACCEPT)
        if hasattr(b, "rows")
    ]
    statement = reqs.rows[3][0].paragraphs
    first = statement[0]
    assert "**bold**" in first.markdown and "*italic*" in first.markdown
    assert "`a_b`" in first.markdown
    assert [p.text for p in statement[1:]] == [
        "- one",
        "- two",
        "1. first",
        "2. second",
    ]


def test_007_update_finds_no_difference_for_an_unchanged_markdown_model(
    tmp_path,
):
    _, document = _import(tmp_path, [_requirement_table("R-1", *RICH)])
    base = _export(tmp_path, document, "base.docx")
    _, report = DocxUpdater.update(
        base,
        items_from_document(document, PROFILE.requirement_table),
        PROFILE,  # type: ignore[arg-type]
    )
    assert (len(report.added), len(report.changed), len(report.deleted)) == (
        0,
        0,
        0,
    )
    assert report.unchanged == 1


def test_008_update_reports_a_changed_markdown_statement(tmp_path):
    _, document = _import(tmp_path, [_requirement_table("R-1", *RICH)])
    base = _export(tmp_path, document, "base.docx")
    _, edited = _import(
        tmp_path,
        [
            _requirement_table(
                "R-1", paragraph("A different statement.", style="ReqText")
            )
        ],
    )
    package, report = DocxUpdater.update(
        base,
        items_from_document(edited, PROFILE.requirement_table),
        PROFILE,  # type: ignore[arg-type]
    )
    assert report.changed == {"R-1": ["STATEMENT"]}
    assert b"<w:ins " in package["word/document.xml"]


def test_009_update_does_not_flag_tables_images_or_breaks_as_changes(tmp_path):
    text = (
        "Intro with a hard break\\\nsecond line.\n\n"
        "| a | b |\n| --- | --- |\n| 1 | 2 |\n\n"
        "![1.00](./_assets/p/pic.png)\n\n- one\n- two\n"
    )
    source = (
        "[DOCUMENT]\nTITLE: Spec\nOPTIONS:\n  MARKUP: Markdown\n\n"
        "[REQUIREMENT]\nUID: R-1\nTITLE: T\nSTATEMENT: >>>\n" + text + "<<<\n"
    )
    document = DocxToSDocConverter.parse(source)
    base = _export(tmp_path, document, "base.docx")
    _, report = DocxUpdater.update(
        base,
        items_from_document(document, PROFILE.requirement_table),
        PROFILE,  # type: ignore[arg-type]
    )
    assert report.changed == {}
    assert report.unchanged == 1
