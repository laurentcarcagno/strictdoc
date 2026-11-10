"""
What the item page shows about a node: the links grouped by relation role and
the lines of the node in its file (for the history).

@relation(SDOC-SRS-213, scope=file)
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.core.traceability_index import TraceabilityIndex
from strictdoc.helpers.file_system import file_open_read_utf8

DIRECTION_PARENT = "parent"
DIRECTION_CHILD = "child"

BLOCK_START_PATTERN = re.compile(r"^\[[A-Z_]+\]\s*$")
NEXT_BLOCK_PATTERN = re.compile(r"^\[\[?/?[A-Z_]+\]\]?\s*$")


@dataclass
class RelationGroup:
    direction: str
    role: str
    nodes: List[SDocNode] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.direction}:{self.role}"


def relation_groups(
    traceability_index: TraceabilityIndex, node: SDocNode
) -> List[RelationGroup]:
    """The parents and the children of a node, one group per role."""
    groups: List[RelationGroup] = []

    def add(direction: str, role: str, related: SDocNode) -> None:
        for group_ in groups:
            if group_.direction == direction and group_.role == role:
                group_.nodes.append(related)
                return
        groups.append(RelationGroup(direction, role, [related]))

    for parent_, role_ in traceability_index.get_parent_relations_with_roles(
        node
    ):
        display_role = traceability_index.get_display_role_for_parent_relation(
            node, parent_, role_
        )
        add(DIRECTION_PARENT, display_role or "Parent", parent_)
    for child_, role_ in traceability_index.get_child_relations_with_roles(
        node
    ):
        display_role = traceability_index.get_display_role_for_child_relation(
            node, child_, role_
        )
        add(DIRECTION_CHILD, display_role or "Child", child_)
    return groups


def block_lines_of_uid(path: str, uid: str) -> Optional[Tuple[int, int]]:
    """
    The first and the last (1-based) line of the block of a file that has the
    UID, or None. A block ends before the next line that opens a block. The
    file is read each time, so an edit in the web interface is taken into
    account.
    """
    with file_open_read_utf8(path) as file_:
        lines = file_.read().splitlines()
    uid_line = f"UID: {uid}"
    for index_, line_ in enumerate(lines):
        if line_.strip() != uid_line:
            continue
        first = index_
        while first > 0 and not BLOCK_START_PATTERN.match(lines[first]):
            first -= 1
        last = index_
        while last + 1 < len(lines) and not NEXT_BLOCK_PATTERN.match(
            lines[last + 1]
        ):
            last += 1
        while last > index_ and lines[last].strip() == "":
            last -= 1
        return first + 1, last + 1
    return None
