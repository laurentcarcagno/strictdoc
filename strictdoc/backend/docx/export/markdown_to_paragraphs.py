"""
Turns the Markdown text of an SDoc node into Word paragraphs and runs.

It supports paragraphs, headings (a bold paragraph), bullet and numbered lists
(the marker is written as text, like the RST path does), **bold**, *italic*,
`monospace`, code blocks (one monospace paragraph per line), pipe tables, links
(the text and the address) and images (written as "[image: name]"). Raw HTML is
ignored, except <br>, which is a line break.
"""

import os
import re
from dataclasses import dataclass
from typing import List, Optional, Union
from urllib.parse import unquote, urlparse

from markdown_it import MarkdownIt
from markdown_it.token import Token

from strictdoc.backend.docx.export.docx_images import load_image
from strictdoc.backend.docx.export.rst_to_paragraphs import (
    ExportImage,
    ExportParagraph,
    ExportRun,
)

_PARSER = MarkdownIt("default", {"html": True})
_LINE_BREAK_HTML = re.compile(r"<br\s*/?>", re.IGNORECASE)


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
    index = 0
    while index < len(tokens):
        token = tokens[index]
        kind = token.type
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
            if len(text) > 0 and _LINE_BREAK_HTML.fullmatch(text) is None:
                blocks.append(ExportParagraph([ExportRun(text)]))
        index += 1
    return blocks


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

    def add(text: str, monospace: bool = False) -> None:
        if len(text) == 0:
            return
        run = ExportRun(
            text,
            bold=bold or bold_depth > 0,
            italic=italic_depth > 0,
            monospace=monospace,
        )
        if len(runs) > 0 and _same_format(runs[-1], run):
            runs[-1].text += text
        else:
            runs.append(run)

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
            if _LINE_BREAK_HTML.fullmatch(child_.content.strip()) is not None:
                add("\n")
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
            source = str(child_.attrGet("src") or "")
            name = os.path.basename(source) or child_.content
            placeholder = f"[image: {name}]"
            image = _load(source, base_dir, child_.content)
            if image is None:
                add(placeholder)
            else:
                # Not merged with the text around it.
                runs.append(ExportRun(placeholder, image=image))
    return runs


def _same_format(first: ExportRun, second: ExportRun) -> bool:
    return (first.bold, first.italic, first.monospace) == (
        second.bold,
        second.italic,
        second.monospace,
    )


def _load(source: str, base_dir: str, alt: str) -> "Optional[ExportImage]":
    """The image file of a relative path, or None (the text stands in)."""
    if len(source) == 0 or urlparse(source).scheme not in ("", "file"):
        return None
    path = unquote(urlparse(source).path)
    if not os.path.isabs(path):
        path = os.path.join(base_dir, path)
    return load_image(os.path.normpath(path), alt)
