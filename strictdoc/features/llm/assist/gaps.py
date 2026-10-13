"""
/gap: what is not covered, found without a model.

With mentions (@DA1, @icd1, @DA1 §5.2): the nodes of those documents or
sections that no requirement derives from. Without: the requirements of the
document that have no parent. Every point is a finding with the UID in its
message.
"""

from typing import Any, List

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.core.document_iterator import SDocDocumentIterator
from strictdoc.features.llm.assist.envelope import Finding
from strictdoc.features.llm.context import ContextItem, node_text

MAX_REPORTED = 50
RULE = "R-GAP"


def _excerpt(node: SDocNode) -> str:
    text = " ".join(node_text(node).split())
    return text[:90] + ("…" if len(text) > 90 else "")


def uncovered_in(
    index: Any, items: List[ContextItem]
) -> "tuple[List[SDocNode], int]":
    """The mentioned nodes that have no child, and how many were looked at."""
    checked = 0
    gaps: List[SDocNode] = []
    seen = set()
    for item_ in items:
        if not item_.uid or item_.uid in seen:
            continue
        seen.add(item_.uid)
        node = index.get_node_by_uid_weak2(item_.uid)
        if (
            not isinstance(node, SDocNode)
            or node.node_type == "SECTION"
            or not node_text(node)
        ):
            continue
        checked += 1
        if not index.get_children_requirements(node):
            gaps.append(node)
    return gaps, checked


def orphans_of(
    index: Any, document: SDocDocument
) -> "tuple[List[SDocNode], int]":
    """The requirements of a document that have no parent."""
    checked = 0
    gaps: List[SDocNode] = []
    for node_, _ in SDocDocumentIterator(
        document=document, node_filter=None
    ).all_content(print_fragments=False):
        if (
            isinstance(node_, SDocNode)
            and node_.node_type not in ("SECTION", "TEXT")
            and node_.reserved_uid
        ):
            checked += 1
            if not index.get_parent_requirements(node_):
                gaps.append(node_)
    return gaps, checked


def findings_of(
    gaps: List[SDocNode], checked: int, what: str
) -> "tuple[str, List[Finding], List[str]]":
    """The message, the findings and the warnings for a list of gaps."""
    findings = [
        Finding(
            severity="warning",
            rule=RULE,
            quote="",
            message=f"{node_.reserved_uid} {what}: {_excerpt(node_)}",
            source="check",
        )
        for node_ in gaps[:MAX_REPORTED]
    ]
    warnings: List[str] = []
    if len(gaps) > MAX_REPORTED:
        warnings.append(
            f"Only the first {MAX_REPORTED} of {len(gaps)} are listed."
        )
    covered = checked - len(gaps)
    message = (
        f"{covered} of {checked} covered, {len(gaps)} not."
        if checked
        else "Nothing to check here."
    )
    return message, findings, warnings
