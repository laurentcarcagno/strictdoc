"""
The one-off action that links the requirements of a project to its applicable
documents: it reads the relation columns that the Word profile names
(``relation_fields``), resolves the references they hold ("[DA2] REQ-106005")
and adds the missing Parent relations. The text of the columns is not changed.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple

from strictdoc.backend.docx.docx_export import load_project_profile
from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.backend.sdoc.models.reference import ParentReqReference
from strictdoc.core.document_iterator import SDocDocumentIterator
from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.hierarchy.levels import is_input_document
from strictdoc.features.hierarchy.source import build_reference_resolver
from strictdoc.helpers.exception import StrictDocException


@dataclass
class ResolveReport:
    requirements_with_references: int = 0
    links_added: int = 0
    already_linked: int = 0
    # (UID of the requirement, why a reference could not be resolved).
    unresolved: List[Tuple[str, str]] = field(default_factory=list)
    documents_changed: List[str] = field(default_factory=list)
    applied: bool = False

    def format(self) -> str:
        summary = (
            f"{self.requirements_with_references} requirement(s) with "
            f"references: {self.links_added} link(s) "
            f"{'added' if self.applied else 'to add'}, "
            f"{self.already_linked} already there, "
            f"{len(self.unresolved)} reference(s) not resolved."
        )
        lines = [summary]
        for uid_, message_ in self.unresolved:
            lines.append(f"  Unresolved: {uid_}: {message_}")
        for title_ in self.documents_changed:
            lines.append(
                f"  {'Written' if self.applied else 'Would change'}: {title_}"
            )
        if not self.applied:
            lines.append("Nothing was written.")
        return "\n".join(lines)


def resolve_project_references(
    *,
    traceability_index: Any,
    project_config: ProjectConfig,
    write_document: Callable[[SDocDocument], None],
    apply: bool,
) -> ResolveReport:
    resolver = build_reference_resolver(
        project_config.applicable_documents, traceability_index
    )
    if resolver is None:
        raise StrictDocException(
            "The project names no applicable document "
            "(option applicable_documents)."
        )
    profile = load_project_profile(project_config)
    layout = profile.requirement_table
    if layout is None or len(layout.relation_fields) == 0:
        raise StrictDocException(
            "The Word profile names no relation column (relation_fields)."
        )

    all_uids = {
        node_.reserved_uid
        for document_ in traceability_index.document_tree.document_list
        for node_, _ in SDocDocumentIterator(
            document=document_, node_filter=None
        ).all_content(print_fragments=False)
        if isinstance(node_, SDocNode) and node_.reserved_uid
    }
    report = ResolveReport(applied=apply)
    changed: Dict[str, SDocDocument] = {}
    for document_ in traceability_index.document_tree.document_list:
        # An input document is not changed by this action.
        if is_input_document(document_):
            continue
        iterator = SDocDocumentIterator(document=document_, node_filter=None)
        for node_, _ in iterator.all_content(print_fragments=False):
            if not isinstance(node_, SDocNode) or not node_.reserved_uid:
                continue
            _resolve_node(
                node_, layout.relation_fields, resolver, all_uids, report
            )
            if getattr(node_, "_hierarchy_changed", False):
                changed[document_.title] = document_
                del node_._hierarchy_changed  # type: ignore[attr-defined]
    report.documents_changed = sorted(changed)
    if apply:
        for document_ in changed.values():
            write_document(document_)
    return report


def _resolve_node(
    node: SDocNode,
    relation_fields: List[str],
    resolver: Any,
    all_uids: set,
    report: ResolveReport,
) -> None:
    text = " ; ".join(
        value_.get_text_value()
        for name_ in relation_fields
        for value_ in node.ordered_fields_lookup.get(name_, [])
    )
    if len(text.strip()) == 0:
        return
    resolved = resolver(text, all_uids)
    if len(resolved.uids) == 0 and len(resolved.unresolved) == 0:
        return
    report.requirements_with_references += 1
    for message_ in resolved.unresolved:
        report.unresolved.append((node.reserved_uid, message_))
    existing = {
        relation_.ref_uid
        for relation_ in node.relations
        if isinstance(relation_, ParentReqReference)
    }
    for uid_ in resolved.uids:
        if uid_ == node.reserved_uid:
            continue
        if uid_ in existing:
            report.already_linked += 1
            continue
        report.links_added += 1
        node._hierarchy_changed = True  # type: ignore[attr-defined]
        existing.add(uid_)
        if report.applied:
            node.relations.append(
                ParentReqReference(parent=node, ref_uid=uid_, role=None)
            )
