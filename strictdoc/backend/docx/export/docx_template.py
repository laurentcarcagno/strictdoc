"""
The Word template of an export.

A template is a .docx file that supplies everything except the generated
content: styles, headers, footers, numbering, page setup and the front matter
(cover page, table of contents). The generated content replaces the body from
the first heading that follows the table of contents. The look of a
requirement comes from the first requirement table of the template.

Without a template file, a minimal one is built from the profile.
"""

import re
import zipfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from strictdoc.backend.docx.docx_profile import (
    DocxProfile,
    DocxRequirementTable,
)
from strictdoc.helpers.exception import StrictDocException
from strictdoc.helpers.file_system import file_open_read_bytes

WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
RELATIONSHIPS_NAMESPACE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)

_TOP_LEVEL_TAG = re.compile(r"<(/?)w:(p|tbl|sdt)(?=[\s/>])[^>]*?(/?)>")
_TOC_FIELD = re.compile(r"<w:instrText[^>]*>\s*TOC\b")
_SETTINGS_ANCHORS = (
    "<w:hdrShapeDefaults",
    "<w:footnotePr",
    "<w:endnotePr",
    "<w:compat",
    "<w:docVars",
    "<w:rsids",
)


@dataclass
class DocxTemplate:
    # Every part of the package, in order. word/document.xml is replaced when
    # the output is written.
    parts: List[Tuple[str, bytes]]
    document_head: str
    front_matter: str
    section_properties: str
    document_tail: str
    # A cleaned <w:tbl> to clone for each requirement.
    requirement_skeleton: str
    has_table_of_contents: bool

    @staticmethod
    def load(path: str, profile: DocxProfile) -> "DocxTemplate":
        assert profile.requirement_table is not None
        try:
            with file_open_read_bytes(path) as file_:
                with zipfile.ZipFile(file_) as package_:
                    parts = [
                        (name_, package_.read(name_))
                        for name_ in package_.namelist()
                    ]
        except zipfile.BadZipFile as exception_:
            raise StrictDocException(
                f"Could not read the template {path}: {exception_}."
            ) from exception_
        document_xml = dict(parts).get("word/document.xml")
        if document_xml is None:
            raise StrictDocException(
                f"The template {path} has no word/document.xml."
            )
        return DocxTemplate._from_document_xml(
            parts, document_xml.decode("utf8"), profile
        )

    @staticmethod
    def minimal(profile: DocxProfile) -> "DocxTemplate":
        layout = profile.requirement_table
        assert layout is not None
        document_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{WORD_NAMESPACE}"><w:body>'
            "</w:body></w:document>"
        )
        parts = [
            ("[Content_Types].xml", _CONTENT_TYPES.encode("utf8")),
            ("_rels/.rels", _ROOT_RELATIONSHIPS.encode("utf8")),
            ("word/document.xml", document_xml.encode("utf8")),
            (
                "word/_rels/document.xml.rels",
                _DOCUMENT_RELATIONSHIPS.encode("utf8"),
            ),
            ("word/styles.xml", _styles_xml(profile).encode("utf8")),
        ]
        template = DocxTemplate._from_document_xml(
            parts, document_xml, profile, skeleton=_skeleton_xml(layout)
        )
        return template

    @staticmethod
    def _from_document_xml(
        parts: List[Tuple[str, bytes]],
        document_xml: str,
        profile: DocxProfile,
        skeleton: Optional[str] = None,
    ) -> "DocxTemplate":
        layout = profile.requirement_table
        assert layout is not None
        body_start = document_xml.index("<w:body>") + len("<w:body>")
        body_end = document_xml.rindex("</w:body>")
        chunks = split_top_level(document_xml[body_start:body_end])

        section_properties = ""
        if len(chunks) > 0 and chunks[-1].startswith("<w:sectPr"):
            section_properties = chunks.pop()

        front_end = _front_matter_end(chunks, profile)
        front_matter = "".join(chunks[:front_end])
        has_toc = _TOC_FIELD.search(front_matter) is not None
        if has_toc:
            front_matter = _mark_table_of_contents_dirty(front_matter)

        if skeleton is None:
            skeleton = _find_skeleton(chunks, layout)
        if skeleton is None:
            skeleton = _skeleton_xml(layout)
        return DocxTemplate(
            parts=parts,
            document_head=document_xml[:body_start],
            front_matter=front_matter,
            section_properties=section_properties,
            document_tail=document_xml[body_end:],
            requirement_skeleton=skeleton,
            has_table_of_contents=has_toc,
        )

    def build_package(self, body_xml: str) -> Dict[str, bytes]:
        """The package parts with the generated body in place."""
        document_xml = (
            self.document_head
            + self.front_matter
            + body_xml
            + self.section_properties
            + self.document_tail
        )
        result: Dict[str, bytes] = {}
        for name_, data_ in self.parts:
            if name_ == "word/document.xml":
                result[name_] = document_xml.encode("utf8")
            elif name_ == "word/settings.xml" and self.has_table_of_contents:
                updated = _request_field_update(data_.decode("utf8"))
                result[name_] = updated.encode("utf8")
            else:
                result[name_] = data_
        return result


