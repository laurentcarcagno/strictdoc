"""
Make an SVG file safe: an allow-list of elements and attributes.

SVG is an active format (script, event attributes, references to files and to
remote addresses). The function below parses the file with a parser that is not
given a DTD, keeps only the elements and the attributes that draw something, and
removes every reference that does not point inside the file. A file that cannot
be made safe is rejected with SvgRejected.
"""

import re
from typing import Dict, FrozenSet, List, Optional, Tuple
from xml.etree import ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
XML_NS = "http://www.w3.org/XML/1998/namespace"

MAX_SVG_BYTES = 10 * 1024 * 1024
MAX_SVG_ELEMENTS = 50_000
MAX_SVG_DEPTH = 64

ALLOWED_ELEMENTS: FrozenSet[str] = frozenset(
    {
        "svg", "g", "defs", "symbol", "use", "title", "desc", "path", "rect",
        "circle", "ellipse", "line", "polyline", "polygon", "text", "tspan",
        "textPath", "image", "linearGradient", "radialGradient", "stop",
        "pattern", "clipPath", "mask", "marker", "style", "filter",
        "feGaussianBlur", "feOffset", "feBlend", "feColorMatrix", "feFlood",
        "feMerge", "feMergeNode", "feComposite", "feDropShadow",
    }
)  # fmt: skip

ALLOWED_ATTRIBUTES: FrozenSet[str] = frozenset(
    {
        "id", "class", "style", "transform", "x", "y", "x1", "y1", "x2", "y2",
        "cx", "cy", "r", "rx", "ry", "fx", "fy", "width", "height", "d",
        "points", "viewBox", "preserveAspectRatio", "version", "dx", "dy",
        "rotate", "textLength", "lengthAdjust", "startOffset", "method",
        "spacing", "fill", "fill-opacity", "fill-rule", "stroke",
        "stroke-width", "stroke-opacity", "stroke-linecap", "stroke-linejoin",
        "stroke-miterlimit", "stroke-dasharray", "stroke-dashoffset",
        "opacity", "color", "display", "visibility", "overflow", "clip-path",
        "clip-rule", "mask", "filter", "marker-start", "marker-mid",
        "marker-end", "markerWidth", "markerHeight", "markerUnits", "refX",
        "refY", "orient", "font-family", "font-size", "font-style",
        "font-weight", "font-variant", "font-stretch", "text-anchor",
        "text-decoration", "letter-spacing", "word-spacing",
        "dominant-baseline", "alignment-baseline", "baseline-shift",
        "writing-mode", "direction", "unicode-bidi", "stop-color",
        "stop-opacity", "offset", "gradientUnits", "gradientTransform",
        "spreadMethod", "patternUnits", "patternContentUnits",
        "patternTransform", "clipPathUnits", "maskUnits", "maskContentUnits",
        "filterUnits", "primitiveUnits", "in", "in2", "result", "stdDeviation",
        "mode", "operator", "values", "flood-color", "flood-opacity",
        "k1", "k2", "k3", "k4", "type", "shape-rendering", "text-rendering",
        "image-rendering", "color-interpolation", "color-interpolation-filters",
        "vector-effect", "pointer-events", "href", "xmlns", "mix-blend-mode",
        "isolation", "paint-order",
    }
)  # fmt: skip

# Elements whose href may point to a local #id.
_LOCAL_HREF_ELEMENTS = frozenset(
    {"use", "linearGradient", "radialGradient", "pattern", "textPath"}
)
_DATA_IMAGE = re.compile(
    r"^data:image/(png|jpeg|gif);base64,[A-Za-z0-9+/=\s]*$"
)
_DOCTYPE = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE | re.DOTALL)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_DANGEROUS_VALUE = re.compile(
    r"javascript:|vbscript:|expression\s*\(|behaviou?r\s*:|-moz-binding",
    re.IGNORECASE,
)


class SvgRejected(ValueError):
    pass


