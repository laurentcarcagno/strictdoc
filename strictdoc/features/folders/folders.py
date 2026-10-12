"""
Folders of a project, to organise its documents.

StrictDoc shows a folder in the project tree only when a document is in it. A
folder that a person creates is empty at first, so it carries a marker file
(``.sdoc-folder``): the tree shows the folders that have one. The marker is not a
document and is never read as one (it has no document extension).
"""

import os
import re
from typing import Iterator, List

from strictdoc.core.file_system.file_tree import Folder
from strictdoc.helpers.exception import StrictDocException

MARKER = ".sdoc-folder"

_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_RESERVED = ("_assets", "output", "Output", "word")
MAX_DEPTH = 8


def has_folder_marker(folder: Folder) -> bool:
    return os.path.isfile(os.path.join(folder.full_path, MARKER))


def clean_folder_path(text: str) -> str:
    """
    The relative path of a new folder, with "/" and no slash at either end.
    Raises StrictDocException with a message for the person.
    """
    path = text.strip().replace("\\", "/").strip("/")
    if len(path) == 0:
        raise StrictDocException("The folder name must not be empty.")
    segments = [segment_ for segment_ in path.split("/")]
    if len(segments) > MAX_DEPTH:
        raise StrictDocException(f"At most {MAX_DEPTH} levels of folders.")
    for segment_ in segments:
        if segment_ in _RESERVED:
            raise StrictDocException(f"'{segment_}' is a reserved name.")
        if _SEGMENT.match(segment_) is None or segment_.endswith("."):
            raise StrictDocException(
                f"Invalid folder name '{segment_}': use letters, digits, "
                "'_', '-' and '.', starting with a letter or a digit, and "
                "'/' between levels."
            )
    return "/".join(segments)


def create_folder(root: str, relative_path: str) -> List[str]:
    """
    Creates the folder (and the missing levels above it), each with the
    marker. Returns the relative paths of the folders that did not exist.
    Raises StrictDocException when it exists, or when a file is in the way.
    """
    path = clean_folder_path(relative_path)
    real_root = os.path.realpath(root)
    created: List[str] = []
    current = real_root
    parts: List[str] = []
    for segment_ in path.split("/"):
        parts.append(segment_)
        current = os.path.join(current, segment_)
        if os.path.islink(current) or (
            os.path.exists(current) and not os.path.isdir(current)
        ):
            raise StrictDocException(
                f"'{'/'.join(parts)}' exists and is not a folder."
            )
        if not os.path.isdir(current):
            os.mkdir(current)
            created.append("/".join(parts))
    if len(created) == 0:
        raise StrictDocException(f"The folder '{path}' already exists.")
    for relative_ in created:
        marker = os.path.join(real_root, relative_, MARKER)
        with open(marker, "w", encoding="utf8"):
            pass
    return created


def folder_paths(folder: Folder) -> Iterator[str]:
    """
    The relative paths of the folders below a folder, that can hold
    documents (without the reserved ones).
    """
    for sub_ in folder.subfolder_trees:
        name = sub_.folder_name
        if name in _RESERVED or name.startswith((".", "_")):
            continue
        yield sub_.rel_path.rstrip("/")
        yield from folder_paths(sub_)