def split_top_level(body_xml: str) -> List[str]:
    """
    Splits the content of w:body into top-level chunks: paragraphs, tables and
    structured document tags (with everything they contain), and the single
    tags between them.
    """
    chunks: List[str] = []
    depth = 0
    chunk_start = 0
    position = 0
    for match_ in _TOP_LEVEL_TAG.finditer(body_xml):
        is_closing = match_.group(1) == "/"
        is_self_closing = match_.group(3) == "/"
        if depth == 0 and not is_closing:
            if match_.start() > chunk_start:
                chunks.extend(
                    _split_between(body_xml[chunk_start : match_.start()])
                )
            chunk_start = match_.start()
        if is_self_closing:
            if depth == 0:
                chunks.append(body_xml[chunk_start : match_.end()])
                chunk_start = match_.end()
        elif is_closing:
            depth -= 1
            if depth == 0:
                chunks.append(body_xml[chunk_start : match_.end()])
                chunk_start = match_.end()
        else:
            depth += 1
        position = match_.end()
    if chunk_start < len(body_xml):
        chunks.extend(_split_between(body_xml[chunk_start:]))
    del position
    return chunks


def _split_between(xml: str) -> List[str]:
    """Single tags and the section properties that sit between chunks."""
    xml = xml.strip()
    if len(xml) == 0:
        return []
    section = re.search(r"<w:sectPr\b.*?</w:sectPr>", xml, re.S)
    if section is None:
        return [xml]
    before = xml[: section.start()].strip()
    after = xml[section.end() :].strip()
    result = [before] if len(before) > 0 else []
    result.append(section.group(0))
    if len(after) > 0:
        result.append(after)
    return result


def _front_matter_end(chunks: List[str], profile: DocxProfile) -> int:
    heading_markers = [
        f'<w:pStyle w:val="{style_}"/>' for style_ in profile.heading_styles
    ]
    last_toc_index = -1
    for index_, chunk_ in enumerate(chunks):
        if _TOC_FIELD.search(chunk_) is not None:
            last_toc_index = index_
    for index_ in range(last_toc_index + 1, len(chunks)):
        chunk_ = chunks[index_]
        if chunk_.startswith("<w:p") and any(
            marker_ in chunk_ for marker_ in heading_markers
        ):
            return index_
    return len(chunks) if last_toc_index >= 0 else 0


def _mark_table_of_contents_dirty(xml: str) -> str:
    return re.sub(
        r'(<w:fldChar w:fldCharType="begin")(/>(?:(?!<w:fldChar).)*?'
        r"<w:instrText[^>]*>\s*TOC\b)",
        r'\1 w:dirty="true"\2',
        xml,
        flags=re.S,
    )


def _request_field_update(settings_xml: str) -> str:
    if "<w:updateFields" in settings_xml:
        return settings_xml
    for anchor_ in _SETTINGS_ANCHORS:
        if anchor_ in settings_xml:
            return settings_xml.replace(
                anchor_, '<w:updateFields w:val="true"/>' + anchor_, 1
            )
    return settings_xml.replace(
        "</w:settings>", '<w:updateFields w:val="true"/></w:settings>', 1
    )


def _find_skeleton(
    chunks: List[str], layout: DocxRequirementTable
) -> Optional[str]:
    marker = f'<w:pStyle w:val="{layout.id_style}"/>'
    for chunk_ in chunks:
        if not chunk_.startswith("<w:tbl"):
            continue
        first_style = re.search(r'<w:pStyle w:val="([^"]*)"/>', chunk_)
        has_nested_table = chunk_.count("<w:tbl>") > 1
        if (
            first_style is not None
            and marker == first_style.group(0)
            and not has_nested_table
        ):
            return clean_skeleton(chunk_)
    return None


