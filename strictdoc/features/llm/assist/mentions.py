"""
The @ mentions of the assistant bar: finding them in the typed text, searching
them for the autocomplete, and turning them into the blocks of context that go
into the prompt.

The server resolves the mentions from the text itself; what the browser says
about them is never used. Whatever a mention names goes into the prompt as data
between BEGIN and END lines (see features/llm/context.py).
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.core.document_iterator import SDocDocumentIterator
from strictdoc.features.hierarchy.source import (
    IndexReferenceSource,
    build_reference_resolver,
)
from strictdoc.features.llm.context import (
    KIND_NODE,
    KIND_PARENT,
    ContextError,
    ContextItem,
    _dedupe,
    _input_items,
    _item,
    _neighbours,
)

KIND_SELECTION = "selection"
MAX_MENTIONS = 20
MAX_SUGGESTIONS = 8
SPECIAL = ("selection", "this", "parents", "children", "neighbours", "doc")
_MENTION = re.compile(
    r"(?<![\w@])@([A-Za-z0-9_][\w.\-]*(?::[^\s,;]+)?(?:\s+§\s?[\w.\-]+)?)"
)
_TRAILING = ".,;:)!?"


@dataclass
class Resolved:
    items: List[ContextItem] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def find_mentions(text: str) -> List[str]:
    """The distinct mentions of a text, without the @, in order."""
    tokens: List[str] = []
    for match_ in _MENTION.finditer(text):
        token = re.sub(r"\s+", " ", match_.group(1)).rstrip(_TRAILING)
        if token and token not in tokens:
            tokens.append(token)
    return tokens[:MAX_MENTIONS]


def _safe(name: str) -> str:
    return re.sub(r"[^\w.\-]", "_", name)[:40]


def _stem(document: SDocDocument) -> str:
    meta = document.meta
    return meta.document_filename_base if meta is not None else ""


def _documents(index: Any) -> List[SDocDocument]:
    return list(index.document_tree.document_list)


def _find_document(index: Any, name: str) -> Optional[SDocDocument]:
    wanted = name.strip().lower()
    for document_ in _documents(index):
        if _stem(document_).lower() == wanted:
            return document_
    for document_ in _documents(index):
        if document_.title.strip().lower() == wanted:
            return document_
    return None


def _document_items(
    document: SDocDocument, limit_chars: int
) -> "tuple[List[ContextItem], bool]":
    """
    The nodes of a document. Too big (more than the limit): only the outline,
    the UID and the title of each node, and a flag that says so.
    """
    kind = "document:" + _safe(_stem(document) or document.title)
    nodes: List[SDocNode] = []
    for node_, _ in SDocDocumentIterator(
        document=document, node_filter=None
    ).all_content(print_fragments=False):
        if isinstance(node_, SDocNode):
            nodes.append(node_)
    items = [_item(kind, node_) for node_ in nodes]
    total = sum(len(item_.text) for item_ in items)
    if total <= limit_chars:
        return items, False
    outline = [
        ContextItem(
            kind=item_.kind,
            uid=item_.uid,
            title=item_.title,
            text="",
            document_title=item_.document_title,
            classification=item_.classification,
        )
        for item_ in items
    ]
    return outline, True


def resolve_mentions(
    *,
    index: Any,
    applicable_documents: Dict[str, str],
    tokens: List[str],
    target_node: Optional[SDocNode],
    target_document: Optional[SDocDocument],
    selection_text: str,
    limit_chars: int,
) -> Resolved:
    """The context items of the mentions; unknown ones are reported."""
    resolved = Resolved()
    resolver = build_reference_resolver(applicable_documents, index)
    source = IndexReferenceSource(index, applicable_documents)
    for token_ in tokens:
        lowered = token_.lower()
        try:
            items = _resolve_one(
                index=index,
                source=source,
                resolver=resolver,
                token=token_,
                lowered=lowered,
                target_node=target_node,
                target_document=target_document,
                selection_text=selection_text,
                limit_chars=limit_chars,
                resolved=resolved,
            )
        except ContextError as exception_:
            resolved.unresolved.append(f"@{token_}: {exception_}")
            continue
        if items is None:
            resolved.unresolved.append(f"@{token_}: not found.")
            continue
        resolved.items.extend(items)
    resolved.items = _dedupe(resolved.items)
    return resolved


def _resolve_one(
    *,
    index: Any,
    source: IndexReferenceSource,
    resolver: Any,
    token: str,
    lowered: str,
    target_node: Optional[SDocNode],
    target_document: Optional[SDocDocument],
    selection_text: str,
    limit_chars: int,
    resolved: Resolved,
) -> Optional[List[ContextItem]]:
    if lowered == "selection":
        if not selection_text:
            raise ContextError("nothing is selected.")
        return [
            ContextItem(
                kind=KIND_SELECTION,
                uid="",
                title="selection",
                text=selection_text,
            )
        ]
    if lowered == "this":
        if target_node is None:
            raise ContextError("this requirement is not saved yet.")
        return [_item(KIND_NODE, target_node)]
    if lowered in ("parents", "children", "neighbours"):
        if target_node is None:
            raise ContextError("this requirement is not saved yet.")
        if lowered == "parents":
            return [
                _item(KIND_PARENT, node_)
                for node_ in index.get_parent_requirements(target_node)
            ]
        if lowered == "children":
            return [
                _item("child", node_)
                for node_ in index.get_children_requirements(target_node)
            ]
        return [
            _item("neighbour", node_) for node_ in _neighbours(target_node, 3)
        ]
    if lowered == "doc":
        if target_document is None:
            raise ContextError("there is no current document.")
        items, outline_only = _document_items(target_document, limit_chars)
        if outline_only:
            resolved.notes.append(
                "@doc is too big: only its outline is given; mention a UID "
                "or a section."
            )
        return items
    if lowered.startswith("section:"):
        title = token.split(":", 1)[1].strip().lower()
        document = target_document
        found = _find_section(document, title) if document else None
        if found is None:
            raise ContextError("no section with that title here.")
        return _input_section_items(found)
    # An input document section: "DA1 §5.14.1".
    if "§" in token:
        short, _, rest = token.partition("§")
        reference = f"[{short.strip()}] §{rest.strip()}"
        return _input_items(index, reference, resolver)
    node = index.get_node_by_uid_weak2(token)
    if isinstance(node, SDocNode):
        return [_item("requirement", node)]
    document = source.documents.get(token) or _find_document(index, token)
    if document is not None:
        items, outline_only = _document_items(document, limit_chars)
        if outline_only:
            resolved.notes.append(
                f"@{token} is too big: only its outline is given; mention "
                "a UID or a section (@DA1 §5.2)."
            )
        return items
    return None


def _find_section(
    document: Optional[SDocDocument], title: str
) -> Optional[SDocNode]:
    if document is None:
        return None
    for node_, _ in SDocDocumentIterator(
        document=document, node_filter=None
    ).all_content(print_fragments=False):
        if (
            isinstance(node_, SDocNode)
            and node_.node_type == "SECTION"
            and (node_.reserved_title or "").strip().lower() == title
        ):
            return node_
    return None


def _input_section_items(section: SDocNode) -> List[ContextItem]:
    items = [_item("section", section)]
    for child_ in getattr(section, "section_contents", []):
        if isinstance(child_, SDocNode):
            items.extend(_input_section_items(child_))
    return items


def search_mentions(
    *,
    index: Any,
    applicable_documents: Dict[str, str],
    query: str,
    target_node_available: bool,
    selection_available: bool,
    limit: int = MAX_SUGGESTIONS,
) -> List[Dict[str, str]]:
    """The suggestions of the @ list for what the user has typed so far."""
    wanted = query.strip().lower()
    found: List[Dict[str, str]] = []

    def add(token: str, kind: str, label: str, detail: str = "") -> None:
        if len(found) < limit:
            found.append(
                {"token": token, "kind": kind, "label": label, "detail": detail}
            )

    for name_ in SPECIAL:
        if name_.startswith(wanted):
            if name_ == "selection" and not selection_available:
                continue
            if (
                name_ in ("this", "parents", "children", "neighbours")
                and not target_node_available
            ):
                continue
            add(name_, "special", name_)
    for short_, location_ in applicable_documents.items():
        if short_.lower().startswith(wanted):
            add(short_, "input", short_, location_)
    for document_ in _documents(index):
        stem = _stem(document_)
        if stem and (
            wanted in stem.lower() or wanted in document_.title.lower()
        ):
            add(stem, "document", document_.title, stem)
    if wanted:
        for document_ in _documents(index):
            for node_, _ in SDocDocumentIterator(
                document=document_, node_filter=None
            ).all_content(print_fragments=False):
                if len(found) >= limit:
                    return found
                if not isinstance(node_, SDocNode) or not node_.reserved_uid:
                    continue
                uid = node_.reserved_uid
                title = node_.reserved_title or ""
                if wanted in uid.lower() or (
                    len(wanted) >= 3 and wanted in title.lower()
                ):
                    add(uid, "requirement", title or uid, document_.title)
    return found
