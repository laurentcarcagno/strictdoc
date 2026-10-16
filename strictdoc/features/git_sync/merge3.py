"""
A three-way merge of documents, node by node.

`merge3(base, local, server)` cuts the three texts into blocks
(blocks.py) and merges the sequences like diff3 does with lines. The result
is a list of regions, in the order of the merged document:

  same      the three agree, or both sides made the same change
  local     only the local side changed: the merged text is the local one
  server    only the server side changed: the merged text is the server one
  conflict  both sides changed the same blocks in different ways

The "local" side is the repository of the project, the "server" side is what
the remote has (origin). A conflict has no merged text until a choice is made.
"""

import difflib
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from strictdoc.features.git_sync.blocks import Block, split_blocks

SAME = "same"
LOCAL = "local"
SERVER = "server"
CONFLICT = "conflict"


@dataclass
class Region:
    kind: str
    base: List[Block]
    local: List[Block]
    server: List[Block]

    @staticmethod
    def _text(blocks: Sequence[Block]) -> str:
        return "".join(block_.text for block_ in blocks)

    @property
    def base_text(self) -> str:
        return self._text(self.base)

    @property
    def local_text(self) -> str:
        return self._text(self.local)

    @property
    def server_text(self) -> str:
        return self._text(self.server)

    def merged_text(self) -> Optional[str]:
        """The text of the region, None for a conflict."""
        if self.kind == SERVER:
            return self.server_text
        if self.kind in (LOCAL, SAME):
            return self.local_text
        return None

    def choice_text(self, choice: str) -> str:
        """The text for a choice on a conflict: local, server or both."""
        if choice == "server":
            return self.server_text
        if choice == "both":
            return self.local_text + self.server_text
        return self.local_text


def _texts(blocks: Sequence[Block]) -> List[str]:
    return [block_.text for block_ in blocks]


def _matches(base_keys: List[str], other_keys: List[str]) -> Dict[int, int]:
    """For each block of the base that is found in the other side: where."""
    matcher = difflib.SequenceMatcher(
        None, base_keys, other_keys, autojunk=False
    )
    found: Dict[int, int] = {}
    for tag_, i1, i2, j1, _j2 in matcher.get_opcodes():
        if tag_ == "equal":
            for offset_ in range(i2 - i1):
                found[i1 + offset_] = j1 + offset_
    return found


def _chunk_region(
    base: List[Block], local: List[Block], server: List[Block]
) -> Optional[Region]:
    """The region of a stretch between two anchors; None when it is empty."""
    if not base and not local and not server:
        return None
    base_t, local_t, server_t = _texts(base), _texts(local), _texts(server)
    if local_t == server_t:
        kind = SAME
    elif local_t == base_t:
        kind = SERVER
    elif server_t == base_t:
        kind = LOCAL
    else:
        kind = CONFLICT
    return Region(kind, base, local, server)


def _anchor_region(base: Block, local: Block, server: Block) -> Region:
    """A block that the three versions have: changed by one side, or not."""
    if local.text == server.text:
        kind = SAME
    elif local.text == base.text:
        kind = SERVER
    elif server.text == base.text:
        kind = LOCAL
    else:
        kind = CONFLICT
    return Region(kind, [base], [local], [server])


def _without_base(local: List[Block], server: List[Block]) -> List[Region]:
    """Both sides added the file: only what they share is not a conflict."""
    matcher = difflib.SequenceMatcher(
        None,
        [block_.key for block_ in local],
        [block_.key for block_ in server],
        autojunk=False,
    )
    regions: List[Region] = []
    for tag_, i1, i2, j1, j2 in matcher.get_opcodes():
        local_part, server_part = local[i1:i2], server[j1:j2]
        if tag_ == "equal":
            for offset_ in range(i2 - i1):
                same = local_part[offset_].text == server_part[offset_].text
                regions.append(
                    Region(
                        SAME if same else CONFLICT,
                        [],
                        [local_part[offset_]],
                        [server_part[offset_]],
                    )
                )
        else:
            regions.append(Region(CONFLICT, [], local_part, server_part))
    return regions


def merge_blocks(
    base: List[Block], local: List[Block], server: List[Block]
) -> List[Region]:
    if not base:
        return _without_base(local, server)
    base_keys = [block_.key for block_ in base]
    in_local = _matches(base_keys, [block_.key for block_ in local])
    in_server = _matches(base_keys, [block_.key for block_ in server])
    anchors: List[Tuple[int, int, int]] = [
        (i, in_local[i], in_server[i])
        for i in sorted(set(in_local) & set(in_server))
    ]
    regions: List[Region] = []
    previous = (-1, -1, -1)
    for anchor in anchors + [(len(base), len(local), len(server))]:
        between = _chunk_region(
            base[previous[0] + 1 : anchor[0]],
            local[previous[1] + 1 : anchor[1]],
            server[previous[2] + 1 : anchor[2]],
        )
        if between is not None:
            regions.append(between)
        if anchor[0] < len(base):
            regions.append(
                _anchor_region(
                    base[anchor[0]], local[anchor[1]], server[anchor[2]]
                )
            )
        previous = anchor
    return regions


def merge3(base_text: str, local_text: str, server_text: str) -> List[Region]:
    return merge_blocks(
        split_blocks(base_text),
        split_blocks(local_text),
        split_blocks(server_text),
    )


def conflict_indexes(regions: Sequence[Region]) -> List[int]:
    return [
        i_ for i_, region_ in enumerate(regions) if region_.kind == CONFLICT
    ]


def assemble(regions: Sequence[Region], texts: Dict[int, str]) -> str:
    """
    The merged document. `texts` gives the text of each conflict, by the index
    of its region; a missing one raises KeyError.
    """
    parts: List[str] = []
    for index_, region_ in enumerate(regions):
        merged = region_.merged_text()
        parts.append(texts[index_] if merged is None else merged)
    return "".join(parts)
