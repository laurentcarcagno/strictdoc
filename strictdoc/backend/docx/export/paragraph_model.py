"""
The paragraphs and the runs that the Word export writes.
"""

from dataclasses import dataclass, field
from typing import List, Optional


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
    # For an SVG, its rasterization: the picture for readers that do not show
    # SVG. `data` stays the SVG.
    fallback_png: Optional[bytes] = None


@dataclass
class ExportRun:
    # For an image run, the text that stands for the image ("[image: name]"):
    # it is what the Word text reads back as.
    text: str
    bold: bool = False
    italic: bool = False
    monospace: bool = False
    # "superscript" or "subscript" (<sup> and <sub> of a Markdown field).
    vertical: Optional[str] = None
    image: Optional[ExportImage] = None


@dataclass
class ExportParagraph:
    runs: List[ExportRun] = field(default_factory=list)
    # "note" or "warning" for a paragraph of an admonition (a div with the
    # class sdoc-admonition); the profile names the Word style of each.
    admonition: Optional[str] = None
