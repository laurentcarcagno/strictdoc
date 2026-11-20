"""
Converts the RST of a StrictDoc field to Markdown.

This is the engine of developer/tools/rst_to_markdown.py. It parses the RST
with docutils and writes the document tree as Markdown. What Markdown cannot
say is written as the HTML elements that the user guide describes (an
admonition is a div of the class sdoc-admonition, a table is a table, a
definition list is a dl). What has no equivalent is dropped, with a warning.

The [LINK: ...] and [ANCHOR: ...] markers of StrictDoc are not RST: they are
replaced by words before the parsing and put back as they were.
"""

import io
import os
import re
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from html import escape as html_escape
from typing import Any, Dict, Iterator, List, Optional, Tuple

from docutils import nodes
from docutils.core import publish_doctree
from docutils.parsers.rst import Directive, directives, roles

from strictdoc.backend.rst.directives.raw_html_role import raw_html_role
from strictdoc.core.image_formats import SUPPORTED_IMAGE_FORMATS

# An anchor title in double quotes may hold a closing bracket.
_MARKER = re.compile(r'\[(?:LINK|ANCHOR): (?:[^\]"\n]|"[^"\n]*")*\]')
_MARKER_WORD = re.compile(r"SDOCMARKER(\d+)END")
_EQUATION_WORD = re.compile(r"SDOCEQUATION([A-Za-z0-9]+)END")

_ADMONITIONS = {
    "note": "Note",
    "hint": "Hint",
    "tip": "Tip",
    "important": "Important",
    "attention": "Attention",
    "caution": "Caution",
    "danger": "Danger",
    "error": "Error",
    "warning": "Warning",
}

# The RST directives that describe a page and not a node: dropped.
_STRUCTURE_TOPICS = {"contents"}

_IMAGE_PREFERENCE = [".svg", ".png"]


@dataclass
class ConversionResult:
    markdown: str
    # What could not be converted faithfully, one message per construct.
    warnings: List[str] = field(default_factory=list)
    # The RST constructs that were met, by name: "paragraph", "table"...
    constructs: Counter = field(default_factory=Counter)  # type: ignore[type-arg]


class _EquationLabelDirective(Directive):  # type: ignore[misc]
    """.. math:: with the options of the Sphinx directive."""

    has_content = True
    optional_arguments = 0
    option_spec = {
        "nowrap": directives.flag,
        "no-wrap": directives.flag,
        "label": directives.unchanged,
        "number": directives.flag,
    }

    def run(self) -> List[nodes.Node]:
        content = "\n".join(self.content)
        node = nodes.math_block(self.block_text, content)
        node["sdoc_label"] = self.options.get("label")
        return [node]


def _math_role(
    _name: str,
    _rawtext: str,
    text: str,
    _lineno: int,
    _inliner: Any,
    _options: Optional[Dict[str, Any]] = None,
    _content: Optional[List[str]] = None,
) -> Tuple[List[nodes.Node], List[nodes.system_message]]:
    return [nodes.math(text, text)], []


def _equation_role(
    _name: str,
    _rawtext: str,
    text: str,
    _lineno: int,
    _inliner: Any,
    _options: Optional[Dict[str, Any]] = None,
    _content: Optional[List[str]] = None,
) -> Tuple[List[nodes.Node], List[nodes.system_message]]:
    node = nodes.inline(text, text, classes=["sdoc-equation"])
    return [node], []


@contextmanager
def _docutils_registry() -> Iterator[None]:
    """
    The directives and roles that the conversion needs, without changing what
    the rest of the process has registered (StrictDoc registers its own).
    """
    saved_directives = dict(directives._directives)
    saved_roles = dict(roles._roles)
    try:
        directives._directives.pop("image", None)
        directives.register_directive("math", _EquationLabelDirective)
        roles.register_local_role("math", _math_role)
        roles.register_local_role("eq", _equation_role)
        roles.register_local_role("rawhtml", raw_html_role)
        yield
    finally:
        directives._directives.clear()
        directives._directives.update(saved_directives)
        roles._roles.clear()
        roles._roles.update(saved_roles)


