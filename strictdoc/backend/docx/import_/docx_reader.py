"""
Reads the body of a Word (.docx) file into paragraphs and tables.

A .docx file is a zip package. This reader uses only the standard library and
reads word/document.xml. Tracked changes are resolved on reading: accepted
(insertions kept, deletions dropped) or rejected (the opposite).
"""

import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Union

from strictdoc.helpers.exception import StrictDocException
from strictdoc.helpers.file_system import file_open_read_bytes

WORD_NAMESPACE = (
    "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
)

MONOSPACE_FONTS = ("Courier New", "Consolas", "Lucida Console", "Courier")


class TrackedChangesMode(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"


@dataclass
class DocxParagraph:
    style: str
    # Plain text, without markup.
    text: str
    # The same text with RST inline markup for bold, italic and monospace.
    rst: str
    is_list_item: bool = False


@dataclass
class DocxCell:
    paragraphs: List[DocxParagraph] = field(default_factory=list)


@dataclass
class DocxTable:
    rows: List[List[DocxCell]] = field(default_factory=list)


DocxBlock = Union[DocxParagraph, DocxTable]

# One piece of text with its formatting: (text, bold, italic, monospace).
_Segment = Tuple[str, bool, bool, bool]


class DocxReader:
    @staticmethod
    def read(path: str, mode: TrackedChangesMode) -> List[DocxBlock]:
        root = _parse_document_xml(path)
        body = root.find(WORD_NAMESPACE + "body")
        if body is None:
            raise StrictDocException(f"Not a Word document: {path}.")
        blocks: List[DocxBlock] = []
        for element_ in body:
            if element_.tag == WORD_NAMESPACE + "p":
                paragraph = _read_paragraph(element_, mode)
                if paragraph is not None:
                    blocks.append(paragraph)
            elif element_.tag == WORD_NAMESPACE + "tbl":
                table = _read_table(element_, mode)
                # A table whose rows were all removed by the mode is gone.
                if (
                    len(table.rows) > 0
                    or element_.find(WORD_NAMESPACE + "tr") is None
                ):
                    blocks.append(table)
        return blocks


def read_table_element(
    element: ET.Element, mode: TrackedChangesMode
) -> DocxTable:
    """Reads a w:tbl element that the caller has parsed."""
    return _read_table(element, mode)


def _parse_document_xml(path: str) -> ET.Element:
    try:
        with file_open_read_bytes(path) as file_:
            with zipfile.ZipFile(file_) as package_:
                document_xml = package_.read("word/document.xml")
        return ET.fromstring(document_xml)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exception_:
        raise StrictDocException(
            f"Could not read {path} as a Word document: {exception_}."
        ) from exception_


def _read_table(element: ET.Element, mode: TrackedChangesMode) -> DocxTable:
    table = DocxTable()
    for row_element_ in element.findall(WORD_NAMESPACE + "tr"):
        if _is_row_dropped(row_element_, mode):
            continue
        cells: List[DocxCell] = []
        for cell_element_ in row_element_.findall(WORD_NAMESPACE + "tc"):
            cells.append(_read_cell(cell_element_, mode))
        table.rows.append(cells)
    return table


def _is_row_dropped(row_element: ET.Element, mode: TrackedChangesMode) -> bool:
    row_properties = row_element.find(WORD_NAMESPACE + "trPr")
    if row_properties is None:
        return False
    dropped_tag = "del" if mode == TrackedChangesMode.ACCEPT else "ins"
    return row_properties.find(WORD_NAMESPACE + dropped_tag) is not None


def _read_cell(element: ET.Element, mode: TrackedChangesMode) -> DocxCell:
    cell = DocxCell()
    for child_ in element:
        if child_.tag == WORD_NAMESPACE + "p":
            paragraph = _read_paragraph(child_, mode)
            if paragraph is not None:
                cell.paragraphs.append(paragraph)
        elif child_.tag == WORD_NAMESPACE + "tbl":
            # A nested table is flattened into one paragraph per row.
            for nested_row_ in _read_table(child_, mode).rows:
                texts = [
                    " ".join(paragraph_.text for paragraph_ in cell_.paragraphs)
                    for cell_ in nested_row_
                ]
                text = " | ".join(texts)
                cell.paragraphs.append(
                    DocxParagraph("", text, _escape_rst(text))
                )
    return cell


def _read_paragraph(
    element: ET.Element, mode: TrackedChangesMode
) -> Optional[DocxParagraph]:
    properties = element.find(WORD_NAMESPACE + "pPr")
    style = ""
    is_list_item = False
    mark_is_inserted = False
    mark_is_deleted = False
    if properties is not None:
        style_element = properties.find(WORD_NAMESPACE + "pStyle")
        if style_element is not None:
            style = style_element.get(WORD_NAMESPACE + "val", "")
        is_list_item = properties.find(WORD_NAMESPACE + "numPr") is not None
        mark_properties = properties.find(WORD_NAMESPACE + "rPr")
        if mark_properties is not None:
            mark_is_inserted = (
                mark_properties.find(WORD_NAMESPACE + "ins") is not None
            )
            mark_is_deleted = (
                mark_properties.find(WORD_NAMESPACE + "del") is not None
            )

    segments: List[_Segment] = []
    _collect_segments(element, mode, False, False, False, segments)
    text = "".join(segment_[0] for segment_ in segments)
    # A paragraph that the mode removes, whose text is gone: nothing is left.
    mark_is_removed = (
        mark_is_inserted
        if mode == TrackedChangesMode.REJECT
        else mark_is_deleted
    )
    if mark_is_removed and len(text.strip()) == 0:
        return None
    return DocxParagraph(
        style=style,
        text=text,
        rst=_segments_to_rst(segments),
        is_list_item=is_list_item,
    )


def _collect_segments(
    element: ET.Element,
    mode: TrackedChangesMode,
    bold: bool,
    italic: bool,
    monospace: bool,
    segments: List[_Segment],
) -> None:
    for child_ in element:
        tag = child_.tag
        if tag == WORD_NAMESPACE + "pPr":
            continue
        if tag == WORD_NAMESPACE + "ins":
            if mode == TrackedChangesMode.ACCEPT:
                _collect_segments(
                    child_, mode, bold, italic, monospace, segments
                )
        elif tag == WORD_NAMESPACE + "del":
            if mode == TrackedChangesMode.REJECT:
                _collect_segments(
                    child_, mode, bold, italic, monospace, segments
                )
        elif tag == WORD_NAMESPACE + "r":
            run_bold, run_italic, run_monospace = _read_run_format(
                child_, bold, italic, monospace
            )
            for run_child_ in child_:
                text = _run_child_text(run_child_)
                if text is not None:
                    segments.append((text, run_bold, run_italic, run_monospace))
        else:
            # Hyperlinks, smart tags, structured document tags, fields.
            _collect_segments(child_, mode, bold, italic, monospace, segments)


def _read_run_format(
    run_element: ET.Element, bold: bool, italic: bool, monospace: bool
) -> Tuple[bool, bool, bool]:
    properties = run_element.find(WORD_NAMESPACE + "rPr")
    if properties is None:
        return bold, italic, monospace
    if _is_switched_on(properties.find(WORD_NAMESPACE + "b")):
        bold = True
    if _is_switched_on(properties.find(WORD_NAMESPACE + "i")):
        italic = True
    fonts = properties.find(WORD_NAMESPACE + "rFonts")
    if fonts is not None:
        font_name = fonts.get(WORD_NAMESPACE + "ascii", "")
        if font_name in MONOSPACE_FONTS:
            monospace = True
    return bold, italic, monospace


def _is_switched_on(element: Optional[ET.Element]) -> bool:
    if element is None:
        return False
    value = element.get(WORD_NAMESPACE + "val")
    return value is None or value.lower() not in ("0", "false", "off")


def _run_child_text(element: ET.Element) -> Optional[str]:
    tag = element.tag
    if tag in (WORD_NAMESPACE + "t", WORD_NAMESPACE + "delText"):
        return element.text if element.text is not None else ""
    if tag == WORD_NAMESPACE + "tab":
        return " "
    if tag == WORD_NAMESPACE + "br":
        return "\n"
    if tag == WORD_NAMESPACE + "noBreakHyphen":
        return "-"
    return None


def _segments_to_rst(segments: List[_Segment]) -> str:
    merged: List[_Segment] = []
    for segment_ in segments:
        if len(merged) > 0 and merged[-1][1:] == segment_[1:]:
            previous = merged[-1]
            merged[-1] = (previous[0] + segment_[0], *previous[1:])
        else:
            merged.append(segment_)

    pieces: List[str] = []
    for text_, bold_, italic_, monospace_ in merged:
        core = text_.strip(" ")
        if len(core) == 0 or not (bold_ or italic_ or monospace_):
            pieces.append(_escape_rst(text_))
            continue
        leading = text_[: len(text_) - len(text_.lstrip(" "))]
        trailing = text_[len(text_.rstrip(" ")) :]
        if monospace_:
            marked = "``" + core + "``"
        else:
            marker = "**" if bold_ else "*"
            marked = marker + _escape_rst(core) + marker
        pieces.append(leading + marked + trailing)
    return "".join(pieces)


def _escape_rst(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace("*", "\\*")
    text = text.replace("`", "\\`")
    return re.sub(r"(?<=\w)_(?=\W|$)", r"\\_", text)
