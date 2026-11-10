"""
The simple search: a UID that is typed exactly opens the item, and three
facets (kind, status, links) build a query of the query language, so that a
user does not have to write one.

@relation(SDOC-SRS-214, scope=file)
"""

from dataclasses import dataclass
from typing import List, Optional

from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.core.document_tree import DocumentTree
from strictdoc.core.traceability_index import TraceabilityIndex
from strictdoc.helpers.cast import assert_cast

KIND_REQUIREMENT = "requirement"
KIND_SECTION = "section"
KINDS = (KIND_REQUIREMENT, KIND_SECTION)

LINKS_WITH_PARENT = "with_parent"
LINKS_WITHOUT_PARENT = "without_parent"
LINKS = (LINKS_WITH_PARENT, LINKS_WITHOUT_PARENT)


@dataclass(frozen=True)
class SearchFacets:
    kind: str = ""
    status: str = ""
    links: str = ""

    def is_active(self) -> bool:
        return len(self.kind) > 0 or len(self.status) > 0 or len(self.links) > 0


def build_facet_query(facets: SearchFacets) -> str:
    """
    The query of the facets, or an empty string when no facet is chosen. An
    unknown value of a facet is ignored.
    """
    conditions: List[str] = []
    if facets.kind == KIND_REQUIREMENT:
        conditions.append("node.is_requirement")
    elif facets.kind == KIND_SECTION:
        conditions.append("node.is_section")
    if len(facets.status) > 0 and '"' not in facets.status:
        conditions.append(f'node["STATUS"] == "{facets.status}"')
    if facets.links == LINKS_WITH_PARENT:
        conditions.append("node.has_parent_requirements")
    elif facets.links == LINKS_WITHOUT_PARENT:
        conditions.append("not node.has_parent_requirements")
    if len(conditions) == 0:
        return ""
    if len(conditions) == 1:
        return conditions[0]
    return "(" + " and ".join(conditions) + ")"


def find_item_by_exact_uid(
    traceability_index: TraceabilityIndex, text: str
) -> Optional[SDocNode]:
    """The item whose UID is the whole text, or None."""
    uid = text.strip()
    if len(uid) == 0 or len(uid.split()) != 1:
        return None
    node = traceability_index.get_linkable_node_by_uid_weak(uid)
    if isinstance(node, SDocNode) and node.is_normative_node():
        return node
    return None


def collect_statuses(traceability_index: TraceabilityIndex) -> List[str]:
    """The values of the STATUS field that the nodes of the project use."""
    statuses = set()
    document_tree = assert_cast(traceability_index.document_tree, DocumentTree)
    for document_ in document_tree.document_list:
        iterator = traceability_index.get_document_iterator(document_)
        for node_, _ in iterator.all_content(print_fragments=False):
            if not isinstance(node_, SDocNode):
                continue
            status = node_.get_meta_field_value_by_title("STATUS")
            if status is not None and len(status) > 0:
                statuses.add(status)
    return sorted(statuses)
