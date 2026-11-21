"""
A .sdoc or .md text as a list of blocks, the unit of the merge.

A block starts at a line that opens a node ("[REQUIREMENT]", "[[SECTION]]",
"[TEXT]", ...) or closes a section ("[[/SECTION]]") and runs to the next such
line. The text before the first node (the document header, its free text and
its grammar) is the first block. The text of a block is kept as it is, so a
merged file is the concatenation of the blocks and nothing is re-written.

A block has a key that tells it from the others across versions: its MID, else
its UID, else a hash of its text (then a changed block is a removed and an
added one). The closing line of a section has the key of its section.

In a Markdown document (split_markdown_blocks) a block starts at a heading and
runs to the next one: the title, the metadata and the text before the first
heading below the title are the first block. A section has no closing line,
its depth is the level of its heading.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# A line that opens a node or a section, or closes a section. "[/FREETEXT]"
# (one bracket) is part of its block.
_MARKER = re.compile(r"^\[\[?(/?)([A-Z][A-Z0-9_]*)\]\]?\s*$")
# The lines of the header: they do not open a node.
_HEADER_MARKERS = ("DOCUMENT", "FREETEXT", "GRAMMAR")
_IDENTITY = re.compile(r"^(MID|UID): *(\S.*?)\s*$")
_HEADING = re.compile(r"^(#{1,6})[ \t]")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_MARKDOWN_IDENTITY = re.compile(
    r"^\*\*(MID|UID)\*\*: *`?([^`\s\\]+)`?[ \t]*\\?\s*$"
)


@dataclass(frozen=True)
class Block:
    kind: str  # "header", the node type, or "/SECTION" (a closing line)
    key: str
    text: str

    @property
    def title(self) -> str:
        for line_ in self.text.splitlines():
            if line_.startswith("TITLE:"):
                return line_[len("TITLE:") :].strip()
            if _HEADING.match(line_):
                return line_.lstrip("#").strip()
        return ""


def _identity(lines: List[str]) -> Optional[str]:
    """MID, else UID, of a block (outside the multiline values)."""
    found = {}
    inside = False
    for line_ in lines:
        if inside:
            if line_.rstrip() == "<<<":
                inside = False
            continue
        if line_.rstrip().endswith(">>>"):
            inside = True
            continue
        match = _IDENTITY.match(line_)
        if match is not None and match.group(1) not in found:
            found[match.group(1)] = match.group(2)
    for name_ in ("MID", "UID"):
        if name_ in found:
            return f"{name_}:{found[name_]}"
    return None


def split_blocks(text: str) -> List[Block]:
    """The blocks of a document text; "".join(b.text) gives the text back."""
    lines = text.splitlines(keepends=True)
    raw: List[Tuple[str, List[str]]] = []  # (kind, [lines])
    current_kind = "header"
    current: List[str] = []
    inside = False  # in a multiline value (">>>" ... "<<<")
    for line_ in lines:
        if inside:
            current.append(line_)
            if line_.rstrip() == "<<<":
                inside = False
            continue
        match = _MARKER.match(line_.rstrip("\r\n"))
        starts = False
        kind = ""
        if match is not None:
            closing, name = match.group(1), match.group(2)
            double = line_.lstrip().startswith("[[")
            if closing and double:
                starts, kind = True, "/" + name
            elif not closing and name not in _HEADER_MARKERS:
                starts, kind = True, name
        if starts:
            raw.append((current_kind, current))
            current_kind, current = kind, []
        current.append(line_)
        if line_.rstrip().endswith(">>>"):
            inside = True
    raw.append((current_kind, current))

    blocks: List[Block] = []
    stack: List[str] = []  # the keys of the open sections
    for kind_, block_lines in raw:
        if kind_ == "header" and not block_lines:
            continue
        body = "".join(block_lines)
        identity = _identity(block_lines)
        if kind_.startswith("/"):
            opened = stack.pop() if stack else "?"
            key = f"close:{opened}"
        else:
            if identity is None:
                digest = hashlib.sha1(body.encode("utf8")).hexdigest()[:12]
                identity = f"hash:{kind_}:{digest}"
            key = identity
            if kind_ == "header":
                key = "header"
            elif kind_ in ("SECTION", "COMPOSITE_REQUIREMENT"):
                stack.append(key)
        blocks.append(Block(kind_, key, body))
    return blocks


def _markdown_identity(lines: List[str]) -> Optional[str]:
    """MID, else UID, in the meta block that follows the heading."""
    found = {}
    started = False
    for line_ in lines[1:]:
        if len(line_.strip()) == 0:
            if started:
                break
            continue
        started = True
        match = _MARKDOWN_IDENTITY.match(line_.rstrip("\r\n"))
        if match is not None and match.group(1) not in found:
            found[match.group(1)] = match.group(2)
    for name_ in ("MID", "UID"):
        if name_ in found:
            return f"{name_}:{found[name_]}"
    return None


def split_markdown_blocks(text: str) -> List[Block]:
    """The blocks of a Markdown document; "".join(b.text) gives the text back."""
    raw: List[Tuple[str, List[str]]] = []
    current_kind = "header"
    current: List[str] = []
    fence: Optional[str] = None
    title_seen = False
    for line_ in text.splitlines(keepends=True):
        fence_match = _FENCE.match(line_)
        if fence_match is not None:
            marker = fence_match.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence):
                fence = None
        elif fence is None and _HEADING.match(line_):
            if not title_seen:
                title_seen = True
            else:
                raw.append((current_kind, current))
                current_kind, current = "NODE", []
        current.append(line_)
    raw.append((current_kind, current))

    blocks: List[Block] = []
    for kind_, block_lines in raw:
        if kind_ == "header" and not block_lines:
            continue
        body = "".join(block_lines)
        if kind_ == "header":
            key = "header"
        else:
            key = _markdown_identity(block_lines) or (
                "hash:NODE:"
                + hashlib.sha1(body.encode("utf8")).hexdigest()[:12]
            )
        blocks.append(Block(kind_, key, body))
    return blocks
