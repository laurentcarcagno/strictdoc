"""
/kbcheck: the citations of the knowledge base that no longer match it.

/cite writes a requirement of the base as a quote that ends with its source:

    > The OBC shall send the heartbeat packet every 500 ms.
    > — ISIS-IF-249-0100, ISIS-SYS-IF-249-CNES ed. 9.0 §3.2 (kb://isis/…/9.0/3.2)

This finds those quotes in the text of a document and asks the base for each
requirement again, with no model. A quote is a finding when the requirement is
gone, when the document has a newer edition or when the text is not the one of
the base any more (the base changed, or the quote was edited by hand).
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from strictdoc.features.kb.client import KBResult

RULE_GONE = "R-KB-GONE"
RULE_EDITION = "R-KB-EDITION"
RULE_CHANGED = "R-KB-CHANGED"
RULE_UNCHECKED = "R-KB-UNCHECKED"

_FOOTER = re.compile(
    r"^>\s*—\s*(?P<id>[^\s,]+),\s.*\((?P<ref>kb://[^)\s]+)\)\s*$"
)


@dataclass(frozen=True)
class Citation:
    req_id: str
    mission: str
    doc_ref: str
    edition: str
    section: str
    quote: str


def find_citations(text: str) -> List[Citation]:
    """The quotes written by /cite in a text."""
    found: List[Citation] = []
    lines = text.splitlines()
    for number_, line_ in enumerate(lines):
        footer = _FOOTER.match(line_.strip())
        if footer is None:
            continue
        parts = footer.group("ref")[len("kb://") :].split("/", 3)
        if len(parts) != 4:
            continue
        quote: List[str] = []
        before = number_ - 1
        while before >= 0 and lines[before].lstrip().startswith(">"):
            quote.insert(0, lines[before].lstrip()[1:].strip())
            before -= 1
        found.append(
            Citation(
                req_id=footer.group("id"),
                mission=parts[0],
                doc_ref=parts[1],
                edition=parts[2],
                section=parts[3],
                quote="\n".join(quote),
            )
        )
    return found


def _same(first: str, second: str) -> bool:
    return " ".join(first.split()) == " ".join(second.split())


def check(
    citation: Citation, current: Optional[KBResult]
) -> List[tuple[str, str, str]]:
    """
    (severity, rule, message) for one quote; empty when it still matches.
    `current` is the answer of get_requirement, None when the base was not
    reached.
    """
    if current is None:
        return [
            (
                "info",
                RULE_UNCHECKED,
                f"{citation.req_id} was not compared: the base was not reached.",
            )
        ]
    if not current.ok:
        return [
            (
                "error",
                RULE_GONE,
                (
                    f"{citation.req_id} is not in the base any more "
                    f"({citation.doc_ref} ed. {citation.edition})."
                ),
            )
        ]
    if current.truncated or not current.citations:
        return [
            (
                "info",
                RULE_UNCHECKED,
                f"{citation.req_id} is too long to be compared here.",
            )
        ]
    result: List[tuple[str, str, str]] = []
    now = current.citations[0]
    if (
        str(now.get("doc_ref")) != citation.doc_ref
        or str(now.get("edition")) != citation.edition
    ):
        result.append(
            (
                "warning",
                RULE_EDITION,
                (
                    f"{citation.req_id} is now in {now.get('doc_ref')} ed. "
                    f"{now.get('edition')}; the quote is from "
                    f"{citation.doc_ref} ed. {citation.edition}."
                ),
            )
        )
    if not _same(str(current.data.get("text") or ""), citation.quote):
        result.append(
            (
                "warning",
                RULE_CHANGED,
                (
                    f"The text of {citation.req_id} is not the one of the "
                    "base: cite it again (/cite) to replace the quote."
                ),
            )
        )
    return result


def by_requirement(
    citations: List[Citation],
) -> Dict[str, Citation]:
    """One citation per requirement, the first found (to ask the base once)."""
    unique: Dict[str, Citation] = {}
    for citation_ in citations:
        unique.setdefault(citation_.req_id, citation_)
    return unique
