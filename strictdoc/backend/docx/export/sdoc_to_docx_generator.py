"""
Generates a Word document from the content of an SDoc document.
"""

import dataclasses
import os
import re
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from strictdoc.backend.docx.docx_profile import (
    MARKUP_MARKDOWN,
    MARKUP_RST,
    DocxProfile,
    DocxRequirementTable,
)
from strictdoc.backend.docx.export.docx_comments import (
    ExportComment,
    anchor_first_paragraph,
    embed_comments,
)
from strictdoc.backend.docx.export.docx_images import (
    embed_images,
    images_in,
)
from strictdoc.backend.docx.export.docx_template import (
    DocxTemplate,
    split_top_level,
)
from strictdoc.backend.docx.export.docx_xml import (
    empty_paragraph_xml,
    paragraph_xml,
    table_xml,
    text_paragraph_xml,
)
from strictdoc.backend.docx.export.markdown_to_paragraphs import (
    ExportTable,
    markdown_to_blocks,
)
from strictdoc.backend.docx.export.rst_to_paragraphs import (
    ExportImage,
    ExportParagraph,
    ExportRun,
    rst_to_paragraphs,
)
from strictdoc.backend.docx.export.text_to_paragraphs import text_to_paragraphs
from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.core.document_iterator import SDocDocumentIterator
from strictdoc.features.comments.model import parse_comment

# A paragraph is either self-closing or has content. "<w:pPr>" does not match.
PARAGRAPH_PATTERN = re.compile(
    r"<w:p(?:\s[^>]*)?/>|<w:p(?:\s[^>]*)?>.*?</w:p>", re.S
)

DEFAULT_EXPORT_LAYOUT = DocxRequirementTable(
    id_style="RequirementId",
    title_style="RequirementTitle",
    meta_rows={},
    text_style="RequirementText",
    note_label=None,
)


@dataclass
class ExportSection:
    level: int
    title: str


@dataclass
class ExportText:
    statement: str
    # The markup of the SDoc document that the text comes from.
    markup: str = MARKUP_RST
    # The folder of that document: relative image paths start there.
    base_dir: str = ""


@dataclass
class ExportRequirement:
    uid: str
    title: str
    statement: str
    fields: Dict[str, str] = field(default_factory=dict)
    note: str = ""
    markup: str = MARKUP_RST
    base_dir: str = ""
    comments: List[ExportComment] = field(default_factory=list)


@dataclass
class ExportInfoTable:
    """A table of plain texts (the first row is the header)."""

    rows: List[List[str]]


ExportItem = Union[
    ExportSection, ExportText, ExportRequirement, ExportInfoTable
]


def effective_profile(profile: DocxProfile) -> DocxProfile:
    """A profile without a requirement table still exports requirements."""
    if profile.requirement_table is not None:
        return profile
    return dataclasses.replace(profile, requirement_table=DEFAULT_EXPORT_LAYOUT)


def _export_comments(
    node: SDocNode, mode: str, markup: str, base_dir: str
) -> List[ExportComment]:
    """The comments of a node that go to Word, as the profile says."""
    if mode == "none":
        return []
    prefix = re.sub(
        r"[^0-9A-Za-z_-]",
        "_",
        node.reserved_uid or node.reserved_mid.get_string_value(),
    )
    comments: List[ExportComment] = []
    for index_, field_ in enumerate(node.get_comment_fields()):
        comment = parse_comment(field_.get_text_value())
        if comment.is_resolved and mode != "all":
            continue
        identifier = comment.id or f"legacy{index_}"
        comments.append(
            ExportComment(
                key=f"{prefix}-{identifier}",
                author=comment.author,
                date=comment.date,
                body=comment.body,
                resolved=comment.is_resolved,
                markup=markup,
                base_dir=base_dir,
            )
        )
    return comments


