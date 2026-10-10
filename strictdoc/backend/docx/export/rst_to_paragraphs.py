"""
Turns the RST text of an SDoc statement into Word paragraphs and runs.

It supports what the importer writes: paragraphs, bullet lists, **bold**,
*italic*, ``monospace`` and backslash escapes. Other RST is kept as text.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

_BULLET_PATTERN = re.compile(r"^- ")


@dataclass
class ExportImage:
    """An image file that is embedded in the Word document."""

    # A hash of the content: two uses of the same file share one media part.
    token: str
    name: str
    alt: str
    data: bytes
    extension: str
    content_type: str
    width_emu: int
    height_emu: int


@dataclass
class ExportRun:
    # For an image run, the text that stands for the image ("[image: name]"):
    # it is what the Word text reads back as.
    text: str
    bold: bool = False
    italic: bool = False
    monospace: bool = False
    image: Optional[ExportImage] = None


@dataclass
class ExportParagraph:
    runs: List[ExportRun] = field(default_factory=list)


def rst_to_paragraphs(rst: str) -> List[ExportParagraph]:
    paragraphs: List[ExportParagraph] = []
    for block_ in re.split(r"\n\s*\n", rst.strip("\n")):
        lines = [line_.rstrip() for line_ in block_.split("\n")]
        if len(block_.strip()) == 0:
            continue
        if _BULLET_PATTERN.match(lines[0]) is not None:
            for item_ in _bullet_items(lines):
                paragraphs.append(ExportParagraph(_inline_runs(item_)))
        else:
            text = " ".join(line_.strip() for line_ in lines)
            paragraphs.append(ExportParagraph(_inline_runs(text)))
    return paragraphs


def _bullet_items(lines: List[str]) -> List[str]:
    items: List[str] = []
    for line_ in lines:
        if _BULLET_PATTERN.match(line_) is not None:
            items.append(line_)
        elif len(items) > 0:
            items[-1] += " " + line_.strip()
    return items


def _inline_runs(text: str) -> List[ExportRun]:
    runs: List[ExportRun] = []
    buffer: List[str] = []

    def flush_plain() -> None:
        if len(buffer) > 0:
            runs.append(ExportRun("".join(buffer)))
            buffer.clear()

    index = 0
    while index < len(text):
        character = text[index]
        if character == "\\" and index + 1 < len(text):
            buffer.append(text[index + 1])
            index += 2
            continue
        marker = _marker_at(text, index)
        if marker is not None:
            end = text.find(marker, index + len(marker))
            inner = text[index + len(marker) : end] if end != -1 else ""
            if end != -1 and len(inner) > 0 and not inner[0].isspace():
                flush_plain()
                runs.append(
                    ExportRun(
                        _unescape(inner) if marker != "``" else inner,
                        bold=marker == "**",
                        italic=marker == "*",
                        monospace=marker == "``",
                    )
                )
                index = end + len(marker)
                continue
        buffer.append(character)
        index += 1
    flush_plain()
    return runs


def _marker_at(text: str, index: int) -> Optional[str]:
    for marker_ in ("``", "**", "*"):
        if text.startswith(marker_, index):
            return marker_
    return None


def _unescape(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text)
