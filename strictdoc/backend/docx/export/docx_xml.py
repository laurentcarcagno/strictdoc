"""
Small builders for WordprocessingML text. All text is escaped here.
"""

from typing import List, Optional
from xml.sax.saxutils import escape

from strictdoc.backend.docx.export.docx_images import drawing_xml
from strictdoc.backend.docx.export.rst_to_paragraphs import (
    ExportParagraph,
    ExportRun,
)

MONOSPACE_FONT = "Courier New"


def run_xml(run: ExportRun) -> str:
    if run.image is not None:
        return f"<w:r>{drawing_xml(run.image)}</w:r>"
    properties = ""
    if run.bold:
        properties += "<w:b/>"
    if run.italic:
        properties += "<w:i/>"
    if run.monospace:
        properties += (
            f'<w:rFonts w:ascii="{MONOSPACE_FONT}" w:hAnsi="{MONOSPACE_FONT}"/>'
        )
    properties_xml = f"<w:rPr>{properties}</w:rPr>" if properties else ""
    # A newline in the text is a line break of the paragraph.
    pieces = "<w:br/>".join(
        f'<w:t xml:space="preserve">{escape(piece_)}</w:t>'
        for piece_ in run.text.split("\n")
    )
    return f"<w:r>{properties_xml}{pieces}</w:r>"


def paragraph_xml(
    paragraph: ExportParagraph,
    style: Optional[str] = None,
    properties_xml: str = "",
    run_properties_xml: str = "",
) -> str:
    """
    properties_xml replaces the paragraph properties when given (used to keep
    the look of a template paragraph); run_properties_xml is added to every
    run that has no formatting of its own.
    """
    if properties_xml == "" and style is not None:
        properties_xml = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>'
    runs: List[str] = []
    for run_ in paragraph.runs:
        xml = run_xml(run_)
        if run_properties_xml != "" and "<w:rPr>" not in xml:
            xml = xml.replace("<w:r>", f"<w:r>{run_properties_xml}", 1)
        runs.append(xml)
    return f"<w:p>{properties_xml}{''.join(runs)}</w:p>"


def text_paragraph_xml(text: str, style: Optional[str] = None) -> str:
    return paragraph_xml(ExportParagraph([ExportRun(text)]), style)


def empty_paragraph_xml() -> str:
    return "<w:p/>"


def table_xml(rows: List[List[str]], style: Optional[str] = None) -> str:
    """A plain table; every cell is a text."""
    column_count = max((len(row_) for row_ in rows), default=1)
    properties = (
        "<w:tblPr>"
        + (f'<w:tblStyle w:val="{style}"/>' if style is not None else "")
        + '<w:tblW w:w="0" w:type="auto"/><w:tblBorders>'
        + "".join(
            f'<w:{side_} w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
            for side_ in (
                "top",
                "left",
                "bottom",
                "right",
                "insideH",
                "insideV",
            )
        )
        + "</w:tblBorders></w:tblPr>"
    )
    grid = (
        "<w:tblGrid>"
        + '<w:gridCol w:w="2000"/>' * column_count
        + "</w:tblGrid>"
    )
    body_rows = []
    for row_ in rows:
        cells = row_ + [""] * (column_count - len(row_))
        body_rows.append(
            "<w:tr>"
            + "".join(
                '<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr>'
                + text_paragraph_xml(cell_)
                + "</w:tc>"
                for cell_ in cells
            )
            + "</w:tr>"
        )
    return f"<w:tbl>{properties}{grid}{''.join(body_rows)}</w:tbl>"