def items_from_document(
    document: SDocDocument,
    layout: DocxRequirementTable,
    comments: str = "none",
) -> List[ExportItem]:
    items: List[ExportItem] = []
    markup = (
        document.config.get_markup()
        if document.config is not None
        else MARKUP_RST
    )
    base_dir = (
        os.path.dirname(document.meta.input_doc_full_path)
        if document.meta is not None
        else ""
    )
    iterator = SDocDocumentIterator(document=document, node_filter=None)
    for node_, context_ in iterator.all_content(print_fragments=False):
        if not isinstance(node_, SDocNode):
            continue
        if node_.node_type == "SECTION":
            items.append(
                ExportSection(context_.get_level(), node_.reserved_title or "")
            )
        elif node_.node_type == "TEXT":
            items.append(ExportText(_content(node_), markup, base_dir))
        elif node_.node_type == "REQUIREMENT":
            fields = {
                name_: _field_value(node_, name_)
                for name_ in layout.meta_rows.values()
            }
            note = (
                _field_value(node_, layout.note_field)
                if layout.note_label is not None
                else ""
            )
            items.append(
                ExportRequirement(
                    uid=node_.reserved_uid or "",
                    title=node_.reserved_title or "",
                    statement=_content(node_),
                    fields=fields,
                    note=note,
                    markup=markup,
                    base_dir=base_dir,
                    comments=_export_comments(
                        node_, comments, markup, base_dir
                    ),
                )
            )
    return items


def _content(node: SDocNode) -> str:
    return node.get_content_field().get_text_value()


def _field_value(node: SDocNode, field_name: str) -> str:
    fields = node.ordered_fields_lookup.get(field_name)
    return fields[0].get_text_value().strip() if fields else ""


class DocxGenerator:
    @staticmethod
    def generate(
        items: List[ExportItem],
        profile: DocxProfile,
        template: DocxTemplate,
    ) -> Dict[str, bytes]:
        profile = effective_profile(profile)
        assert profile.requirement_table is not None
        heading_styles = heading_style_by_level(profile)
        body: List[str] = []
        for item_ in items:
            if isinstance(item_, ExportSection):
                level = min(item_.level, max(heading_styles))
                body.append(
                    text_paragraph_xml(item_.title, heading_styles[level])
                )
            elif isinstance(item_, ExportText):
                body.extend(
                    _text_blocks(item_.statement, item_.markup, item_.base_dir)
                )
            elif isinstance(item_, ExportInfoTable):
                body.append(table_xml(item_.rows))
                body.append(empty_paragraph_xml())
            else:
                body.append(
                    requirement_xml(
                        item_,
                        profile.requirement_table,
                        template.requirement_skeleton,
                    )
                )
                body.append(empty_paragraph_xml())
        package = template.build_package("".join(body))
        embed_images(package, collect_item_images(items))
        embed_comments(package, collect_item_comments(items))
        return package

    @staticmethod
    def write(package: Dict[str, bytes], path: str) -> None:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as output_:
            for name_, data_ in package.items():
                output_.writestr(name_, data_)


def collect_item_images(items: List[ExportItem]) -> Dict[str, ExportImage]:
    """The images that the text of the items uses, by token."""
    paragraphs: List[ExportParagraph] = []
    for item_ in items:
        if isinstance(item_, ExportText):
            if item_.markup == MARKUP_MARKDOWN:
                paragraphs.extend(
                    block_
                    for block_ in markdown_to_blocks(
                        item_.statement, item_.base_dir
                    )
                    if isinstance(block_, ExportParagraph)
                )
        elif isinstance(item_, ExportRequirement):
            for text_ in (item_.statement, item_.note):
                paragraphs.extend(
                    text_to_paragraphs(text_, item_.markup, item_.base_dir)
                )
    return images_in(paragraphs)


def collect_item_comments(items: List[ExportItem]) -> List[ExportComment]:
    """The comments of the requirements of the items."""
    return [
        comment_
        for item_ in items
        if isinstance(item_, ExportRequirement)
        for comment_ in item_.comments
    ]


