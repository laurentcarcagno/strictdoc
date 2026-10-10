"""
Suspect links: a child node answers a parent node as it was when someone
reviewed the link. When the parent changes afterwards, the link is suspect
until an author clears it.

The reviewed state is a baseline file, trace_baseline.json, at the project
root: one line per link, the SHA-1 of the parent content that was reviewed.
The baseline is not part of the nodes, so a parent edit does not touch its
children and a merge conflict stays on one line.
"""

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
)

from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.core.document_iterator import SDocDocumentIterator

if TYPE_CHECKING:
    from strictdoc.core.project_config import ProjectConfig

BASELINE_FILE_NAME = "trace_baseline.json"
DEFAULT_SUSPECT_FIELDS: Tuple[str, ...] = ("TITLE", "STATEMENT")
_SEPARATOR = " < "


class BaselineError(ValueError):
    pass


@dataclass(frozen=True)
class SuspectLink:
    child: SDocNode
    parent: SDocNode


def uid_of(node: SDocNode) -> str:
    """The UID of a node that is part of a link (iter_links only gives those)."""
    uid = node.reserved_uid
    assert uid, node
    return uid


def content_hash(node: SDocNode, fields: Sequence[str]) -> str:
    """The SHA-1 of the fields of a node that count as its reviewed content."""
    digest = hashlib.sha1()
    for field_name in fields:
        values = node.ordered_fields_lookup.get(field_name, [])
        text = "\n".join(value_.get_text_value() for value_ in values)
        digest.update(f"{field_name}\0{text}\0".encode())
    return digest.hexdigest()


def link_key(child_uid: str, parent_uid: str) -> str:
    if _SEPARATOR in child_uid or _SEPARATOR in parent_uid:
        raise BaselineError(
            f"The UIDs '{child_uid}' and '{parent_uid}' cannot be recorded "
            f"in the baseline: they contain '{_SEPARATOR}'."
        )
    return f"{child_uid}{_SEPARATOR}{parent_uid}"


