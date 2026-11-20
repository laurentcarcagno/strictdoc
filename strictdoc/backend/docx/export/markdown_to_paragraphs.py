"""
Turns the Markdown text of an SDoc node into Word paragraphs and runs.

It supports paragraphs, headings (a bold paragraph), bullet and numbered lists
(the marker is written as text, like the RST path does), **bold**, *italic*,
`monospace`, code blocks (one monospace paragraph per line), pipe tables, links
(the text and the address) and images (written as "[image: name]"). Raw HTML is
ignored, except <br>, which is a line break; <sup> and <sub>, which are
superscript and subscript runs; the admonitions (a div of the class
sdoc-admonition), whose paragraphs carry the kind "note" or "warning"; and the
definition lists (the term is bold). The text of any other HTML block is kept
without its tags, and the comments are dropped.
"""

import html
import os
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import List, Optional, Tuple, Union
from urllib.parse import unquote, urlparse

from markdown_it import MarkdownIt
from markdown_it.token import Token

from strictdoc.backend.docx.export.docx_images import load_image
from strictdoc.backend.docx.export.paragraph_model import (
    ExportImage,
    ExportParagraph,
    ExportRun,
)

_PARSER = MarkdownIt("default", {"html": True})
_LINE_BREAK_HTML = re.compile(r"<br\s*/?>", re.IGNORECASE)
# A paragraph that the Markdown editor aligns is an HTML paragraph.
_HTML_PARAGRAPH = re.compile(
    r"<p(?:\s[^>]*)?>(.*)</p>", re.IGNORECASE | re.DOTALL
)
_EMPHASIS_HTML = re.compile(r"<(/?)(strong|b|em|i)>", re.IGNORECASE)
_VERTICAL_HTML = re.compile(r"<(/?)(sup|sub)>", re.IGNORECASE)
_ADMONITION_OPEN = re.compile(
    r'<div\b[^>]*\bclass="([^"]*\bsdoc-admonition\b[^"]*)"[^>]*>',
    re.IGNORECASE,
)
_ADMONITION_TITLE = re.compile(
    r'<p\b[^>]*\bclass="[^"]*\bsdoc-admonition-title\b[^"]*"[^>]*>'
    r"(.*?)</p>",
    re.IGNORECASE | re.DOTALL,
)
_CLOSING_DIV = re.compile(r"</div>", re.IGNORECASE)
_WARNING_KINDS = ("attention", "caution", "danger", "error", "warning")
_IMAGE_HTML = re.compile(r"<img\s[^>]*>", re.IGNORECASE)
_HTML_ATTRIBUTE = re.compile(r'([\w-]+)="([^"]*)"')


@dataclass
class ExportTable:
    """A Markdown table; every cell is a plain text."""

    rows: List[List[str]]


ExportBlock = Union[ExportParagraph, ExportTable]


def markdown_to_blocks(markdown: str, base_dir: str = "") -> List[ExportBlock]:
    """base_dir is where the relative paths of the images start."""
    tokens = _PARSER.parse(markdown)
    blocks: List[ExportBlock] = []
    lists: List[List[object]] = []  # [ordered, next number]
    prefix: Optional[str] = None
    admonition: Optional[str] = None
    index = 0
    while index < len(tokens):
        token = tokens[index]
        kind = token.type
        blocks_before = len(blocks)
        if kind in ("bullet_list_open", "ordered_list_open"):
            start = token.attrGet("start")
            lists.append([kind == "ordered_list_open", int(start or 1)])
        elif kind in ("bullet_list_close", "ordered_list_close"):
            lists.pop()
        elif kind == "list_item_open":
            ordered, number = lists[-1]
            marker = f"{number}. " if ordered else "- "
            if ordered:
                lists[-1][1] = int(number) + 1  # type: ignore[call-overload]
            prefix = "  " * (len(lists) - 1) + marker
        elif kind == "paragraph_open":
            runs = _inline_runs(
                tokens[index + 1].children or [], base_dir=base_dir
            )
            if prefix is not None:
                runs.insert(0, ExportRun(prefix))
                prefix = None
            blocks.append(ExportParagraph(runs))
            index += 2
        elif kind == "heading_open":
            runs = _inline_runs(
                tokens[index + 1].children or [], bold=True, base_dir=base_dir
            )
            blocks.append(ExportParagraph(runs))
            index += 2
        elif kind in ("fence", "code_block"):
            for line_ in token.content.rstrip("\n").split("\n"):
                blocks.append(
                    ExportParagraph([ExportRun(line_, monospace=True)])
                )
        elif kind == "table_open":
            table, index = _table(tokens, index)
            blocks.append(table)
        elif kind == "html_block":
            text = token.content.strip()
            opening = _admonition_kind(text)
            if opening is not None:
                admonition = opening
                title = _ADMONITION_TITLE.search(text)
                if title is not None:
                    title_tokens = _PARSER.parseInline(title.group(1))
                    blocks.append(
                        ExportParagraph(
                            _inline_runs(
                                title_tokens[0].children or [],
                                bold=True,
                                base_dir=base_dir,
                            )
                        )
                    )
            elif (
                admonition is not None
                and _CLOSING_DIV.fullmatch(text) is not None
            ):
                admonition = None
            else:
                blocks.extend(_html_block_paragraphs(text, base_dir))
        if admonition is not None:
            for block_ in blocks[blocks_before:]:
                if isinstance(block_, ExportParagraph):
                    block_.admonition = admonition
        index += 1
    return blocks


