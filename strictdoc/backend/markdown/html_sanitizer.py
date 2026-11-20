"""
@relation(SDOC-SRS-24, scope=file)
"""

import re
from html import escape
from html.parser import HTMLParser
from typing import Dict, FrozenSet, List, Optional, Tuple

# The raw HTML of a Markdown field is kept, but only what draws a document: an
# allow-list of elements and attributes, as for the SVG files (see
# strictdoc/features/svg/sanitizer.py). What is not allowed is shown as text
# ("&lt;script&gt;"), so that the author sees it, and nothing runs.

ALLOWED_ELEMENTS: FrozenSet[str] = frozenset(
    {
        "a", "abbr", "aside", "b", "bdi", "bdo", "blockquote", "br",
        "caption", "cite", "code", "col", "colgroup", "dd", "del",
        "details", "dfn", "div", "dl", "dt", "em", "figcaption", "figure",
        "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "ins", "kbd",
        "li", "mark", "ol", "p", "pre", "q", "s", "samp", "small", "span",
        "strong", "sub", "summary", "sup", "table", "tbody", "td", "tfoot",
        "th", "thead", "time", "tr", "u", "ul", "var", "wbr",
    }
)  # fmt: skip

_GLOBAL_ATTRIBUTES: FrozenSet[str] = frozenset(
    {
        "class", "id", "title", "lang", "dir", "role", "style",
        "aria-label", "aria-labelledby", "aria-describedby", "aria-hidden",
    }
)  # fmt: skip

_ELEMENT_ATTRIBUTES: Dict[str, FrozenSet[str]] = {
    "a": frozenset({"href"}),
    "img": frozenset({"src", "alt", "width", "height"}),
    "blockquote": frozenset({"cite"}),
    "q": frozenset({"cite"}),
    "time": frozenset({"datetime"}),
    "details": frozenset({"open"}),
    "ol": frozenset({"start", "type", "reversed"}),
    "li": frozenset({"value"}),
    "col": frozenset({"span", "width"}),
    "colgroup": frozenset({"span", "width"}),
    "table": frozenset({"align", "bgcolor", "width", "border"}),
    "tr": frozenset({"align", "bgcolor", "valign"}),
    "td": frozenset(
        {"colspan", "rowspan", "align", "bgcolor", "valign", "width"}
    ),
    "th": frozenset(
        {"colspan", "rowspan", "align", "bgcolor", "valign", "width", "scope"}
    ),
    "p": frozenset({"align"}),
    "div": frozenset({"align"}),
}

_URL_ATTRIBUTES: FrozenSet[str] = frozenset({"href", "src", "cite"})
_URL_SCHEMES: FrozenSet[str] = frozenset({"http", "https", "mailto", "tel"})
_DATA_IMAGE = re.compile(
    r"^data:image/(png|jpe?g|gif|webp|bmp);base64,[A-Za-z0-9+/=\s]*$",
    re.IGNORECASE,
)
_SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x20\x7f-\x9f]")

_STYLE_PROPERTIES: FrozenSet[str] = frozenset(
    {
        "text-align", "background-color", "color", "width", "max-width",
        "height", "margin", "margin-left", "margin-right", "margin-top",
        "margin-bottom", "font-weight", "font-style", "text-decoration",
        "vertical-align",
    }
)  # fmt: skip
_STYLE_VALUE = re.compile(r"^[A-Za-z0-9\s#%.,()+\-/]*$")


_KNOWN_TAG = re.compile(
    r"</?(?:" + "|".join(sorted(ALLOWED_ELEMENTS)) + r")(?:\s[^<>]*)?/?>",
    re.IGNORECASE,
)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def strip_html_tags(text: str) -> str:
    """
    The text of a Markdown field without the tags of the allowed elements and
    without the HTML comments, for the search index and for a prompt. Text
    that looks like a tag but is not one (``<UID>``) stays.
    """
    return _KNOWN_TAG.sub("", _COMMENT.sub("", text))


def sanitize_html_fragment(html: str) -> str:
    """
    The HTML of a Markdown block or span, with only the allowed elements and
    attributes. A tag is written again from the attributes that were read, so
    that what the browser sees is what was checked here.
    """
    sanitizer = _Sanitizer()
    sanitizer.feed(html)
    sanitizer.close()
    return "".join(sanitizer.output)


def _is_safe_url(attribute_name: str, value: str) -> bool:
    compact = _CONTROL_CHARACTERS.sub("", value)
    scheme_match = _SCHEME.match(compact)
    if scheme_match is None:
        return True
    scheme = scheme_match.group(1).lower()
    if scheme in _URL_SCHEMES:
        return True
    return (
        attribute_name == "src"
        and scheme == "data"
        and _DATA_IMAGE.match(compact) is not None
    )


def _safe_style(value: str) -> Optional[str]:
    declarations: List[str] = []
    for declaration in value.split(";"):
        if declaration.strip() == "":
            continue
        name, separator, property_value = declaration.partition(":")
        name = name.strip().lower()
        property_value = property_value.strip()
        if (
            separator == ""
            or name not in _STYLE_PROPERTIES
            or _STYLE_VALUE.match(property_value) is None
            or "url(" in property_value.lower()
            or "expression" in property_value.lower()
        ):
            continue
        declarations.append(f"{name}: {property_value}")
    if len(declarations) == 0:
        return None
    return "; ".join(declarations)


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.output: List[str] = []

    def handle_starttag(
        self, tag: str, attrs: List[Tuple[str, Optional[str]]]
    ) -> None:
        self.output.append(self._start_tag(tag, attrs, closing=""))

    def handle_startendtag(
        self, tag: str, attrs: List[Tuple[str, Optional[str]]]
    ) -> None:
        original = self.get_starttag_text() or ""
        closing = " /" if original.endswith(" />") else "/"
        self.output.append(self._start_tag(tag, attrs, closing=closing))

    def handle_endtag(self, tag: str) -> None:
        if tag in ALLOWED_ELEMENTS:
            self.output.append(f"</{tag}>")
        else:
            self.output.append(escape(f"</{tag}>"))

    def handle_data(self, data: str) -> None:
        self.output.append(data.replace("<", "&lt;"))

    def handle_entityref(self, name: str) -> None:
        self.output.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.output.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.output.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self.output.append(escape(f"<!{decl}>"))

    def handle_pi(self, data: str) -> None:
        self.output.append(escape(f"<?{data}>"))

    def unknown_decl(self, data: str) -> None:
        self.output.append(escape(f"<![{data}]>"))

    def _start_tag(
        self,
        tag: str,
        attrs: List[Tuple[str, Optional[str]]],
        closing: str,
    ) -> str:
        original = self.get_starttag_text() or f"<{tag}>"
        if tag not in ALLOWED_ELEMENTS:
            return escape(original)
        allowed = _GLOBAL_ATTRIBUTES | _ELEMENT_ATTRIBUTES.get(tag, frozenset())
        kept: List[str] = []
        for name, value in attrs:
            if name not in allowed:
                continue
            if value is None:
                kept.append(name)
                continue
            if name in _URL_ATTRIBUTES and not _is_safe_url(name, value):
                continue
            written = value
            if name == "style":
                safe_style = _safe_style(value)
                if safe_style is None:
                    continue
                written = safe_style
            kept.append(f'{name}="{escape(written, quote=True)}"')
        return f"<{tag}{''.join(' ' + item for item in kept)}{closing}>"
