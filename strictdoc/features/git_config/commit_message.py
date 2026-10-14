"""
Conventional commit messages built from the diff of a document.

The UIDs of the nodes that changed are found from the line numbers of the diff
(``git diff -U0``) and the new text of the document: a changed line belongs to
the closest block ``[...]`` above it, and the UID is read in that block.
"""

import os
import re
from typing import List, Tuple

MAX_UIDS_IN_MESSAGE = 5
HUNK_PATTERN = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
BLOCK_START_PATTERN = re.compile(r"^\[[A-Z_]+\]\s*$")
UID_LINE_PATTERN = re.compile(r"^UID:\s*(\S+)\s*$")


def _uid_of_block_at(lines: List[str], line_number: int) -> str:
    """The UID of the block that holds the (1-based) line, or an empty string."""
    index = min(line_number, len(lines)) - 1
    while index >= 0 and not BLOCK_START_PATTERN.match(lines[index]):
        index -= 1
    index += 1
    while index < len(lines):
        if BLOCK_START_PATTERN.match(lines[index]):
            return ""
        match = UID_LINE_PATTERN.match(lines[index])
        if match is not None:
            return match.group(1)
        index += 1
    return ""


def changed_uids(
    diff: str, new_content: str
) -> Tuple[List[str], List[str], List[str]]:
    """(UIDs of the changed nodes, UIDs added, UIDs deleted)."""
    lines = new_content.splitlines()
    uids: List[str] = []
    for diff_line in diff.splitlines():
        match = HUNK_PATTERN.match(diff_line)
        if match is None:
            continue
        start = int(match.group(1))
        count = int(match.group(2)) if match.group(2) is not None else 1
        for line_number in range(start, start + max(count, 1)):
            uid = _uid_of_block_at(lines, line_number)
            if uid != "" and uid not in uids:
                uids.append(uid)

    added: List[str] = []
    deleted: List[str] = []
    for diff_line in diff.splitlines():
        if diff_line.startswith("+") and not diff_line.startswith("+++"):
            match_uid = UID_LINE_PATTERN.match(diff_line[1:])
            if match_uid is not None:
                added.append(match_uid.group(1))
        elif diff_line.startswith("-") and not diff_line.startswith("---"):
            match_uid = UID_LINE_PATTERN.match(diff_line[1:])
            if match_uid is not None:
                deleted.append(match_uid.group(1))
    both = set(added) & set(deleted)
    added = [uid for uid in added if uid not in both]
    deleted = [uid for uid in deleted if uid not in both]
    uids = [uid for uid in uids if uid not in deleted]
    return uids, added, deleted


def _list(uids: List[str]) -> str:
    shown = uids[:MAX_UIDS_IN_MESSAGE]
    text = ", ".join(shown)
    if len(uids) > len(shown):
        text += f", and {len(uids) - len(shown)} more"
    return f"[{text}]"


def document_message(path: str, diff: str, new_content: str) -> str:
    uids, added, deleted = changed_uids(diff, new_content)
    for verb, group in (("add", added), ("delete", deleted)):
        if len(group) > 0:
            noun = "requirement" if len(group) == 1 else "requirements"
            return f"feat(doc): {verb} {noun} {_list(group)}"
    if len(uids) > 0:
        noun = "requirement" if len(uids) == 1 else "requirements"
        return f"feat(doc): update {noun} {_list(uids)}"
    return f"feat(doc): update {os.path.basename(path)}"


def asset_message(names: List[str]) -> str:
    noun = "asset" if len(names) == 1 else "assets"
    return f"feat(doc): add {noun} {', '.join(names)}"
