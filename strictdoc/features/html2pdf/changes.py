"""
The nodes of a document that changed since its last tagged version, for the
change bars of the PDF export.

The last version is the latest version tag (A1, A2, B... see
features/git_config/versioning.py) of the repository that holds the document.
The document of that tag is read from git and its nodes are compared with the
nodes of the current document, field by field. Comments are not compared: the
PDF has none.
"""

import os
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from git import GitCommandError, InvalidGitRepositoryError, Repo

from strictdoc.backend.sdoc.reader import SDReader
from strictdoc.features.git_config.versioning import latest_valid_tag
from strictdoc.helpers.exception import StrictDocException

_IGNORED_FIELDS = ("MID", "COMMENT")

Signature = Tuple[Tuple[str, str], ...]


def _walk(elements: List[Any]) -> Iterator[Any]:
    """The nodes and sections below a list of elements, in order."""
    for element_ in elements:
        yield element_
        contents = getattr(element_, "section_contents", None)
        if contents:
            yield from _walk(list(contents))


def _fields(node: Any) -> Dict[str, List[Any]]:
    return getattr(node, "ordered_fields_lookup", {}) or {}


def _signature(node: Any) -> Signature:
    """The text of the fields of a node, without the ones that are not printed."""
    parts: List[Tuple[str, str]] = [("@type", str(node.node_type))]
    for name_, fields_ in _fields(node).items():
        if name_ in _IGNORED_FIELDS:
            continue
        parts.append((name_, "\n".join(f_.get_text_value() for f_ in fields_)))
    return tuple(parts)


def _identity(node: Any) -> Optional[str]:
    """What tells a node from the others across versions, if it has it."""
    fields = _fields(node)
    for name_ in ("MID", "UID"):
        if name_ in fields and fields[name_]:
            return f"{name_}:{fields[name_][0].get_text_value().strip()}"
    return None


def _old_document_text(path: str) -> Optional[str]:
    try:
        repo = Repo(path, search_parent_directories=True)
    except (InvalidGitRepositoryError, OSError):
        return None
    working_dir = repo.working_tree_dir
    if working_dir is None:
        return None
    tag = latest_valid_tag(tag_.name for tag_ in repo.tags)
    if tag == "":
        return None
    relative = os.path.relpath(
        os.path.realpath(path), os.path.realpath(working_dir)
    )
    try:
        text: str = repo.git.show(f"{tag}:{relative.replace(os.sep, '/')}")
    except GitCommandError:
        # The document did not exist at that version: all of it is new.
        return ""
    # git strips the last line break, which the SDoc grammar wants.
    return text + "\n"


def changed_nodes_since_last_tag(
    document: Any, path: Optional[str]
) -> Optional[Set[int]]:
    """
    The `id()` of the nodes of the document that are new or modified since the
    latest version tag; None when there is nothing to compare with (no
    repository, no tag).
    """
    if not path or not os.path.isfile(path):
        return None
    old_text = _old_document_text(path)
    if old_text is None:
        return None

    old_by_identity: Dict[str, Signature] = {}
    old_signatures: Set[Signature] = set()
    if old_text != "":
        try:
            old_document = SDReader.read(old_text, file_path=path)
        except StrictDocException:
            return None
        for node_ in _walk(list(old_document.section_contents)):
            signature = _signature(node_)
            old_signatures.add(signature)
            identity = _identity(node_)
            if identity is not None:
                old_by_identity[identity] = signature

    changed: Set[int] = set()
    for node_ in _walk(list(document.section_contents)):
        if not hasattr(node_, "node_type"):
            continue
        # Nodes of an included document are compared with their own file.
        owner = node_.get_document() if hasattr(node_, "get_document") else None
        if owner is not None and owner is not document:
            continue
        signature = _signature(node_)
        identity = _identity(node_)
        if identity is not None and identity in old_by_identity:
            if old_by_identity[identity] != signature:
                changed.add(id(node_))
        elif signature not in old_signatures:
            changed.add(id(node_))
    return changed
