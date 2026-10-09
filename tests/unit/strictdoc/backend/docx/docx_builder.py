"""
Builds minimal .docx packages for tests. Only what the reader needs.
"""

import zipfile
from typing import List, Optional

WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
AUTHOR_ATTRIBUTES = (
    'w:id="1" w:author="Test Author" w:date="2026-01-01T00:00:00Z"'
)


def run(
    text: str,
    bold: bool = False,
    italic: bool = False,
    font: Optional[str] = None,
) -> str:
    properties = ""
    if bold:
        properties += "<w:b/>"
    if italic:
        properties += "<w:i/>"
    if font is not None:
        properties += f'<w:rFonts w:ascii="{font}" w:hAnsi="{font}"/>'
    properties_xml = f"<w:rPr>{properties}</w:rPr>" if properties else ""
    return f'<w:r>{properties_xml}<w:t xml:space="preserve">{text}</w:t></w:r>'


def inserted(runs_xml: str) -> str:
    return f"<w:ins {AUTHOR_ATTRIBUTES}>{runs_xml}</w:ins>"


def deleted(text: str) -> str:
    return (
        f"<w:del {AUTHOR_ATTRIBUTES}><w:r>"
        f'<w:delText xml:space="preserve">{text}</w:delText>'
        "</w:r></w:del>"
    )


def paragraph(
    content: str,
    style: Optional[str] = None,
    list_item: bool = False,
    mark_inserted: bool = False,
) -> str:
    """Content is either plain text or already built runs (starting with <)."""
    if not content.startswith("<"):
        content = run(content) if len(content) > 0 else ""
    properties = ""
    if style is not None:
        properties += f'<w:pStyle w:val="{style}"/>'
    if list_item:
        properties += (
            '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>'
        )
    if mark_inserted:
        properties += f"<w:rPr><w:ins {AUTHOR_ATTRIBUTES}/></w:rPr>"
    properties_xml = f"<w:pPr>{properties}</w:pPr>" if properties else ""
    return f"<w:p>{properties_xml}{content}</w:p>"


def cell(*paragraphs: str) -> str:
    return "<w:tc>" + "".join(paragraphs) + "</w:tc>"


def row(*cells: str, row_change: Optional[str] = None) -> str:
    """row_change is 'ins' or 'del' to mark the whole row as tracked."""
    properties = ""
    if row_change is not None:
        properties = f"<w:trPr><w:{row_change} {AUTHOR_ATTRIBUTES}/></w:trPr>"
    return f"<w:tr>{properties}" + "".join(cells) + "</w:tr>"


def table(*rows: str) -> str:
    return "<w:tbl>" + "".join(rows) + "</w:tbl>"


def write_docx(path: str, body_blocks: List[str]) -> None:
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{WORD_NAMESPACE}"><w:body>'
        + "".join(body_blocks)
        + "</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types"><Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    root_relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships"><Relationship Id="rId1" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package_:
        package_.writestr("[Content_Types].xml", content_types)
        package_.writestr("_rels/.rels", root_relationships)
        package_.writestr("word/document.xml", document_xml)
