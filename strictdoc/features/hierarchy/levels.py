"""
Levels of the document hierarchy and the kind of a document.

A document declares its kind in its custom metadata (``KIND: input``), the
project declares the levels and which levels a node may point its parent
relations to. A document without a kind is not constrained.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence

if TYPE_CHECKING:
    from strictdoc.backend.sdoc.models.document import SDocDocument

KIND_KEY = "KIND"
INPUT_KIND = "input"
RELATION_POLICIES = ("off", "warn", "enforce")


@dataclass(frozen=True)
class Level:
    name: str
    label: str = ""
    # The levels that a node of this level may point its Parent relations to.
    parents: Sequence[str] = field(default_factory=tuple)

    @property
    def title(self) -> str:
        return self.label or self.name


@dataclass(frozen=True)
class InputInfo:
    """What the metadata of an input document says about it."""

    title: str
    issuer: str
    reference: str
    revision: str
    version: str
    date: str


def validate_hierarchy(levels: Sequence[Level]) -> Dict[str, Level]:
    """
    The levels by name. Raises ValueError for an empty or duplicate name, a
    level that is its own parent, an unknown parent, or a cycle.
    """
    by_name: Dict[str, Level] = {}
    for level_ in levels:
        if not isinstance(level_, Level):
            raise ValueError(f"'{level_}' is not a Level.")
        name = level_.name.strip().lower()
        if len(name) == 0:
            raise ValueError("A level has an empty name.")
        if name in by_name:
            raise ValueError(f"The level '{name}' is declared twice.")
        by_name[name] = level_
    for name, level_ in by_name.items():
        for parent_ in level_.parents:
            parent_name = parent_.strip().lower()
            if parent_name == name:
                raise ValueError(f"The level '{name}' is its own parent.")
            if parent_name not in by_name:
                raise ValueError(
                    f"The level '{name}' has an unknown parent '{parent_}'."
                )
    # A cycle: walk the parents with the path of the current branch.
    done: set = set()

    def visit(name: str, path: List[str]) -> None:
        if name in done:
            return
        if name in path:
            cycle = " -> ".join([*path[path.index(name) :], name])
            raise ValueError(f"The levels form a cycle: {cycle}.")
        for parent_ in by_name[name].parents:
            visit(parent_.strip().lower(), [*path, name])
        done.add(name)

    for name in by_name:
        visit(name, [])
    return by_name


def document_metadata(document: "SDocDocument") -> Dict[str, str]:
    """The custom metadata of a document, keys in upper case."""
    config = document.config
    if (
        config is None
        or config.custom_metadata is None
        or config.custom_metadata.entries is None
    ):
        return {}
    return {
        entry.key.upper(): entry.get_text_value().strip()
        for entry in config.custom_metadata.entries
        if entry.key is not None
    }


def document_kind(document: "SDocDocument") -> Optional[str]:
    kind = document_metadata(document).get(KIND_KEY, "").lower()
    return kind or None


def is_input_document(document: "SDocDocument") -> bool:
    return document_kind(document) == INPUT_KIND


def input_info(document: "SDocDocument") -> InputInfo:
    metadata = document_metadata(document)
    config = document.config
    return InputInfo(
        title=document.title,
        issuer=metadata.get("ISSUER", ""),
        reference=metadata.get("REFERENCE", ""),
        revision=metadata.get("REVISION", ""),
        version=(config.version or "") if config is not None else "",
        date=(config.date or "") if config is not None else "",
    )


def relation_violation(
    levels: Dict[str, Level],
    child_kind: Optional[str],
    parent_kind: Optional[str],
) -> Optional[str]:
    """
    A message when a node of the child kind may not point a Parent relation to
    a node of the parent kind, else None. A document without a kind, or with a
    kind that the project does not declare, is not constrained.
    """
    if child_kind is None or parent_kind is None:
        return None
    child_level = levels.get(child_kind)
    if child_level is None or parent_kind not in levels:
        return None
    allowed = {name_.strip().lower() for name_ in child_level.parents}
    if parent_kind in allowed:
        return None
    allowed_text = ", ".join(sorted(allowed)) or "none"
    return (
        f"A '{child_kind}' node may not have a parent in a '{parent_kind}' "
        f"document (allowed: {allowed_text})."
    )
