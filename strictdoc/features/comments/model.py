"""
A review comment: author, date, state and text, kept in the value of a
COMMENT field (no change of the SDoc grammar).

The first line of the value is a header that does not render:

- RST: ``.. sdoc-comment: id=c7f3a9 author=anna date=2026-10-10T12:00:00Z status=open``
- Markdown: ``<!-- sdoc-comment id=c7f3a9 author=anna date=... status=open -->``

The text follows after a blank line. A COMMENT without a header (every comment
written before this feature) is a legacy comment: no author, no date, open.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import quote, unquote

STATUS_OPEN = "open"
STATUS_RESOLVED = "resolved"
STATUSES = (STATUS_OPEN, STATUS_RESOLVED)

_RST_HEADER = re.compile(r"^\.\. sdoc-comment:[ \t]*(.*)$")
_MARKDOWN_HEADER = re.compile(r"^<!-- sdoc-comment[ \t]+(.*?)[ \t]*-->$")
_SAFE = "@.-_"

# Header keys, in the order they are written.
_KEYS = (
    "id",
    "author",
    "date",
    "status",
    "resolved_by",
    "resolved_on",
    "source",
    # A node drafted by a language model carries where it came from.
    "model",
    "provider",
    "prompt",
    "accepted_by",
    # The words of the text that the comment is about, and which occurrence of
    # them in the node (0 for the first): the page highlights them.
    "anchor",
    "anchor_n",
)


@dataclass
class Comment:
    body: str
    id: str = ""
    author: str = ""
    date: str = ""
    status: str = STATUS_OPEN
    resolved_by: str = ""
    resolved_on: str = ""
    # "web" for a comment written in the interface, "word" for one that was
    # read from a Word document.
    source: str = ""
    model: str = ""
    provider: str = ""
    prompt: str = ""
    accepted_by: str = ""
    anchor: str = ""
    anchor_n: str = ""
    # True when the value had no header.
    legacy: bool = field(default=False, compare=False)

    @property
    def is_resolved(self) -> bool:
        return self.status == STATUS_RESOLVED

    @property
    def author_label(self) -> str:
        return self.author if self.author else "unknown"

    @staticmethod
    def new(
        author: str,
        body: str,
        source: str = "web",
        anchor: str = "",
        anchor_n: int = 0,
    ) -> "Comment":
        anchor = clean_anchor(anchor)
        return Comment(
            body=body.strip(),
            id=uuid.uuid4().hex[:8],
            author=author,
            date=now_iso(),
            status=STATUS_OPEN,
            source=source,
            anchor=anchor,
            anchor_n=str(max(0, anchor_n)) if anchor else "",
        )


MAX_ANCHOR = 200


def clean_anchor(text: str) -> str:
    """The selected words of a comment: one line, at most MAX_ANCHOR characters."""
    return " ".join(text.split())[:MAX_ANCHOR]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_comment(value: str) -> Comment:
    """The comment of a COMMENT value, with or without a header."""
    stripped = value.strip("\n")
    first_line, _, rest = stripped.partition("\n")
    fields: Optional[str] = None
    for pattern_ in (_RST_HEADER, _MARKDOWN_HEADER):
        match = pattern_.match(first_line.strip())
        if match is not None:
            fields = match.group(1)
            break
    if fields is None:
        return Comment(body=stripped.strip(), legacy=True)

    values: Dict[str, str] = {}
    for item_ in fields.split():
        key, separator, raw = item_.partition("=")
        if separator and key in _KEYS:
            values[key] = unquote(raw)
    status = values.get("status", STATUS_OPEN)
    return Comment(
        body=rest.strip(),
        id=values.get("id", ""),
        author=values.get("author", ""),
        date=values.get("date", ""),
        status=status if status in STATUSES else STATUS_OPEN,
        resolved_by=values.get("resolved_by", ""),
        resolved_on=values.get("resolved_on", ""),
        source=values.get("source", ""),
        model=values.get("model", ""),
        provider=values.get("provider", ""),
        prompt=values.get("prompt", ""),
        accepted_by=values.get("accepted_by", ""),
        anchor=values.get("anchor", ""),
        anchor_n=values.get("anchor_n", ""),
    )


def format_comment(comment: Comment, markup: str) -> str:
    """The COMMENT value of a comment: the header, a blank line, the text."""
    parts: List[str] = []
    for key_ in _KEYS:
        value = getattr(comment, key_)
        if len(value) > 0 and not (key_ == "status" and value == ""):
            parts.append(f"{key_}={quote(value, safe=_SAFE)}")
    fields = " ".join(parts)
    if markup == "Markdown":
        header = f"<!-- sdoc-comment {fields} -->"
    else:
        header = f".. sdoc-comment: {fields}"
    return f"{header}\n\n{comment.body.strip()}"


def initials(author: str) -> str:
    """Initials for Word: 'anna.durand' gives 'AD'."""
    words = [word_ for word_ in re.split(r"[^A-Za-z0-9]+", author) if word_]
    letters = "".join(word_[0].upper() for word_ in words[:3])
    return letters or "?"
