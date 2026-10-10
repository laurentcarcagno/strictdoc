"""
Comments of the SDoc model as native Word comments.

A Word comment is a part of the package (word/comments.xml) and three marks in
the text: where its range starts, where it ends, and a reference. Word shows
it in the review pane and in the margin, with author, date and initials.

The marks are written with placeholders (the numeric identifier of a Word
comment must be unique in the document), and embed_comments() fills them in
and adds the part, its relationship and its content type, the same way
docx_images.embed_images() does for pictures.

A resolved comment is marked in word/commentsExtended.xml (the "done" flag
that Word 2013 and later use).
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple
from xml.sax.saxutils import quoteattr

from strictdoc.backend.docx.export.docx_xml import paragraph_xml
from strictdoc.backend.docx.export.text_to_paragraphs import text_to_paragraphs
from strictdoc.features.comments.model import initials

COMMENTS_PART = "word/comments.xml"
EXTENDED_PART = "word/commentsExtended.xml"
_RELATIONSHIPS_PART = "word/_rels/document.xml.rels"
_CONTENT_TYPES_PART = "[Content_Types].xml"

_COMMENTS_RELATIONSHIP = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
_EXTENDED_RELATIONSHIP = (
    "http://schemas.microsoft.com/office/2011/relationships/commentsExtended"
)
_COMMENTS_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
_EXTENDED_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtended+xml"
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
_W15 = "http://schemas.microsoft.com/office/word/2012/wordml"

_PLACEHOLDER = "@@SDOC_COMMENT:{}@@"
_PLACEHOLDER_PATTERN = re.compile(r"@@SDOC_COMMENT:([0-9A-Za-z_-]+)@@")


@dataclass
class ExportComment:
    """One comment of the model, ready for Word."""

    # The identifier in the SDoc header, or a stable one made for a legacy one.
    key: str
    author: str
    date: str
    body: str
    resolved: bool = False
    markup: str = "RST"
    base_dir: str = ""

    @property
    def fingerprint(self) -> Tuple[str, str, str]:
        """What identifies a comment when it goes to Word and comes back."""
        return comment_fingerprint(
            self.author,
            self.date,
            comment_plain_text(self.body, self.markup),
        )


def comment_plain_text(body: str, markup: str) -> str:
    """The text of a comment as Word holds it: the paragraphs, no markup."""
    return " ".join(
        "".join(run_.text for run_ in paragraph_.runs)
        for paragraph_ in text_to_paragraphs(body, markup)
    )


def comment_fingerprint(
    author: str, date: str, text: str
) -> Tuple[str, str, str]:
    """(author, date to the minute, SHA-1 of the text without spaces)."""
    plain = re.sub(r"\s+", " ", text).strip()
    return (
        author.strip().lower(),
        date[:16],
        hashlib.sha1(plain.encode("utf8")).hexdigest(),
    )


def anchor_xml(comments: List[ExportComment]) -> Tuple[str, str]:
    """
    The marks that start and end the ranges of the comments of a requirement:
    (xml to put at the start of a paragraph, xml for its end).
    """
    starts = "".join(
        f'<w:commentRangeStart w:id="{_PLACEHOLDER.format(comment_.key)}"/>'
        for comment_ in comments
    )
    ends = "".join(
        f'<w:commentRangeEnd w:id="{_PLACEHOLDER.format(comment_.key)}"/>'
        f'<w:r><w:commentReference w:id="{_PLACEHOLDER.format(comment_.key)}"/></w:r>'
        for comment_ in comments
    )
    return starts, ends


def anchor_first_paragraph(
    table_xml: str, comments: List[ExportComment]
) -> str:
    """
    Puts the ranges of the comments around the content of the first paragraph
    of a requirement table (the paragraph of its identifier).
    """
    if len(comments) == 0:
        return table_xml
    starts, ends = anchor_xml(comments)
    match = re.search(r"<w:p(?:\s[^>]*)?>.*?</w:p>", table_xml, re.S)
    if match is None:
        return table_xml
    paragraph = match.group(0)
    properties = re.match(
        r"(<w:p(?:\s[^>]*)?>)(<w:pPr>.*?</w:pPr>)?", paragraph, re.S
    )
    assert properties is not None
    head = properties.group(0)
    anchored = (
        head + starts + paragraph[len(head) : -len("</w:p>")] + ends + "</w:p>"
    )
    return table_xml[: match.start()] + anchored + table_xml[match.end() :]


def _paragraph_id(key: str) -> str:
    """An 8 hex digit identifier for w14:paraId, below 0x80000000."""
    digest = hashlib.sha1(key.encode("utf8")).hexdigest()[:8]
    return f"{int(digest, 16) % 0x7FFFFFFF:08X}"


def _comment_xml(comment: ExportComment, word_id: int) -> str:
    paragraphs = text_to_paragraphs(
        comment.body, comment.markup, comment.base_dir
    )
    rendered = [paragraph_xml(paragraph_) for paragraph_ in paragraphs]
    if len(rendered) == 0:
        rendered = ["<w:p/>"]
    # Word starts the first paragraph of a comment with its annotation mark,
    # and the last paragraph carries the identifier that commentsExtended uses.
    rendered[0] = (
        rendered[0].replace("<w:p>", "<w:p><w:r><w:annotationRef/></w:r>", 1)
        if rendered[0].startswith("<w:p>")
        else rendered[0]
    )
    rendered[-1] = (
        rendered[-1].replace(
            "<w:p>", f'<w:p w14:paraId="{_paragraph_id(comment.key)}">', 1
        )
        if rendered[-1].startswith("<w:p>")
        else rendered[-1]
    )
    date = f" w:date={quoteattr(comment.date)}" if comment.date else ""
    return (
        f'<w:comment w:id="{word_id}" w:author={quoteattr(comment.author or "Unknown")}'
        f"{date} w:initials={quoteattr(initials(comment.author))}>"
        + "".join(rendered)
        + "</w:comment>"
    )


def _comments_document(inner: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:comments xmlns:w="{_W}" xmlns:w14="{_W14}">{inner}</w:comments>'
    )


def embed_comments(
    package: Dict[str, bytes], comments: List[ExportComment]
) -> int:
    """
    Writes the comments into the package and fills in the placeholders of
    word/document.xml. A comment that the file already holds (same author,
    date to the minute and text) is not added again. Returns the number of
    comments added.
    """
    document_xml = package["word/document.xml"].decode("utf8")
    used_keys = [key_ for key_ in _PLACEHOLDER_PATTERN.findall(document_xml)]
    by_key = {comment_.key: comment_ for comment_ in comments}
    keys: List[str] = []
    for key_ in used_keys:
        if key_ in by_key and key_ not in keys:
            keys.append(key_)
    if len(keys) == 0:
        return 0

    existing_xml = (
        package[COMMENTS_PART].decode("utf8")
        if COMMENTS_PART in package
        else ""
    )
    taken = [
        int(id_)
        for id_ in re.findall(r'<w:comment\b[^>]*\sw:id="(\d+)"', existing_xml)
    ]
    next_id = max(taken, default=-1) + 1

    new_comments: List[str] = []
    ids: Dict[str, int] = {}
    for key_ in keys:
        ids[key_] = next_id
        new_comments.append(_comment_xml(by_key[key_], next_id))
        next_id += 1
    for key_, word_id in ids.items():
        document_xml = document_xml.replace(
            _PLACEHOLDER.format(key_), str(word_id)
        )
    package["word/document.xml"] = document_xml.encode("utf8")

    if existing_xml:
        package[COMMENTS_PART] = existing_xml.replace(
            "</w:comments>", "".join(new_comments) + "</w:comments>", 1
        ).encode("utf8")
    else:
        package[COMMENTS_PART] = _comments_document(
            "".join(new_comments)
        ).encode("utf8")
        _add_relationship(
            package, "rIdSdocComments", _COMMENTS_RELATIONSHIP, "comments.xml"
        )
        _add_content_type(package, "/word/comments.xml", _COMMENTS_CONTENT_TYPE)

    resolved = [key_ for key_ in keys if by_key[key_].resolved]
    if len(resolved) > 0 or EXTENDED_PART in package:
        _embed_extended(package, [by_key[key_] for key_ in keys])
    return len(keys)


def _embed_extended(
    package: Dict[str, bytes], added: List[ExportComment]
) -> None:
    lines = "".join(
        f'<w15:commentEx w15:paraId="{_paragraph_id(comment_.key)}" '
        f'w15:done="{1 if comment_.resolved else 0}"/>'
        for comment_ in added
    )
    if EXTENDED_PART in package:
        package[EXTENDED_PART] = (
            package[EXTENDED_PART]
            .decode("utf8")
            .replace("</w15:commentsEx>", lines + "</w15:commentsEx>", 1)
            .encode("utf8")
        )
        return
    package[EXTENDED_PART] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w15:commentsEx xmlns:w15="{_W15}">{lines}</w15:commentsEx>'
    ).encode()
    _add_relationship(
        package,
        "rIdSdocCommentsEx",
        _EXTENDED_RELATIONSHIP,
        "commentsExtended.xml",
    )
    _add_content_type(
        package, "/word/commentsExtended.xml", _EXTENDED_CONTENT_TYPE
    )


def _add_relationship(
    package: Dict[str, bytes], relationship_id: str, kind: str, target: str
) -> None:
    xml = package[_RELATIONSHIPS_PART].decode("utf8")
    if f'Id="{relationship_id}"' in xml:
        return
    package[_RELATIONSHIPS_PART] = xml.replace(
        "</Relationships>",
        f'<Relationship Id="{relationship_id}" Type="{kind}" Target="{target}"/></Relationships>',
        1,
    ).encode("utf8")


def _add_content_type(
    package: Dict[str, bytes], part_name: str, content_type: str
) -> None:
    xml = package[_CONTENT_TYPES_PART].decode("utf8")
    if f'PartName="{part_name}"' in xml:
        return
    package[_CONTENT_TYPES_PART] = xml.replace(
        "</Types>",
        f'<Override PartName="{part_name}" ContentType="{content_type}"/></Types>',
        1,
    ).encode("utf8")


def new_comment_keys_exclude(
    comments: List[ExportComment], existing: List[Tuple[str, str, str]]
) -> List[ExportComment]:
    """The comments whose fingerprint is not among the existing ones."""
    known = set(existing)
    return [
        comment_ for comment_ in comments if comment_.fingerprint not in known
    ]