def heading_style_by_level(profile: DocxProfile) -> Dict[int, str]:
    """Level -> style. A level the profile does not name uses the one above."""
    named: Dict[int, str] = {}
    for style_, level_ in profile.heading_styles.items():
        named.setdefault(level_, style_)
    by_level: Dict[int, str] = {}
    previous_style = named[min(named)]
    for level_ in range(1, max(named) + 1):
        previous_style = named.get(level_, previous_style)
        by_level[level_] = previous_style
    return by_level


def _text_blocks(
    statement: str, markup: str = MARKUP_RST, base_dir: str = ""
) -> List[str]:
    if markup == MARKUP_MARKDOWN:
        blocks: List[str] = []
        for block_ in markdown_to_blocks(statement, base_dir):
            if isinstance(block_, ExportTable):
                blocks.append(table_xml(block_.rows))
                blocks.append(empty_paragraph_xml())
            else:
                blocks.append(paragraph_xml(block_))
        return blocks
    if statement.lstrip().startswith(".. list-table::"):
        return [table_xml(_parse_list_table(statement)), empty_paragraph_xml()]
    return [paragraph_xml(p_) for p_ in rst_to_paragraphs(statement)]


def _parse_list_table(rst: str) -> List[List[str]]:
    rows: List[List[str]] = []
    for line_ in rst.split("\n")[1:]:
        stripped = line_.strip()
        if stripped.startswith("* -"):
            rows.append([_plain(stripped[3:])])
        elif stripped.startswith("-") and len(rows) > 0:
            rows[-1].append(_plain(stripped[1:]))
    return rows


def _plain(text: str) -> str:
    text = text.strip()
    runs: List[ExportRun] = [
        run_ for p_ in rst_to_paragraphs(text) for run_ in p_.runs
    ]
    return "".join(run_.text for run_ in runs)


def requirement_xml(
    requirement: ExportRequirement,
    layout: DocxRequirementTable,
    skeleton: str,
) -> str:
    head_end = skeleton.index("<w:tr")
    head = skeleton[:head_end]
    rows = re.findall(r"<w:tr\b.*?</w:tr>", skeleton, re.S)
    out_rows: List[str] = []
    text_row_done = False
    for row_ in rows:
        role = row_role(row_, layout, text_row_done)
        if role == "id":
            out_rows.append(_fill_row(row_, [[_p(requirement.uid)]]))
        elif role == "title":
            out_rows.append(_fill_row(row_, [[_p(requirement.title)]]))
        elif role.startswith("meta:"):
            value = requirement.fields.get(role[5:], "")
            out_rows.append(_fill_row(row_, [None, [_p(value)]]))
        elif role == "text":
            text_row_done = True
            paragraphs = text_to_paragraphs(
                requirement.statement, requirement.markup, requirement.base_dir
            )
            out_rows.append(_fill_row(row_, [paragraphs or [_p("")]]))
        elif role == "note":
            note_paragraphs = text_to_paragraphs(
                requirement.note, requirement.markup, requirement.base_dir
            )
            out_rows.append(
                fill_note_row(row_, note_paragraphs, layout.note_label or "")
            )
        elif role == "keep":
            out_rows.append(row_)
    return anchor_first_paragraph(
        head + "".join(out_rows) + "</w:tbl>", requirement.comments
    )


def _p(text: str) -> ExportParagraph:
    return ExportParagraph([ExportRun(text)] if len(text) > 0 else [])


def row_role(
    row_xml: str, layout: DocxRequirementTable, text_row_done: bool
) -> str:
    cells = re.findall(r"<w:tc\b.*?</w:tc>", row_xml, re.S)
    first_style = re.search(r'<w:pStyle w:val="([^"]*)"/>', cells[0])
    style = first_style.group(1) if first_style is not None else ""
    label = text_of(cells[0]).strip()
    if style == layout.id_style:
        return "id"
    if layout.title_style is not None and style == layout.title_style:
        return "title"
    if len(cells) >= 2 and label in layout.meta_rows:
        return "meta:" + layout.meta_rows[label]
    if layout.note_label is not None and label.startswith(layout.note_label):
        return "note"
    if len(cells) == 1 and not text_row_done:
        return "text"
    return "drop"


