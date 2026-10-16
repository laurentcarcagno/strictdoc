"""
What the view of the conflicts shows: each region of a merge as nodes, on the
server side and on the local side.

A block is read with the header of its own version of the document (so that a
custom grammar is known) and shown like the document screen shows a node: its
title, its UID, its fields. A block that cannot be read is shown as text.
"""

import html
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Sequence

from markupsafe import Markup

from strictdoc.backend.sdoc.reader import SDReader
from strictdoc.features.git_sync.blocks import Block
from strictdoc.features.git_sync.merge3 import (
    CONFLICT,
    SAME,
    Region,
)
from strictdoc.helpers.exception import StrictDocException

# Shows a field: (markup of the document, text of the field) -> HTML, or
# raises when it cannot be rendered (then the text is shown).
FieldRenderer = Callable[[Optional[str], object], Markup]

_HIDDEN_FIELDS = ("MID", "UID", "TITLE")


@dataclass
class FieldView:
    label: str
    html: Markup


@dataclass
class NodeView:
    kind: str
    title: str
    uid: str
    fields: List[FieldView] = field(default_factory=list)
    # Text of a block that could not be read as a node.
    raw: str = ""
    # The other side has not this node, or has it different.
    differs: bool = False
    # A closing line of a section: nothing to show but the end of the section.
    closing: bool = False


@dataclass
class RowView:
    """A row of the view: a region, or a run of regions that did not change."""

    index: int  # the index of the region (of the first one of a run)
    kind: str
    left: List[NodeView]
    right: List[NodeView]
    local_text: str = ""
    server_text: str = ""
    both_text: str = ""


def _plain(text: str) -> Markup:
    return Markup("<pre class='gs-text'>%s</pre>") % text


def _node_view(
    block: Block, header: str, render_field: FieldRenderer
) -> NodeView:
    if block.kind.startswith("/"):
        return NodeView(block.kind, "", "", closing=True)
    if block.kind == "header":
        return NodeView("DOCUMENT", block.title, "", raw=block.text)
    closing = "[[/SECTION]]\n" if block.kind == "SECTION" else ""
    if block.kind == "COMPOSITE_REQUIREMENT":
        closing = "[[/COMPOSITE_REQUIREMENT]]\n"
    try:
        document = SDReader.read(header + block.text + closing)
        node: Any = document.section_contents[0]
        markup = document.config.markup if document.config else None
        fields: List[FieldView] = []
        for name_, found in node.ordered_fields_lookup.items():
            if name_ in _HIDDEN_FIELDS:
                continue
            for field_ in found:
                try:
                    shown = render_field(markup, field_)
                except Exception:  # noqa: BLE001 (any renderer failure)
                    shown = _plain(html.escape(field_.get_text_value()))
                fields.append(FieldView(name_, shown))
        return NodeView(
            block.kind,
            node.reserved_title or "",
            node.reserved_uid or "",
            fields,
        )
    except (StrictDocException, IndexError, AttributeError):
        return NodeView(block.kind, block.title, "", raw=block.text)


def header_of(blocks: Sequence[Block]) -> str:
    """The header block of a document: its title, options and grammar."""
    for block_ in blocks:
        if block_.kind == "header":
            return block_.text
    return "[DOCUMENT]\nTITLE: -\n\n"


def _views(
    blocks: Sequence[Block],
    header: str,
    other: Sequence[Block],
    render_field: FieldRenderer,
    mark: bool,
) -> List[NodeView]:
    others = {block_.key: block_.text for block_ in other}
    views: List[NodeView] = []
    for block_ in blocks:
        view = _node_view(block_, header, render_field)
        if mark and not view.closing:
            view.differs = others.get(block_.key) != block_.text
        views.append(view)
    return views


def build_rows(
    regions: Sequence[Region],
    local_header: str,
    server_header: str,
    render_field: FieldRenderer,
) -> List[RowView]:
    """The rows of the view; the regions that did not change are one row."""
    rows: List[RowView] = []
    for index_, region_ in enumerate(regions):
        changed = region_.kind != SAME
        left = _views(
            region_.server, server_header, region_.local, render_field, changed
        )
        right = _views(
            region_.local, local_header, region_.server, render_field, changed
        )
        if region_.kind == SAME and rows and rows[-1].kind == SAME:
            rows[-1].left.extend(left)
            rows[-1].right.extend(right)
            continue
        rows.append(
            RowView(
                index=index_,
                kind=region_.kind,
                left=left,
                right=right,
                local_text=region_.local_text,
                server_text=region_.server_text,
                both_text=region_.choice_text("both"),
            )
        )
    return rows


def count_conflicts(rows: Sequence[RowView]) -> int:
    return sum(1 for row_ in rows if row_.kind == CONFLICT)