class Baseline:
    def __init__(self, entries: Optional[Dict[str, str]] = None) -> None:
        self.entries: Dict[str, str] = dict(entries or {})

    @staticmethod
    def load(path: str) -> "Baseline":
        if not os.path.isfile(path):
            return Baseline()
        try:
            with open(path, encoding="utf-8") as file_:
                data: Any = json.load(file_)
        except (OSError, json.JSONDecodeError) as exception_:
            raise BaselineError(
                f"The baseline {path} cannot be read: {exception_}"
            ) from exception_
        if not isinstance(data, dict) or not all(
            isinstance(key_, str) and isinstance(value_, str)
            for key_, value_ in data.items()
        ):
            raise BaselineError(
                f"The baseline {path} must be an object of text values."
            )
        return Baseline(data)

    def to_text(self) -> str:
        """Sorted, one line per link, so that a diff and a merge stay local."""
        if len(self.entries) == 0:
            return "{}\n"
        lines = [
            f"{json.dumps(key_)}: {json.dumps(self.entries[key_])}"
            for key_ in sorted(self.entries)
        ]
        return "{\n" + ",\n".join(lines) + "\n}\n"

    def save(self, path: str) -> None:
        directory = os.path.dirname(os.path.abspath(path))
        file_descriptor, temporary = tempfile.mkstemp(
            dir=directory, prefix=".trace_baseline", suffix=".tmp"
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as file_:
                file_.write(self.to_text())
            os.replace(temporary, path)
        except BaseException:
            if os.path.exists(temporary):
                os.unlink(temporary)
            raise


def iter_links(traceability_index: Any) -> Iterator[Tuple[SDocNode, SDocNode]]:
    """(child, parent) for every Parent relation between nodes with a UID."""
    for document_ in traceability_index.document_tree.document_list:
        iterator = SDocDocumentIterator(document=document_, node_filter=None)
        for node_, _ in iterator.all_content(print_fragments=False):
            if not isinstance(node_, SDocNode) or not node_.reserved_uid:
                continue
            for parent_ in traceability_index.get_parent_requirements(node_):
                if parent_.reserved_uid:
                    yield node_, parent_


def suspect_links(
    traceability_index: Any, baseline: Baseline, fields: Sequence[str]
) -> List[SuspectLink]:
    """
    The links whose parent differs from the reviewed state. A link that has
    no entry is not suspect: nobody reviewed it yet (see sync_new_links).
    """
    result: List[SuspectLink] = []
    for child, parent in iter_links(traceability_index):
        reviewed = baseline.entries.get(link_key(uid_of(child), uid_of(parent)))
        if reviewed is not None and reviewed != content_hash(parent, fields):
            result.append(SuspectLink(child=child, parent=parent))
    return result


def sync_new_links(
    traceability_index: Any, baseline: Baseline, fields: Sequence[str]
) -> bool:
    """
    A new link is reviewed by whoever creates it: it gets its entry at once.
    The entry of a link that no longer exists is dropped. True if the baseline
    changed.
    """
    changed = False
    current = set()
    for child, parent in iter_links(traceability_index):
        key = link_key(uid_of(child), uid_of(parent))
        current.add(key)
        if key not in baseline.entries:
            baseline.entries[key] = content_hash(parent, fields)
            changed = True
    for key in [key_ for key_ in baseline.entries if key_ not in current]:
        del baseline.entries[key]
        changed = True
    return changed


def clear_link(
    baseline: Baseline,
    child: SDocNode,
    parent: SDocNode,
    fields: Sequence[str],
) -> None:
    """The review of a suspect link is done: take the parent as it is now."""
    baseline.entries[link_key(uid_of(child), uid_of(parent))] = content_hash(
        parent, fields
    )


def baseline_all(
    traceability_index: Any, baseline: Baseline, fields: Sequence[str]
) -> int:
    """Take every link as reviewed. Returns the number of links."""
    baseline.entries.clear()
    count = 0
    for child, parent in iter_links(traceability_index):
        baseline.entries[link_key(uid_of(child), uid_of(parent))] = (
            content_hash(parent, fields)
        )
        count += 1
    return count


def impact_of(
    suspects: Sequence[SuspectLink], parent_uids: Sequence[str]
) -> Dict[str, List[str]]:
    """The children that are suspect because of the given parents."""
    wanted = set(parent_uids)
    impact: Dict[str, List[str]] = {}
    for link_ in suspects:
        if uid_of(link_.parent) in wanted:
            impact.setdefault(uid_of(link_.parent), []).append(
                uid_of(link_.child)
            )
    return {key_: sorted(value_) for key_, value_ in impact.items()}


_CACHE: Dict[str, Tuple[float, Baseline]] = {}


def load_cached(path: str) -> Baseline:
    """The baseline of a path, read again only when the file changed."""
    try:
        modified = os.stat(path).st_mtime
    except OSError:
        return Baseline()
    cached = _CACHE.get(path)
    if cached is not None and cached[0] == modified:
        return cached[1]
    baseline = Baseline.load(path)
    _CACHE[path] = (modified, baseline)
    return baseline


def baseline_path(project_config: "ProjectConfig") -> str:
    assert project_config.input_paths is not None
    return os.path.join(project_config.input_paths[0], BASELINE_FILE_NAME)


def suspect_fields(project_config: "ProjectConfig") -> Tuple[str, ...]:
    return tuple(project_config.suspect_fields) or DEFAULT_SUSPECT_FIELDS


def suspect_parents(
    traceability_index: Any, project_config: "ProjectConfig", node: SDocNode
) -> List[str]:
    """The UIDs of the parents of a node that changed since the link was reviewed."""
    if not project_config.suspect_links or not node.reserved_uid:
        return []
    try:
        baseline = load_cached(baseline_path(project_config))
    except BaselineError:
        return []
    if len(baseline.entries) == 0:
        return []
    fields = suspect_fields(project_config)
    return sorted(
        uid_of(link_.parent)
        for link_ in suspect_links(traceability_index, baseline, fields)
        if link_.child is node
    )