def text_of(xml: str) -> str:
    return "".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", xml))


def _fill_row(
    row_xml: str,
    cell_contents: List[Optional[List[ExportParagraph]]],
) -> str:
    """Replaces the paragraphs of the cells that have content (not None)."""
    cells = re.findall(r"<w:tc\b.*?</w:tc>", row_xml, re.S)
    result = row_xml
    for index_, cell_ in enumerate(cells):
        content = cell_contents[index_] if index_ < len(cell_contents) else None
        if content is not None:
            result = result.replace(
                cell_, replace_cell_paragraphs(cell_, content), 1
            )
    return result


def fill_note_row(
    row_xml: str, note: List[ExportParagraph], note_label: str
) -> str:
    """
    Writes the label ("Note :") and the note. The first paragraph of the note
    follows the label in the same paragraph, as in the documents this
    importer reads. Whatever else the template cell holds goes.
    """
    cell_pattern = re.compile(r"<w:tc\b.*?</w:tc>", re.S)
    cell_match = cell_pattern.search(row_xml)
    if cell_match is None:
        return row_xml
    cell_xml = cell_match.group(0)
    paragraph_match = PARAGRAPH_PATTERN.search(cell_xml)
    if paragraph_match is None:
        return row_xml
    prototype = paragraph_match.group(0)
    label_match = re.match(
        rf"\s*{re.escape(note_label)}\s*:?", text_of(prototype)
    )
    label = label_match.group(0).strip() if label_match else f"{note_label} :"
    paragraphs = [ExportParagraph([ExportRun(label)])]
    if len(note) > 0:
        paragraphs = [
            ExportParagraph([ExportRun(label + " ")] + note[0].runs),
            *note[1:],
        ]
    new_paragraphs = "".join(paragraph_like(prototype, p_) for p_ in paragraphs)
    end_of_content = cell_xml.rindex("</w:tc>")
    new_cell = (
        cell_xml[: paragraph_match.start()]
        + new_paragraphs
        + cell_xml[end_of_content:]
    )
    return row_xml.replace(cell_xml, new_cell, 1)


def replace_cell_paragraphs(
    cell_xml: str, paragraphs: List[ExportParagraph]
) -> str:
    match = PARAGRAPH_PATTERN.search(cell_xml)
    prototype = match.group(0) if match is not None else "<w:p/>"
    start = match.start() if match is not None else cell_xml.rindex("</w:tc>")
    end = cell_xml.rindex("</w:tc>")
    new_paragraphs = "".join(
        paragraph_like(prototype, paragraph_) for paragraph_ in paragraphs
    ) or paragraph_like(prototype, ExportParagraph())
    return cell_xml[:start] + new_paragraphs + cell_xml[end:]


def paragraph_like(prototype: str, paragraph: ExportParagraph) -> str:
    """A paragraph that looks like the prototype: same properties and font."""
    properties = re.search(r"<w:pPr>.*?</w:pPr>", prototype, re.S)
    run_properties = re.search(
        r"<w:r\b[^>]*>(<w:rPr>.*?</w:rPr>)", prototype, re.S
    )
    return paragraph_xml(
        paragraph,
        properties_xml=properties.group(0) if properties is not None else "",
        run_properties_xml=run_properties.group(1)
        if run_properties is not None
        else "",
    )


__all__ = [
    "DocxGenerator",
    "ExportInfoTable",
    "ExportItem",
    "ExportRequirement",
    "ExportSection",
    "ExportText",
    "collect_item_images",
    "effective_profile",
    "items_from_document",
    "split_top_level",
]