def sanitize_svg(data: bytes) -> bytes:
    """The cleaned file as UTF-8 bytes. Raises SvgRejected."""
    if len(data) > MAX_SVG_BYTES:
        raise SvgRejected("The SVG file is too large.")
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    # A DTD is how entity bombs and external entities are written: no DTD at
    # all, whatever the parser would do with it.
    if _DOCTYPE.search(data):
        raise SvgRejected("The SVG file has a DTD or entities.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exception_:
        raise SvgRejected("The SVG file is not UTF-8 text.") from exception_
    if re.search(r"<\?xml[^>]*encoding\s*=\s*['\"](?!utf-8)", text, re.I):
        raise SvgRejected("The SVG file must be encoded in UTF-8.")
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as exception_:
        raise SvgRejected(f"The SVG file is not valid XML: {exception_}") from (
            exception_
        )
    if root.tag != f"{{{SVG_NS}}}svg":
        raise SvgRejected("The file is not an SVG image.")

    counter = [0]
    _clean(root, 0, counter)
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=False)


def _local(tag: str) -> Tuple[str, str]:
    if tag.startswith("{"):
        namespace, _, name = tag[1:].partition("}")
        return namespace, name
    return "", tag


def _clean(element: ET.Element, depth: int, counter: List[int]) -> None:
    counter[0] += 1
    if counter[0] > MAX_SVG_ELEMENTS:
        raise SvgRejected("The SVG file has too many elements.")
    if depth > MAX_SVG_DEPTH:
        raise SvgRejected("The SVG file is nested too deeply.")

    _, name = _local(element.tag)
    _clean_attributes(element, name)

    if name == "style":
        css = _clean_css(element.text or "")
        element.text = css if css is not None else ""
    for child in list(element):
        namespace, child_name = _local(child.tag)
        if namespace != SVG_NS or child_name not in ALLOWED_ELEMENTS:
            element.remove(child)
            continue
        _clean(child, depth + 1, counter)
        # Text and tail of dropped markup stays; comments and processing
        # instructions never reach the tree.


def _clean_attributes(element: ET.Element, element_name: str) -> None:
    kept: Dict[str, str] = {}
    for key, value in element.attrib.items():
        namespace, name = _local(key)
        if namespace == XML_NS and name in ("space", "lang"):
            kept[key] = value
            continue
        if namespace == XLINK_NS and name == "href":
            name = "href"
        elif namespace != "":
            continue
        if name.lower().startswith("on"):
            continue
        if name == "href":
            if _href_allowed(element_name, value):
                kept[key] = value.strip()
            continue
        if name == "style":
            cleaned = _clean_css(value, declarations=True)
            if cleaned:
                kept[key] = cleaned
            continue
        if name not in ALLOWED_ATTRIBUTES:
            continue
        if _DANGEROUS_VALUE.search(value) or not _urls_are_local(value):
            continue
        kept[key] = value
    element.attrib.clear()
    element.attrib.update(kept)


def _href_allowed(element_name: str, value: str) -> bool:
    value = value.strip()
    if element_name == "image":
        return bool(_DATA_IMAGE.match(value))
    if element_name in _LOCAL_HREF_ELEMENTS:
        return value.startswith("#") and len(value) > 1
    return False


def _urls_are_local(value: str) -> bool:
    return all(
        match.group(2).strip().startswith("#") for match in _URL.finditer(value)
    )


def _clean_css(css: str, declarations: bool = False) -> Optional[str]:
    """
    A style value or a style element, reduced to what cannot reach out: no
    at-rule, no escape, no script, only local url() references. Returns None
    when the text is refused as a whole.
    """
    css = _CSS_COMMENT.sub("", css)
    if "@" in css or "\\" in css or _DANGEROUS_VALUE.search(css):
        return None
    if not _urls_are_local(css):
        return None
    if "<" in css:
        return None
    return css.strip() if declarations else css
