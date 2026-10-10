"""
SVG to PNG, for the places that cannot show a vector drawing (the fallback of
the Word picture).

The rasterizer is resvg (Python package resvg-py): a self-contained wheel with
no system library and no network access. It does read a plain file path found
in an image reference, so it is only given a file that sanitize_svg has
cleaned.
"""

import os
import re
from typing import List, Optional, Tuple
from xml.etree import ElementTree as ET

from strictdoc.features.svg.sanitizer import SvgRejected, sanitize_svg

try:
    import resvg_py
except ImportError:  # pragma: no cover - the package is a dependency
    resvg_py = None  # type: ignore[assignment]

# CSS pixels per unit at 96 pixels per inch.
_UNITS = {
    "": 1.0,
    "px": 1.0,
    "pt": 96.0 / 72.0,
    "pc": 16.0,
    "mm": 96.0 / 25.4,
    "cm": 96.0 / 2.54,
    "in": 96.0,
}
_LENGTH = re.compile(
    r"^\s*([0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)\s*([a-z%]*)\s*$"
)
_DEFAULT_SIZE = (300, 150)
_MAX_PIXELS = 8000


def available() -> bool:
    return resvg_py is not None


def svg_display_size(data: bytes) -> Tuple[int, int]:
    """
    The size of the drawing in pixels at 96 per inch, from width and height,
    else from the viewBox, else the default size of a browser.
    """
    root = ET.fromstring(data)
    width = _length(root.get("width"))
    height = _length(root.get("height"))
    view_box = _view_box(root.get("viewBox"))
    if view_box is not None:
        box_width, box_height = view_box
        if width is None and height is None:
            width, height = box_width, box_height
        elif width is None and height is not None:
            width = height * box_width / box_height
        elif height is None and width is not None:
            height = width * box_height / box_width
    if width is None or height is None:
        return _DEFAULT_SIZE
    return max(1, round(width)), max(1, round(height))


def rasterize_svg(data: bytes, width_px: Optional[int] = None) -> bytes:
    """
    A PNG with a transparent background. `data` is cleaned again here: a file
    placed in the assets folder by hand is not trusted. Raises SvgRejected.
    """
    if resvg_py is None:
        raise SvgRejected("No SVG rasterizer is installed.")
    cleaned = sanitize_svg(data)
    own_width, own_height = svg_display_size(cleaned)
    width = min(width_px or own_width, _MAX_PIXELS)
    if own_height * width / max(own_width, 1) > _MAX_PIXELS:
        raise SvgRejected("The SVG drawing is too large to render.")
    font_dirs: List[str] = [
        path_
        for path_ in os.environ.get("STRICTDOC_SVG_FONT_DIRS", "").split(
            os.pathsep
        )
        if path_
    ]
    try:
        return bytes(
            resvg_py.svg_to_bytes(
                svg_string=cleaned.decode("utf-8"),
                width=width,
                font_dirs=font_dirs or None,
                # The generic families are mapped to fonts that the server
                # image installs (fonts-liberation).
                font_family="Liberation Sans",
                sans_serif_family="Liberation Sans",
                serif_family="Liberation Serif",
                monospace_family="Liberation Mono",
            )
        )
    except ValueError as exception_:
        raise SvgRejected(
            f"The SVG drawing cannot be rendered: {exception_}"
        ) from (exception_)


def _length(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    match = _LENGTH.match(value)
    if match is None or match.group(2) == "%":
        return None
    unit = _UNITS.get(match.group(2))
    if unit is None:
        return None
    result = float(match.group(1)) * unit
    return result if result > 0 else None


def _view_box(value: Optional[str]) -> Optional[Tuple[float, float]]:
    if value is None:
        return None
    parts = re.split(r"[\s,]+", value.strip())
    if len(parts) != 4:
        return None
    try:
        width, height = float(parts[2]), float(parts[3])
    except ValueError:
        return None
    return (width, height) if width > 0 and height > 0 else None