class RstToMarkdownConverter:
    """
    One converter per document: the numbers of the equations are kept from one
    field to the next, and the image paths are looked up from base_dir.
    """

    def __init__(self, base_dir: str = "") -> None:
        self.base_dir = base_dir
        # Equation label -> number.
        self.equations: Dict[str, int] = {}
        self._warnings: List[str] = []
        self._constructs: Counter = Counter()  # type: ignore[type-arg]
        self._markers: List[str] = []

    # ---- Public ---------------------------------------------------------------

    def convert(self, rst: str) -> ConversionResult:
        self._warnings = []
        self._constructs = Counter()
        self._markers = []

        protected = _MARKER.sub(self._protect_marker, rst)
        tree = self._parse(protected)
        lines = self._blocks(tree.children, level=0)
        markdown = "\n".join(lines).strip("\n")
        markdown = _MARKER_WORD.sub(
            lambda match_: self._markers[int(match_.group(1))], markdown
        )
        markdown = _EQUATION_WORD.sub(self._equation_reference, markdown)
        if re.search(r"^<<<", markdown, re.MULTILINE) is not None:
            # A line that starts with <<< ends a multiline field of an SDoc
            # file, and the indentation of the RST code block that held it is
            # gone: one space keeps the field whole.
            self._warn(
                "terminator",
                "a line that starts with <<< is indented by one space",
            )
            markdown = re.sub(r"^<<<", " <<<", markdown, flags=re.MULTILINE)
        if len(markdown) > 0:
            markdown += "\n"
        return ConversionResult(
            markdown=markdown,
            warnings=list(dict.fromkeys(self._warnings)),
            constructs=self._constructs,
        )

    def convert_plain_text(self, text: str) -> ConversionResult:
        """
        The Markdown of a field of a document with MARKUP: Text. That markup
        shows the text as it is, with a line break at every new line: the
        special characters are escaped and a new line is a hard break.
        """
        self._markers = []
        protected = _MARKER.sub(self._protect_marker, text)
        paragraphs: List[str] = []
        for block_ in re.split(r"\n[ \t]*\n", protected.strip("\n")):
            lines = _escape_line_starts(
                [_escape_text(line_.rstrip()) for line_ in block_.split("\n")]
            )
            paragraphs.append("\\\n".join(lines))
        markdown = "\n\n".join(paragraphs)
        markdown = _MARKER_WORD.sub(
            lambda match_: self._markers[int(match_.group(1))], markdown
        )
        if len(markdown) > 0:
            markdown += "\n"
        return ConversionResult(markdown=markdown)

    def reference_text(self, rst: str) -> str:
        """
        The words of the RST as docutils reads them, for the check of the
        conversion: the same words must be in the Markdown. The equation
        references are the numbers that convert() gives them.
        """
        self._warnings = []
        self._markers = []
        protected = _MARKER.sub(self._protect_marker, rst)
        parts: List[str] = []
        self._collect_words(self._parse(protected), parts)
        text = " ".join(parts)
        return _MARKER_WORD.sub(
            lambda match_: self._markers[int(match_.group(1))], text
        )

    def _collect_words(self, node: nodes.Node, parts: List[str]) -> None:
        if isinstance(node, nodes.Text):
            parts.append(node.astext())
            return
        if isinstance(
            node,
            (
                nodes.system_message,
                nodes.comment,
                nodes.target,
                nodes.substitution_definition,
                nodes.pending,
                nodes.decoration,
            ),
        ):
            return
        if (
            isinstance(node, nodes.topic)
            and set(node.get("classes", [])) & _STRUCTURE_TOPICS
        ):
            return
        if isinstance(node, nodes.inline) and "sdoc-equation" in node.get(
            "classes", []
        ):
            label = node.astext()
            parts.append(str(self.equations.get(_equation_key(label), label)))
            return
        if isinstance(node, nodes.raw):
            if "html" in node.get("format", "").split():
                parts.append(re.sub(r"<[^>]*>", " ", node.astext()))
            return
        if isinstance(node, nodes.image):
            return
        if isinstance(
            node, (nodes.math_block, nodes.math, nodes.literal_block)
        ):
            parts.append(node.astext())
            return
        kind = node.__class__.__name__
        if isinstance(node, nodes.enumerated_list):
            enumtype = node.get("enumtype", "arabic")
            if enumtype != "arabic":
                start = int(node.get("start", 1) or 1)
                for index_, item_ in enumerate(node.children):
                    parts.append(_enumerator(enumtype, start + index_))
                    self._collect_words(item_, parts)
                return
        if kind in _ADMONITIONS and not any(
            isinstance(c_, nodes.title) for c_ in node.children
        ):
            parts.append(_ADMONITIONS[kind])
        for child_ in node.children:
            self._collect_words(child_, parts)

    # ---- Parsing --------------------------------------------------------------

    def _protect_marker(self, match: "re.Match[str]") -> str:
        self._markers.append(match.group(0))
        return f"SDOCMARKER{len(self._markers) - 1}END"

    def _parse(self, rst: str) -> nodes.document:
        stream = io.StringIO()
        with _docutils_registry():
            tree = publish_doctree(
                rst,
                source_path=os.path.join(
                    self.base_dir or os.getcwd(), "STRICTDOC-FRAGMENT.rst"
                ),
                settings_overrides={
                    "report_level": 5,
                    "halt_level": 5,
                    "warning_stream": stream,
                    "file_insertion_enabled": True,
                    "raw_enabled": True,
                    "input_encoding": "utf-8",
                    "syntax_highlight": "none",
                    "doctitle_xform": False,
                    "docinfo_xform": False,
                    "sectsubtitle_xform": False,
                    "strip_comments": False,
                    "embed_stylesheet": False,
                },
            )
        return tree

    def _warn(self, construct: str, message: str) -> None:
        self._warnings.append(f"{construct}: {message}")

    def _equation_reference(self, match: "re.Match[str]") -> str:
        label = match.group(1)
        number = self.equations.get(label)
        if number is None:
            self._warn("eq", f"the equation '{label}' has no label")
            return f"({label})"
        return f"({number})"

    # ---- Blocks ---------------------------------------------------------------

    def _blocks(self, children: Any, level: int) -> List[str]:
        """The Markdown lines of some block nodes, blocks apart by an empty line."""
        lines: List[str] = []
        for child_ in children:
            block = self._block(child_, level)
            if len(block) == 0:
                continue
            if len(lines) > 0:
                lines.append("")
            lines.extend(block)
        return lines

    def _block(self, node: nodes.Node, level: int) -> List[str]:
        kind = node.__class__.__name__
        handler = getattr(self, f"_block_{kind}", None)
        if handler is None:
            return self._block_unknown(node, kind)
        self._constructs[kind] += 1
        result: List[str] = handler(node, level)
        return result

    def _block_unknown(self, node: nodes.Node, kind: str) -> List[str]:
        self._constructs[kind] += 1
        self._warn(kind, "no Markdown equivalent, written as text")
        text = " ".join(node.astext().split())
        return [self._escape(text)] if len(text) > 0 else []

    def _block_paragraph(self, node: nodes.Node, _level: int) -> List[str]:
        return _escape_line_starts(self._inline(node).split("\n"))

    def _block_Text(self, node: nodes.Node, _level: int) -> List[str]:
        return [self._escape(node.astext())]

    def _block_section(self, node: nodes.Node, level: int) -> List[str]:
        title = self._inline(node.children[0]).replace("\n", " ").strip()
        depth = min(level + 1, 6)
        lines = [f"{'#' * depth} {title}"]
        body = self._blocks(node.children[1:], level + 1)
        if len(body) > 0:
            lines.append("")
            lines.extend(body)
        return lines

    def _block_bullet_list(self, node: nodes.Node, level: int) -> List[str]:
        return self._list(node, level, lambda _index: "- ")

    def _block_enumerated_list(self, node: nodes.Node, level: int) -> List[str]:
        start = int(node.get("start", 1) or 1)
        enumtype = node.get("enumtype", "arabic")
        suffix = ")" if node.get("suffix") == ")" else "."
        if enumtype != "arabic":
            # Markdown numbers with digits only: the labels stay in the text.
            self._warn(
                "enumerated_list",
                f"the {enumtype} numbering is written as text, not as a list",
            )
            return self._labelled_items(node, level, enumtype, start, suffix)
        return self._list(
            node, level, lambda index: f"{start + index}{suffix} "
        )

    def _labelled_items(
        self,
        node: nodes.Node,
        level: int,
        enumtype: str,
        start: int,
        suffix: str,
    ) -> List[str]:
        lines: List[str] = []
        for index_, item_ in enumerate(node.children):
            label = _enumerator(enumtype, start + index_)
            body = self._blocks(item_.children, level)
            first = body[0] if body else ""
            if len(lines) > 0:
                lines.append("")
            lines.append(f"{label}\\{suffix} {first}".rstrip())
            lines.extend(line_ for line_ in body[1:])
        return lines

    def _list(self, node: nodes.Node, level: int, marker: Any) -> List[str]:
        items = [
            child_
            for child_ in node.children
            if isinstance(child_, nodes.list_item)
        ]
        # An item with several blocks (not a paragraph and a list) makes a loose
        # list.
        loose = any(
            len(
                [
                    c_
                    for c_ in item_.children
                    if not isinstance(
                        c_, (nodes.bullet_list, nodes.enumerated_list)
                    )
                ]
            )
            > 1
            for item_ in items
        )
        lines: List[str] = []
        for index_, item_ in enumerate(items):
            body = self._blocks_tight(item_.children, level, loose)
            prefix = marker(index_)
            indent = " " * len(prefix)
            if len(body) == 0:
                body = [""]
            item_lines = [prefix + body[0]] + [
                (indent + line_) if len(line_) > 0 else "" for line_ in body[1:]
            ]
            if len(lines) > 0 and loose:
                lines.append("")
            lines.extend(item_lines)
        return lines

    def _blocks_tight(
        self, children: Any, level: int, loose: bool
    ) -> List[str]:
        if loose:
            return self._blocks(children, level)
        lines: List[str] = []
        for child_ in children:
            block = self._block(child_, level)
            if len(block) == 0:
                continue
            if len(lines) > 0 and not isinstance(
                child_, (nodes.bullet_list, nodes.enumerated_list)
            ):
                lines.append("")
            lines.extend(block)
        return lines

    def _block_list_item(self, node: nodes.Node, level: int) -> List[str]:
        return self._blocks(node.children, level)

    def _block_definition_list(
        self, node: nodes.Node, _level: int
    ) -> List[str]:
        parts: List[str] = []
        for item_ in node.children:
            term = ""
            definition = ""
            for child_ in item_.children:
                if isinstance(child_, nodes.term):
                    term = self._html_inline(child_)
                elif isinstance(child_, nodes.classifier):
                    term += f" ({self._html_inline(child_)})"
                elif isinstance(child_, nodes.definition):
                    definition = self._html_blocks(child_.children)
            parts.append(f"<dt>{term}</dt><dd>{definition}</dd>")
        return ["<dl>" + "".join(parts) + "</dl>"]

    def _block_block_quote(self, node: nodes.Node, level: int) -> List[str]:
        body: List[str] = []
        attribution = ""
        for child_ in node.children:
            if isinstance(child_, nodes.attribution):
                attribution = self._inline(child_).strip()
            else:
                block = self._block(child_, level)
                if len(block) > 0:
                    if len(body) > 0:
                        body.append("")
                    body.extend(block)
        if attribution:
            body.extend(["", f"— {attribution}"])
        return [f"> {line_}".rstrip() for line_ in body]

    def _block_literal_block(self, node: nodes.Node, _level: int) -> List[str]:
        classes = [c_ for c_ in node.get("classes", []) if c_ != "code"]
        language = classes[0] if classes else ""
        return self._fence(node.astext(), language)

    def _block_doctest_block(self, node: nodes.Node, _level: int) -> List[str]:
        return self._fence(node.astext(), "python")

    @staticmethod
    def _fence(code: str, language: str) -> List[str]:
        longest = max([len(m_) for m_ in re.findall(r"`+", code)] or [0])
        fence = "`" * max(3, longest + 1)
        return [fence + language] + code.split("\n") + [fence]

    def _block_line_block(self, node: nodes.Node, _level: int) -> List[str]:
        lines = [
            self._inline(line_).replace("\n", " ") for line_ in node.children
        ]
        return _escape_line_starts(
            [f"{line_}\\" for line_ in lines[:-1]] + lines[-1:]
        )

    def _block_field_list(self, node: nodes.Node, level: int) -> List[str]:
        lines: List[str] = []
        for field_ in node.children:
            name = self._inline(field_.children[0]).strip()
            body = self._blocks(field_.children[1].children, level)
            first = body[0] if body else ""
            lines.append(f"- **{name}:** {first}".rstrip())
            lines.extend(f"  {line_}" if line_ else "" for line_ in body[1:])
        return lines

    def _block_option_list(self, node: nodes.Node, level: int) -> List[str]:
        lines: List[str] = []
        for item_ in node.children:
            group = item_.children[0]
            options = ", ".join(f"`{o_.astext()}`" for o_ in group.children)
            body = self._blocks(item_.children[1].children, level)
            first = body[0] if body else ""
            lines.append(f"- {options}: {first}".rstrip())
            lines.extend(f"  {line_}" if line_ else "" for line_ in body[1:])
        return lines

    def _block_comment(self, node: nodes.Node, _level: int) -> List[str]:
        text = node.astext().strip()
        header = re.fullmatch(r"sdoc-comment:[ \t]*(.*)", text, re.DOTALL)
        if header is not None:
            # The header of a review comment (features/comments/model.py).
            return [f"<!-- sdoc-comment {header.group(1).strip()} -->"]
        text = text.replace("--", "- -")
        return [f"<!-- {text} -->"] if text else []

    def _block_raw(self, node: nodes.Node, _level: int) -> List[str]:
        formats = node.get("format", "").split()
        if "html" in formats:
            raw_html: List[str] = str(node.astext()).split("\n")
            return raw_html
        self._warn("raw", f"the raw {' '.join(formats)} block is dropped")
        return []

    def _block_transition(self, _node: nodes.Node, _level: int) -> List[str]:
        return ["---"]

    def _block_target(self, _node: nodes.Node, _level: int) -> List[str]:
        return []

    def _block_substitution_definition(
        self, _node: nodes.Node, _level: int
    ) -> List[str]:
        return []

    def _block_pending(self, _node: nodes.Node, _level: int) -> List[str]:
        return []

    def _block_decoration(self, _node: nodes.Node, _level: int) -> List[str]:
        self._warn("header/footer", "the header and footer are dropped")
        return []

    def _block_system_message(self, node: nodes.Node, _level: int) -> List[str]:
        if int(node.get("level", 1)) < 2:
            return []
        text = " ".join(node.astext().split())
        self._warn("system_message", text)
        literal = [
            c_ for c_ in node.children if isinstance(c_, nodes.literal_block)
        ]
        if literal:
            original = literal[0].astext().replace("--", "- -")
            return [f"<!-- {original} -->"]
        return []

    def _block_problematic(self, node: nodes.Node, _level: int) -> List[str]:
        return [self._escape(node.astext())]

    def _block_image(self, node: nodes.Node, _level: int) -> List[str]:
        return [self._image(node, block=True)]

    def _block_figure(self, node: nodes.Node, level: int) -> List[str]:
        lines: List[str] = []
        for child_ in node.children:
            if isinstance(child_, nodes.image):
                lines.append(self._image(child_, block=True))
            elif isinstance(child_, nodes.caption):
                lines.extend(["", f"*{self._inline(child_).strip()}*"])
            elif isinstance(child_, nodes.legend):
                lines.append("")
                lines.extend(self._blocks(child_.children, level))
        return lines

    def _block_math_block(self, node: nodes.Node, _level: int) -> List[str]:
        label = node.get("sdoc_label")
        parts = [p_.strip() for p_ in node.astext().split("\n\n") if p_.strip()]
        lines: List[str] = []
        for index_, part_ in enumerate(parts):
            if len(lines) > 0:
                lines.append("")
            tag = ""
            if index_ == 0 and label:
                number = self.equations.setdefault(
                    _equation_key(label), len(self.equations) + 1
                )
                tag = f" \\tag{{{number}}}"
            lines.extend(["$$", part_ + tag, "$$"])
        return lines

    def _block_table(self, node: nodes.Node, _level: int) -> List[str]:
        title = ""
        group = None
        for child_ in node.children:
            if isinstance(child_, nodes.title):
                title = self._inline(child_).strip()
            elif isinstance(child_, nodes.tgroup):
                group = child_
        lines: List[str] = []
        if title:
            lines.extend([f"**{title}**", ""])
        if group is None:
            return lines
        lines.append("<table>")
        for section_ in group.children:
            if isinstance(section_, nodes.colspec):
                continue
            tag = "th" if isinstance(section_, nodes.thead) else "td"
            wrapper = "thead" if tag == "th" else "tbody"
            lines.append(f"<{wrapper}>")
            for row_ in section_.children:
                cells: List[str] = []
                for entry_ in row_.children:
                    attributes = ""
                    if entry_.get("morecols"):
                        attributes += f' colspan="{entry_["morecols"] + 1}"'
                    if entry_.get("morerows"):
                        attributes += f' rowspan="{entry_["morerows"] + 1}"'
                    cells.append(
                        f"<{tag}{attributes}>{self._html_blocks(entry_.children)}</{tag}>"
                    )
                lines.append("<tr>" + "".join(cells) + "</tr>")
            lines.append(f"</{wrapper}>")
        lines.append("</table>")
        return lines

    def _block_topic(self, node: nodes.Node, level: int) -> List[str]:
        if set(node.get("classes", [])) & _STRUCTURE_TOPICS:
            self._warn("contents", "the table of contents is dropped")
            return []
        return self._titled_body(node, level)

    def _block_sidebar(self, node: nodes.Node, level: int) -> List[str]:
        body = self._titled_body(node, level)
        return ['<aside class="sdoc-sidebar">', "", *body, "", "</aside>"]

    def _block_rubric(self, node: nodes.Node, _level: int) -> List[str]:
        return [f"**{self._inline(node).strip()}**"]

    def _block_container(self, node: nodes.Node, level: int) -> List[str]:
        classes = " ".join(node.get("classes", []))
        body = self._blocks(node.children, level)
        if classes:
            return [
                f'<div class="{html_escape(classes)}">',
                "",
                *body,
                "",
                "</div>",
            ]
        return body

    def _block_compound(self, node: nodes.Node, level: int) -> List[str]:
        return self._blocks(node.children, level)

    def _titled_body(self, node: nodes.Node, level: int) -> List[str]:
        lines: List[str] = []
        children = list(node.children)
        if children and isinstance(children[0], nodes.title):
            lines.append(f"**{self._inline(children[0]).strip()}**")
            children = children[1:]
        body = self._blocks(children, level)
        if lines and body:
            lines.append("")
        return lines + body

    def _block_admonition(self, node: nodes.Node, level: int) -> List[str]:
        return self._admonition(node, "", "", level)

    def _admonition(
        self, node: nodes.Node, kind: str, title: str, level: int
    ) -> List[str]:
        children = list(node.children)
        if children and isinstance(children[0], nodes.title):
            title = self._html_inline(children[0])
            children = children[1:]
        classes = "sdoc-admonition" + (f" sdoc-{kind}" if kind else "")
        lines = [f'<div class="{classes}" role="note">']
        if title:
            lines.append(f'<p class="sdoc-admonition-title">{title}</p>')
        lines.append("")
        body = self._blocks(children, level)
        lines.extend(body)
        if body:
            lines.append("")
        lines.append("</div>")
        return lines

    # The admonitions that docutils names by their type.
    def _block_note(self, node: nodes.Node, level: int) -> List[str]:
        return self._admonition(node, "note", "Note", level)

    def _block_hint(self, node: nodes.Node, level: int) -> List[str]:
        return self._admonition(node, "hint", "Hint", level)

    def _block_tip(self, node: nodes.Node, level: int) -> List[str]:
        return self._admonition(node, "tip", "Tip", level)

    def _block_important(self, node: nodes.Node, level: int) -> List[str]:
        return self._admonition(node, "important", "Important", level)

    def _block_attention(self, node: nodes.Node, level: int) -> List[str]:
        return self._admonition(node, "attention", "Attention", level)

    def _block_caution(self, node: nodes.Node, level: int) -> List[str]:
        return self._admonition(node, "caution", "Caution", level)

    def _block_danger(self, node: nodes.Node, level: int) -> List[str]:
        return self._admonition(node, "danger", "Danger", level)

    def _block_error(self, node: nodes.Node, level: int) -> List[str]:
        return self._admonition(node, "error", "Error", level)

    def _block_warning(self, node: nodes.Node, level: int) -> List[str]:
        return self._admonition(node, "warning", "Warning", level)

    def _block_footnote(self, node: nodes.Node, _level: int) -> List[str]:
        self._warn("footnote", "a footnote is written as a comment")
        text = " ".join(node.astext().split()).replace("--", "- -")
        return [f"<!-- footnote: {text} -->"]

    def _block_citation(self, node: nodes.Node, _level: int) -> List[str]:
        self._warn("citation", "a citation is written as a comment")
        text = " ".join(node.astext().split()).replace("--", "- -")
        return [f"<!-- citation: {text} -->"]

    # ---- Images ---------------------------------------------------------------

    def _image(self, node: nodes.Node, block: bool) -> str:
        uri = self._resolve_wildcard(str(node.get("uri", "")))
        alt = str(node.get("alt", "") or "")
        width = node.get("width")
        height = node.get("height")
        align = node.get("align")
        target = node.get("target")
        needs_html = bool(width or height or (align and block))
        if needs_html:
            attributes = f'src="{html_escape(uri)}" alt="{html_escape(alt)}"'
            if width:
                attributes += f' width="{html_escape(str(width))}"'
            if height:
                attributes += f' height="{html_escape(str(height))}"'
            image = f"<img {attributes} />"
            if align in ("center", "right") and block:
                image = f'<p style="text-align: {align}">{image}</p>'
            if target:
                image = f'<a href="{html_escape(str(target))}">{image}</a>'
            return image
        image = f"![{self._escape_alt(alt)}]({_link_destination(uri)})"
        if target:
            image = f"[{image}]({_link_destination(str(target))})"
        return image

    def _resolve_wildcard(self, uri: str) -> str:
        if not uri.endswith(".*"):
            return uri
        stem = uri[:-2]
        candidates = _IMAGE_PREFERENCE + [
            extension_
            for extension_ in SUPPORTED_IMAGE_FORMATS
            if extension_ not in _IMAGE_PREFERENCE
        ]
        for extension_ in candidates:
            path = os.path.normpath(
                os.path.join(self.base_dir, stem + extension_)
            )
            if os.path.exists(path):
                return stem + extension_
        self._warn("image", f"no file for the wildcard path '{uri}'")
        return uri

    # ---- Inline ---------------------------------------------------------------

    def _inline(self, node: nodes.Node) -> str:
        """The Markdown of the inline content of a node."""
        return "".join(self._inline_node(child_) for child_ in node.children)

    def _inline_node(self, node: nodes.Node) -> str:
        if isinstance(node, nodes.Text):
            return self._escape(node.astext())
        if isinstance(node, nodes.emphasis):
            return f"*{self._inline(node)}*"
        if isinstance(node, nodes.strong):
            return f"**{self._inline(node)}**"
        if isinstance(node, nodes.title_reference):
            return f"*{self._inline(node)}*"
        if isinstance(node, nodes.literal):
            return self._code_span(node.astext())
        if isinstance(node, nodes.superscript):
            return f"<sup>{self._html_inline(node)}</sup>"
        if isinstance(node, nodes.subscript):
            return f"<sub>{self._html_inline(node)}</sub>"
        if isinstance(node, nodes.math):
            return f"${node.astext()}$"
        if isinstance(node, nodes.image):
            return self._image(node, block=False)
        if isinstance(node, nodes.raw):
            if "html" in node.get("format", "").split():
                return str(node.astext())
            self._warn("raw", "an inline raw block that is not HTML is dropped")
            return ""
        if isinstance(node, nodes.reference):
            return self._reference(node)
        if isinstance(node, nodes.inline):
            classes = node.get("classes", [])
            if "sdoc-equation" in classes:
                return f"SDOCEQUATION{_equation_key(node.astext())}END"
            return self._inline(node)
        if isinstance(
            node, (nodes.footnote_reference, nodes.citation_reference)
        ):
            self._warn(
                "footnote_reference", "a note reference is written as text"
            )
            return self._escape(f"[{node.astext()}]")
        if isinstance(node, (nodes.target, nodes.generated)):
            return self._inline(node)
        if isinstance(node, nodes.problematic):
            return self._escape(node.astext())
        if isinstance(node, (nodes.abbreviation, nodes.acronym)):
            return self._inline(node)
        if isinstance(node, nodes.substitution_reference):
            return self._inline(node)
        if isinstance(node, nodes.system_message):
            if int(node.get("level", 1)) >= 2:
                self._warn("system_message", " ".join(node.astext().split()))
            return ""
        self._warn(node.__class__.__name__, "written as text")
        return self._escape(node.astext())

    def _reference(self, node: nodes.Node) -> str:
        text = self._inline(node)
        uri = node.get("refuri")
        if uri is None:
            return text
        plain = node.astext()
        if plain == uri:
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9+.\-]*://\S+", uri) is None:
                return text
            return f"<{uri}>"
        if uri.startswith("mailto:") and plain == uri[len("mailto:") :]:
            return f"<{plain}>"
        return f"[{text}]({_link_destination(str(uri))})"

    @staticmethod
    def _code_span(text: str) -> str:
        text = text.replace("\n", " ")
        runs = re.findall(r"`+", text)
        longest = max([len(r_) for r_ in runs] or [0])
        fence = "`" * (longest + 1)
        padding = " " if text.startswith("`") or text.endswith("`") else ""
        return f"{fence}{padding}{text}{padding}{fence}"

    # ---- HTML (cells of a table, definitions) ---------------------------------

    def _html_inline(self, node: nodes.Node) -> str:
        return "".join(self._html_node(child_) for child_ in node.children)

    def _html_blocks(self, children: Any) -> str:
        parts: List[str] = []
        for child_ in children:
            parts.append(self._html_block(child_))
        return "<br>".join(part_ for part_ in parts if len(part_) > 0)

    def _html_block(self, node: nodes.Node) -> str:
        if isinstance(node, nodes.paragraph):
            return self._html_inline(node).replace("\n", " ")
        if isinstance(node, (nodes.bullet_list, nodes.enumerated_list)):
            tag = "ul" if isinstance(node, nodes.bullet_list) else "ol"
            items = "".join(
                f"<li>{self._html_blocks(item_.children)}</li>"
                for item_ in node.children
            )
            return f"<{tag}>{items}</{tag}>"
        if isinstance(node, nodes.literal_block):
            return f"<pre><code>{html_escape(node.astext())}</code></pre>"
        if isinstance(node, nodes.image):
            return self._image(node, block=False)
        if isinstance(node, nodes.line_block):
            return "<br>".join(
                self._html_inline(line_) for line_ in node.children
            )
        if isinstance(node, nodes.system_message):
            return ""
        self._warn(node.__class__.__name__, "written as text in a cell")
        return html_escape(" ".join(node.astext().split()))

    def _html_node(self, node: nodes.Node) -> str:
        if isinstance(node, nodes.Text):
            return html_escape(str(node.astext()), quote=False)
        if isinstance(node, nodes.emphasis):
            return f"<em>{self._html_inline(node)}</em>"
        if isinstance(node, nodes.strong):
            return f"<strong>{self._html_inline(node)}</strong>"
        if isinstance(node, nodes.title_reference):
            return f"<em>{self._html_inline(node)}</em>"
        if isinstance(node, nodes.literal):
            return f"<code>{html_escape(node.astext(), quote=False)}</code>"
        if isinstance(node, nodes.superscript):
            return f"<sup>{self._html_inline(node)}</sup>"
        if isinstance(node, nodes.subscript):
            return f"<sub>{self._html_inline(node)}</sub>"
        if isinstance(node, nodes.math):
            return html_escape(f"${node.astext()}$", quote=False)
        if isinstance(node, nodes.image):
            return self._image(node, block=False)
        if isinstance(node, nodes.raw):
            return (
                node.astext()
                if "html" in node.get("format", "").split()
                else ""
            )
        if isinstance(node, nodes.reference):
            uri = node.get("refuri")
            if uri is None:
                return self._html_inline(node)
            return f'<a href="{html_escape(str(uri))}">{self._html_inline(node)}</a>'
        if isinstance(node, nodes.inline):
            if "sdoc-equation" in node.get("classes", []):
                return f"SDOCEQUATION{_equation_key(node.astext())}END"
            return self._html_inline(node)
        if isinstance(node, nodes.system_message):
            return ""
        return html_escape(str(node.astext()), quote=False)

    # ---- Escaping -------------------------------------------------------------

    @staticmethod
    def _escape(text: str) -> str:
        return _escape_text(text)

    @staticmethod
    def _escape_alt(text: str) -> str:
        return (
            text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
        )