def clean_skeleton(table_xml: str) -> str:
    """
    Removes what must not be cloned: tracked changes (kept as accepted), spell
    check marks, bookmarks, revision ids and paragraph ids.
    """
    xml = re.sub(r"<w:del\b[^>/]*>.*?</w:del>", "", table_xml, flags=re.S)
    xml = re.sub(r"<w:(?:ins|del)\b[^>]*/>", "", xml)
    xml = re.sub(r"<w:ins\b[^>]*>", "", xml)
    xml = xml.replace("</w:ins>", "")
    xml = re.sub(r"<w:(?:proofErr|bookmarkStart|bookmarkEnd)\b[^>]*/>", "", xml)
    xml = re.sub(r' w14:(?:paraId|textId)="[^"]*"', "", xml)
    xml = re.sub(r' w:rsid\w*="[^"]*"', "", xml)
    xml = xml.replace("<w:rPr></w:rPr>", "").replace("<w:trPr></w:trPr>", "")
    return xml


def _skeleton_xml(layout: DocxRequirementTable) -> str:
    def row(*cells: str, span: bool = False) -> str:
        cell_properties = (
            '<w:tcPr><w:tcW w:w="9000" w:type="dxa"/><w:gridSpan w:val="2"/>'
            "</w:tcPr>"
            if span
            else '<w:tcPr><w:tcW w:w="4500" w:type="dxa"/></w:tcPr>'
        )
        return (
            "<w:tr>"
            + "".join(
                f"<w:tc>{cell_properties}{cell_}</w:tc>" for cell_ in cells
            )
            + "</w:tr>"
        )

    def paragraph(text: str, style: Optional[str] = None) -> str:
        properties = (
            f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>'
            if style is not None
            else ""
        )
        return (
            f'<w:p>{properties}<w:r><w:t xml:space="preserve">{escape(text)}'
            "</w:t></w:r></w:p>"
        )

    rows = [row(paragraph("UID", layout.id_style), span=True)]
    if layout.title_style is not None:
        rows.append(row(paragraph("Title", layout.title_style), span=True))
    for label_ in layout.meta_rows:
        rows.append(row(paragraph(label_), paragraph("")))
    rows.append(row(paragraph("Statement", layout.text_style), span=True))
    if layout.note_label is not None:
        rows.append(row(paragraph(f"{layout.note_label} :"), span=True))
    borders = "".join(
        f'<w:{side_} w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        for side_ in ("top", "left", "bottom", "right", "insideH", "insideV")
    )
    return (
        '<w:tbl><w:tblPr><w:tblW w:w="9000" w:type="dxa"/>'
        f"<w:tblBorders>{borders}</w:tblBorders></w:tblPr>"
        '<w:tblGrid><w:gridCol w:w="4500"/><w:gridCol w:w="4500"/></w:tblGrid>'
        + "".join(rows)
        + "</w:tbl>"
    )


_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
    'content-types"><Default Extension="rels" ContentType="application/'
    'vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/'
    'vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    "</Types>"
)

_ROOT_RELATIONSHIPS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships"><Relationship Id="rId1" Type="'
    f'{RELATIONSHIPS_NAMESPACE}/officeDocument" Target="word/document.xml"/>'
    "</Relationships>"
)

_DOCUMENT_RELATIONSHIPS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships"><Relationship Id="rId1" Type="'
    f'{RELATIONSHIPS_NAMESPACE}/styles" Target="styles.xml"/></Relationships>'
)


def _styles_xml(profile: DocxProfile) -> str:
    layout = profile.requirement_table
    assert layout is not None
    normal_style = (
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/><w:qFormat/>'
        '<w:pPr><w:spacing w:after="120"/></w:pPr></w:style>'
    )
    styles: List[str] = [normal_style]
    for style_, level_ in profile.heading_styles.items():
        styles.append(
            f'<w:style w:type="paragraph" w:styleId="{style_}">'
            f'<w:name w:val="heading {level_}"/><w:basedOn w:val="Normal"/>'
            '<w:next w:val="Normal"/><w:qFormat/>'
            f'<w:pPr><w:keepNext/><w:spacing w:before="240"/>'
            f'<w:outlineLvl w:val="{level_ - 1}"/></w:pPr>'
            f'<w:rPr><w:b/><w:sz w:val="{max(32 - 4 * level_, 22)}"/></w:rPr>'
            "</w:style>"
        )
    requirement_styles = [
        layout.id_style,
        layout.title_style,
        layout.text_style,
    ]
    for style_ in [
        s_ for s_ in dict.fromkeys(requirement_styles) if s_ is not None
    ]:
        bold = "<w:rPr><w:b/></w:rPr>" if style_ == layout.id_style else ""
        styles.append(
            f'<w:style w:type="paragraph" w:customStyle="1" w:styleId="{style_}">'
            f'<w:name w:val="{style_}"/><w:basedOn w:val="Normal"/>{bold}'
            "</w:style>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{WORD_NAMESPACE}">'
        + "".join(styles)
        + "</w:styles>"
    )
