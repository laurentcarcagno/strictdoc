"""
Numbers of the hierarchy screen: per level, how many documents and nodes, how
many nodes answer a parent in an allowed level (coverage), which nodes are
orphans, and which nodes nobody answers.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.core.document_iterator import SDocDocumentIterator
from strictdoc.features.hierarchy.levels import Level, document_kind


@dataclass
class LevelStats:
    level: Level
    documents: List[str] = field(default_factory=list)
    nodes: List[SDocNode] = field(default_factory=list)
    # Nodes with at least one parent in a level that the level allows.
    answering: List[SDocNode] = field(default_factory=list)
    # Nodes of a level that has allowed parents but no parent at all.
    orphans: List[SDocNode] = field(default_factory=list)
    # Nodes of a level that some other level answers, that nobody answers.
    unanswered: List[SDocNode] = field(default_factory=list)
    suspect: int = 0

    @property
    def coverage_percent(self) -> int:
        if len(self.level.parents) == 0 or len(self.nodes) == 0:
            return 100
        return round(100 * len(self.answering) / len(self.nodes))


@dataclass
class HierarchyStats:
    levels: List[LevelStats]
    # Documents whose kind is not one of the levels, or that have none.
    unclassified_documents: List[str]


def compute_hierarchy_stats(
    traceability_index: Any,
    levels: Dict[str, Level],
    suspect_children: Sequence[str] = (),
) -> HierarchyStats:
    by_level = {
        name_: LevelStats(level=level_) for name_, level_ in levels.items()
    }
    answered_levels = {
        parent_.strip().lower()
        for level_ in levels.values()
        for parent_ in level_.parents
    }
    unclassified: List[str] = []
    for document_ in traceability_index.document_tree.document_list:
        kind = document_kind(document_)
        if kind not in by_level:
            unclassified.append(document_.title)
            continue
        stats = by_level[kind]
        stats.documents.append(document_.title)
        iterator = SDocDocumentIterator(document=document_, node_filter=None)
        for node_, _ in iterator.all_content(print_fragments=False):
            if not isinstance(node_, SDocNode) or not node_.reserved_uid:
                continue
            if node_.node_type in ("SECTION", "TEXT"):
                continue
            stats.nodes.append(node_)
            parents = traceability_index.get_parent_requirements(node_)
            allowed = {name_.strip().lower() for name_ in stats.level.parents}
            if allowed:
                if len(parents) == 0:
                    stats.orphans.append(node_)
                elif any(
                    document_kind(parent_.get_parent_or_including_document())
                    in allowed
                    for parent_ in parents
                ):
                    stats.answering.append(node_)
            if (
                kind in answered_levels
                and len(traceability_index.get_children_requirements(node_))
                == 0
            ):
                stats.unanswered.append(node_)
            if node_.reserved_uid in suspect_children:
                stats.suspect += 1
    return HierarchyStats(
        levels=list(by_level.values()), unclassified_documents=unclassified
    )