def _enumerator(enumtype: str, number: int) -> str:
    """The label of an item of an alphabetic or roman list."""
    if enumtype in ("loweralpha", "upperalpha"):
        letter = chr(ord("a") + (number - 1) % 26)
        return letter.upper() if enumtype == "upperalpha" else letter
    numerals = [
        (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
    ]  # fmt: skip
    remaining = number
    roman = ""
    for value_, numeral_ in numerals:
        while remaining >= value_:
            roman += numeral_
            remaining -= value_
    return roman.upper() if enumtype == "upperroman" else roman


def _equation_key(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", label)


def _link_destination(uri: str) -> str:
    if re.search(r"[\s()<>]", uri):
        return "<" + uri.replace("<", "%3C").replace(">", "%3E") + ">"
    return uri


_UNDERSCORE = re.compile(r"(?<![A-Za-z0-9])_|_(?![A-Za-z0-9])")
_ENTITY = re.compile(r"&(?=#?[A-Za-z0-9]+;)")


def _escape_text(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = re.sub(r"([`*<\[\]$])", r"\\\1", text)
    text = text.replace("~~", "\\~\\~")
    text = _UNDERSCORE.sub(r"\\_", text)
    text = _ENTITY.sub("&amp;", text)
    return text


_LINE_START = re.compile(
    r"^(\s*)(#{1,6}(?=\s|$)|>|[-+*](?=\s)|\d{1,9}[.)](?=\s|$)|={2,}\s*$|-{2,}\s*$)"
)


def _escape_line_starts(lines: List[str]) -> List[str]:
    """What Markdown would read as a block when it starts a line."""
    escaped: List[str] = []
    for source_ in lines:
        line = source_.strip(" ")
        match = _LINE_START.match(line)
        if match is not None:
            start = match.end(1)
            if line[start] in "-=":
                line = line[:start] + "\\" + line[start:]
            elif line[start].isdigit():
                position = re.search(r"[.)]", line[start:])
                assert position is not None
                at = start + position.start()
                line = line[:at] + "\\" + line[at:]
            else:
                line = line[:start] + "\\" + line[start:]
        escaped.append(line)
    return escaped


__all__ = ["ConversionResult", "RstToMarkdownConverter"]
