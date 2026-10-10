"""
The relation policy: checks a Parent or Child relation against the levels of
the project.
"""

from typing import TYPE_CHECKING, Optional

from strictdoc.features.hierarchy.levels import (
    document_kind,
    relation_violation,
)

if TYPE_CHECKING:
    from strictdoc.backend.sdoc.models.document import SDocDocument
    from strictdoc.core.project_config import ProjectConfig
    from strictdoc.core.traceability_index import TraceabilityIndex


def policy_message(
    *,
    config: "ProjectConfig",
    traceability_index: "TraceabilityIndex",
    node_document: "SDocDocument",
    target_uid: str,
    relation_type: str,
) -> Optional[str]:
    """
    Why a node of `node_document` may not have this relation to the node
    `target_uid`, or None. The relation types are "Parent" (the target is the
    parent of the node) and "Child" (the target is a child of the node); any
    other type is not a hierarchy matter.
    """
    if config.relation_policy == "off" or relation_type not in (
        "Parent",
        "Child",
    ):
        return None
    target = traceability_index.get_node_by_uid_weak2(target_uid)
    if target is None:
        return None
    target_document = target.get_parent_or_including_document()
    node_kind = document_kind(node_document)
    target_kind = document_kind(target_document)
    if relation_type == "Parent":
        return relation_violation(
            config.hierarchy_levels, node_kind, target_kind
        )
    return relation_violation(config.hierarchy_levels, target_kind, node_kind)