def _admonition_kind(html_text: str) -> Optional[str]:
    """The kind ("note" or "warning") of an admonition that this HTML opens."""
    match = _ADMONITION_OPEN.match(html_text)
    if match is None:
        return None
    classes = match.group(1).split()
    if any(f"sdoc-{kind_}" in classes for kind_ in _WARNING_KINDS):
        return "warning"
    return "note"


def _html_block_paragraphs(text: str, base_dir: str) -> List[ExportParagraph]:
    if len(text) == 0 or _LINE_BREAK_HTML.fullmatch(text) is not None:
        return []
    html_paragraph = _HTML_PARAGRAPH.fullmatch(text)
    if html_paragraph is not None:
        # The text of the paragraph, without its tags. This export has no
        # alignment.
        inline_tokens = _PARSER.parseInline(html_paragraph.group(1))
        return [
            ExportParagraph(
                _inline_runs(inline_tokens[0].children or [], base_dir=base_dir)
            )
        ]
    if re.match(r"<dl\b", text, re.IGNORECASE) is not None:
        parser = _DefinitionListParser()
        parser.feed(text)
        parser.close()
        return [
            ExportParagraph([ExportRun(text_, bold=is_term_)])
            for is_term_, text_ in parser.entries
        ]
    text_parser = _TextParser()
    text_parser.feed(text)
    text_parser.close()
    return [
        ExportParagraph([ExportRun(line_)]) for line_ in text_parser.lines()
    ]


class _TextParser(HTMLParser):
    """The text of an HTML block, one line per block element."""

    _BREAKING = frozenset(
        {
            "p", "div", "li", "dt", "dd", "tr", "br", "details", "summary",
            "aside", "figure", "figcaption", "blockquote", "table", "ul", "ol",
            "dl", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "hr",
        }
    )  # fmt: skip

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []

    def handle_starttag(self, tag: str, _attrs: object) -> None:
        if tag in self._BREAKING:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BREAKING:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def lines(self) -> List[str]:
        lines = (
            " ".join(line_.split()) for line_ in "".join(self.parts).split("\n")
        )
        return [line_ for line_ in lines if len(line_) > 0]


