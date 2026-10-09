import os
from typing import List

import pytest

from strictdoc.backend.docx.import_.docx_reader import (
    DocxParagraph,
    DocxReader,
    DocxTable,
    TrackedChangesMode,
)
from strictdoc.helpers.exception import StrictDocException
from tests.unit.strictdoc.backend.docx.docx_builder import (
    cell,
    deleted,
    inserted,
    paragraph,
    row,
    run,
    table,
    write_docx,
)


def _read(
    tmp_path: object,
    blocks: List[str],
    mode: TrackedChangesMode = TrackedChangesMode.ACCEPT,
) -> list:  # type: ignore[type-arg]
    path = os.path.join(str(tmp_path), "input.docx")
    write_docx(path, blocks)
    return DocxReader.read(path, mode)


def test_001_paragraph_style_and_text(tmp_path):
    blocks = _read(
        tmp_path,
        [paragraph("Title", style="Heading1"), paragraph("Body text")],
    )
    assert [type(block_) for block_ in blocks] == [DocxParagraph] * 2
    assert blocks[0].style == "Heading1"
    assert blocks[0].text == "Title"
    assert blocks[1].style == ""
    assert blocks[1].text == "Body text"


def test_002_tab_and_line_break_become_space_and_newline(tmp_path):
    xml = "<w:r><w:t>A</w:t><w:tab/><w:t>B</w:t><w:br/><w:t>C</w:t></w:r>"
    blocks = _read(tmp_path, [paragraph(xml)])
    assert blocks[0].text == "A B\nC"


def test_003_accept_mode_keeps_insertions_and_drops_deletions(tmp_path):
    content = run("kept ") + inserted(run("added ")) + deleted("removed")
    blocks = _read(tmp_path, [paragraph(content)], TrackedChangesMode.ACCEPT)
    assert blocks[0].text == "kept added "


def test_004_reject_mode_drops_insertions_and_restores_deletions(tmp_path):
    content = run("kept ") + inserted(run("added ")) + deleted("removed")
    blocks = _read(tmp_path, [paragraph(content)], TrackedChangesMode.REJECT)
    assert blocks[0].text == "kept removed"


def test_005_reject_mode_drops_paragraphs_inserted_as_a_whole(tmp_path):
    blocks = _read(
        tmp_path,
        [
            paragraph("old"),
            paragraph(inserted(run("new")), mark_inserted=True),
        ],
        TrackedChangesMode.REJECT,
    )
    assert [block_.text for block_ in blocks] == ["old"]


def test_006_table_rows_cells_and_paragraphs(tmp_path):
    blocks = _read(
        tmp_path,
        [
            table(
                row(
                    cell(paragraph("A1")),
                    cell(paragraph("B1a"), paragraph("B1b")),
                ),
                row(cell(paragraph("A2")), cell(paragraph("B2"))),
            )
        ],
    )
    assert isinstance(blocks[0], DocxTable)
    assert len(blocks[0].rows) == 2
    second_cell = blocks[0].rows[0][1]
    assert [paragraph_.text for paragraph_ in second_cell.paragraphs] == [
        "B1a",
        "B1b",
    ]


def test_007_tracked_rows_follow_the_mode(tmp_path):
    rows = [
        row(cell(paragraph("normal"))),
        row(cell(paragraph("inserted")), row_change="ins"),
        row(cell(paragraph("deleted")), row_change="del"),
    ]
    accepted = _read(tmp_path, [table(*rows)], TrackedChangesMode.ACCEPT)
    rejected = _read(tmp_path, [table(*rows)], TrackedChangesMode.REJECT)
    texts = lambda block: [  # noqa: E731
        row_[0].paragraphs[0].text for row_ in block.rows
    ]
    assert texts(accepted[0]) == ["normal", "inserted"]
    assert texts(rejected[0]) == ["normal", "deleted"]


def test_008_list_item_is_detected_from_numbering(tmp_path):
    blocks = _read(
        tmp_path,
        [paragraph("item", list_item=True), paragraph("plain")],
    )
    assert blocks[0].is_list_item is True
    assert blocks[1].is_list_item is False


def test_009_bold_italic_and_monospace_runs_become_rst_markup(tmp_path):
    content = (
        run("plain ")
        + run("bold", bold=True)
        + run(" and ")
        + run("italic", italic=True)
        + run(" and ")
        + run("code", font="Courier New")
    )
    blocks = _read(tmp_path, [paragraph(content)])
    assert blocks[0].text == "plain bold and italic and code"
    assert blocks[0].rst == "plain **bold** and *italic* and ``code``"


def test_010_markup_never_swallows_surrounding_spaces(tmp_path):
    content = run("a ") + run(" bold ", bold=True) + run("b")
    blocks = _read(tmp_path, [paragraph(content)])
    assert blocks[0].rst == "a  **bold** b"


def test_011_rst_special_characters_are_escaped(tmp_path):
    blocks = _read(tmp_path, [paragraph("2*3 `x` name_ back\\slash")])
    assert blocks[0].rst == "2\\*3 \\`x\\` name\\_ back\\\\slash"


def test_012_adjacent_runs_with_the_same_format_are_merged(tmp_path):
    content = run("one", bold=True) + run("two", bold=True)
    blocks = _read(tmp_path, [paragraph(content)])
    assert blocks[0].rst == "**onetwo**"


def test_013_a_file_that_is_not_a_docx_is_rejected(tmp_path):
    path = os.path.join(str(tmp_path), "bad.docx")
    with open(path, "w") as file_:
        file_.write("not a zip")
    with pytest.raises(StrictDocException):
        DocxReader.read(path, TrackedChangesMode.ACCEPT)


def test_014_accept_mode_drops_paragraphs_deleted_as_a_whole(tmp_path):
    path = os.path.join(str(tmp_path), "input.docx")
    deleted_paragraph = (
        "<w:p><w:pPr><w:rPr><w:del "
        'w:id="1" w:author="a" w:date="d"/></w:rPr></w:pPr>'
        + deleted("gone")
        + "</w:p>"
    )
    write_docx(path, [paragraph("kept"), deleted_paragraph])
    accepted = DocxReader.read(path, TrackedChangesMode.ACCEPT)
    rejected = DocxReader.read(path, TrackedChangesMode.REJECT)
    assert [block_.text for block_ in accepted] == ["kept"]
    assert [block_.text for block_ in rejected] == ["kept", "gone"]


def test_015_reject_mode_drops_a_table_inserted_as_a_whole(tmp_path):
    path = os.path.join(str(tmp_path), "input.docx")
    inserted_table = table(
        row(cell(paragraph("new")), row_change="ins"),
    )
    write_docx(path, [paragraph("kept"), inserted_table])
    rejected = DocxReader.read(path, TrackedChangesMode.REJECT)
    accepted = DocxReader.read(path, TrackedChangesMode.ACCEPT)
    assert len(rejected) == 1
    assert len(accepted) == 2