class _DefinitionListParser(HTMLParser):
    """The terms (True) and the definitions (False) of a <dl>."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: List[Tuple[bool, str]] = []
        self._current: Optional[bool] = None
        self._text: List[str] = []

    def handle_starttag(self, tag: str, _attrs: object) -> None:
        if tag in ("dt", "dd"):
            self._flush()
            self._current = tag == "dt"

    def handle_endtag(self, tag: str) -> None:
        if tag in ("dt", "dd", "dl"):
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._text.append(data)

    def _flush(self) -> None:
        text = " ".join("".join(self._text).split())
        if self._current is not None and len(text) > 0:
            self.entries.append((self._current, text))
        self._text = []
        self._current = None


def markdown_to_paragraphs(
    markdown: str, base_dir: str = ""
) -> List[ExportParagraph]:
    """The blocks as paragraphs: a table becomes one paragraph per row."""
    paragraphs: List[ExportParagraph] = []
    for block_ in markdown_to_blocks(markdown, base_dir):
        if isinstance(block_, ExportTable):
            for row_ in block_.rows:
                paragraphs.append(
                    ExportParagraph([ExportRun(" | ".join(row_))])
                )
        else:
            paragraphs.append(block_)
    return paragraphs


def _table(tokens: List[Token], index: int) -> "tuple[ExportTable, int]":
    rows: List[List[str]] = []
    while tokens[index].type != "table_close":
        token = tokens[index]
        if token.type == "tr_open":
            rows.append([])
        elif token.type == "inline":
            runs = _inline_runs(token.children or [])
            rows[-1].append("".join(run_.text for run_ in runs))
        index += 1
    return ExportTable(rows), index


def _inline_runs(
    children: List[Token], bold: bool = False, base_dir: str = ""
) -> List[ExportRun]:
    runs: List[ExportRun] = []
    bold_depth = 0
    italic_depth = 0
    links: List[str] = []
    link_text_start: List[int] = []
    vertical: List[str] = []

    def add(text: str, monospace: bool = False) -> None:
        if len(text) == 0:
            return
        run = ExportRun(
            text,
            bold=bold or bold_depth > 0,
            italic=italic_depth > 0,
            monospace=monospace,
            vertical=vertical[-1] if len(vertical) > 0 else None,
        )
        if len(runs) > 0 and _same_format(runs[-1], run):
            runs[-1].text += text
        else:
            runs.append(run)

    def add_image(source: str, alt: str) -> None:
        name = os.path.basename(source) or alt
        placeholder = f"[image: {name}]"
        image = _load(source, base_dir, alt)
        if image is None:
            add(placeholder)
        else:
            # Not merged with the text around it.
            runs.append(ExportRun(placeholder, image=image))

    for child_ in children:
        kind = child_.type
        if kind == "strong_open":
            bold_depth += 1
        elif kind == "strong_close":
            bold_depth -= 1
        elif kind == "em_open":
            italic_depth += 1
        elif kind == "em_close":
            italic_depth -= 1
        elif kind == "text":
            add(child_.content)
        elif kind == "code_inline":
            add(child_.content, monospace=True)
        elif kind == "softbreak":
            add(" ")
        elif kind == "hardbreak":
            add("\n")
        elif kind == "html_inline":
            tag = child_.content.strip()
            emphasis = _EMPHASIS_HTML.fullmatch(tag)
            vertical_tag = _VERTICAL_HTML.fullmatch(tag)
            if _LINE_BREAK_HTML.fullmatch(tag) is not None:
                add("\n")
            elif vertical_tag is not None:
                if vertical_tag.group(1) == "/":
                    if len(vertical) > 0:
                        vertical.pop()
                elif vertical_tag.group(2).lower() == "sup":
                    vertical.append("superscript")
                else:
                    vertical.append("subscript")
            elif emphasis is not None:
                step = -1 if emphasis.group(1) == "/" else 1
                if emphasis.group(2).lower() in ("strong", "b"):
                    bold_depth += step
                else:
                    italic_depth += step
            elif _IMAGE_HTML.fullmatch(tag) is not None:
                # An image that the Markdown editor aligns is an HTML image.
                attributes = {
                    name_: html.unescape(value_)
                    for name_, value_ in _HTML_ATTRIBUTE.findall(tag)
                }
                add_image(attributes.get("src", ""), attributes.get("alt", ""))
        elif kind == "link_open":
            links.append(str(child_.attrGet("href") or ""))
            link_text_start.append(len(runs))
        elif kind == "link_close":
            address = links.pop()
            start = link_text_start.pop()
            shown = "".join(run_.text for run_ in runs[start:])
            if (
                len(address) > 0
                and not address.startswith("#")
                and shown != address
            ):
                add(f" ({address})")
        elif kind == "image":
            add_image(str(child_.attrGet("src") or ""), child_.content)
    return runs


def _same_format(first: ExportRun, second: ExportRun) -> bool:
    return (first.bold, first.italic, first.monospace, first.vertical) == (
        second.bold,
        second.italic,
        second.monospace,
        second.vertical,
    )


def _load(source: str, base_dir: str, alt: str) -> "Optional[ExportImage]":
    """The image file of a relative path, or None (the text stands in)."""
    if len(source) == 0 or urlparse(source).scheme not in ("", "file"):
        return None
    path = unquote(urlparse(source).path)
    if not os.path.isabs(path):
        path = os.path.join(base_dir, path)
    return load_image(os.path.normpath(path), alt)
