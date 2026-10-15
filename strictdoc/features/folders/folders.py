"""
Folders of a project, to organise its documents.

StrictDoc shows a folder in the project tree only when a document is in it. A
folder that a person creates is empty at first, so it carries a marker file
(``.sdoc-folder``): the tree shows the folders that have one. The marker is not a
document and is never read as one (it has no document extension).
"""

import os
import re
from typing import Dict, Iterator, List

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


#
# Rename, move and delete.
#
# Paths are relative to the root of the project ("specs/system",
# "specs/a.sdoc"); "" is the root itself.
#

_INCLUDE = re.compile(r"\[DOCUMENT_FROM_FILE\]\s*\nFILE: *(.+)")
_IMPORT = re.compile(r"^IMPORT_FROM_FILE: *([^@\s].*)$", re.MULTILINE)
DOCUMENT_EXTENSION = ".sdoc"


def _inside(root: str, relative_path: str, what: str) -> str:
    """
    The absolute path of a relative path of the project, which must exist and
    must not go out of the project (no "..", no link).
    """
    real_root = os.path.realpath(root)
    path = relative_path.strip().replace("\\", "/").strip("/")
    segments = [] if path == "" else path.split("/")
    current = real_root
    for segment_ in segments:
        if segment_ in ("", ".", "..") or "\0" in segment_:
            raise StrictDocException(f"Invalid {what} '{relative_path}'.")
        current = os.path.join(current, segment_)
        if os.path.islink(current):
            raise StrictDocException(f"Invalid {what} '{relative_path}'.")
    if not os.path.exists(current):
        raise StrictDocException(f"The {what} '{path}' does not exist.")
    return current


def _clean_name(name: str) -> str:
    text = name.strip()
    if "/" in text or "\\" in text:
        raise StrictDocException(
            "A folder name has no '/': use the move to change its place."
        )
    return clean_folder_path(text)


def _documents_under(root: str, relative_path: str) -> List[str]:
    """The relative paths of the documents in a folder, at any depth."""
    base = os.path.join(os.path.realpath(root), relative_path)
    found: List[str] = []
    for folder_, dirs_, files_ in os.walk(base):
        dirs_[:] = [
            dir_
            for dir_ in dirs_
            if dir_ not in _RESERVED and not dir_.startswith((".", "_"))
        ]
        for file_ in files_:
            if file_.endswith(DOCUMENT_EXTENSION):
                found.append(
                    os.path.relpath(
                        os.path.join(folder_, file_), os.path.realpath(root)
                    ).replace(os.sep, "/")
                )
    return sorted(found)


def _dependencies(root: str) -> Dict[str, List[str]]:
    """
    The files that each document includes or imports by a relative path (the
    paths are relative to the root of the project).
    """
    found: Dict[str, List[str]] = {}
    real_root = os.path.realpath(root)
    for document_ in _documents_under(root, ""):
        try:
            with open(
                os.path.join(real_root, document_), encoding="utf8"
            ) as file_:
                text = file_.read()
        except (OSError, UnicodeDecodeError):
            continue
        targets = _INCLUDE.findall(text) + _IMPORT.findall(text)
        directory = os.path.dirname(document_)
        found[document_] = [
            os.path.normpath(os.path.join(directory, target_.strip())).replace(
                os.sep, "/"
            )
            for target_ in targets
        ]
    return found


def _check_paths_still_resolve(root: str, moving: Dict[str, str]) -> None:
    """
    Documents include and import each other by relative paths. A move is
    refused when it changes one of those paths (when only one side moves).
    `moving` maps the old relative path of each moved document to the new one.
    """
    broken: List[str] = []
    for document_, targets_ in _dependencies(root).items():
        for target_ in targets_:
            new_document = moving.get(document_, document_)
            new_target = moving.get(target_, target_)
            if os.path.relpath(
                new_target, os.path.dirname(new_document) or "."
            ) != os.path.relpath(target_, os.path.dirname(document_) or "."):
                broken.append(f"{document_} -> {target_}")
    if broken:
        raise StrictDocException(
            "The paths of these includes or imports would break: "
            + ", ".join(broken)
            + "."
        )


def _destination(root: str, destination: str, name: str) -> str:
    """The relative path of `name` in the destination folder (checked)."""
    folder = _inside(root, destination, "destination folder")
    if not os.path.isdir(folder):
        raise StrictDocException(
            f"The destination '{destination}' is not a folder."
        )
    return "/".join(part_ for part_ in (destination.strip("/"), name) if part_)


def _keep_folder(root: str, relative_folder: str) -> None:
    """A folder that loses its last document stays in the tree."""
    if relative_folder == "":
        return
    marker = os.path.join(os.path.realpath(root), relative_folder, MARKER)
    if not os.path.exists(marker):
        with open(marker, "w", encoding="utf8"):
            pass


def _move_folder_to(root: str, relative_path: str, new_relative: str) -> str:
    source = _inside(root, relative_path, "folder")
    if not os.path.isdir(source):
        raise StrictDocException(f"'{relative_path}' is not a folder.")
    new_relative = clean_folder_path(new_relative)
    deepest = max(
        (
            len(os.path.relpath(folder_, source).split(os.sep))
            for folder_, _, _ in os.walk(source)
            if folder_ != source
        ),
        default=0,
    )
    if len(new_relative.split("/")) + deepest > MAX_DEPTH:
        raise StrictDocException(f"At most {MAX_DEPTH} levels of folders.")
    target = os.path.join(os.path.realpath(root), new_relative)
    if os.path.lexists(target):
        raise StrictDocException(f"'{new_relative}' exists already.")
    old = relative_path.strip("/")
    moving = {
        document_: new_relative + document_[len(old) :]
        for document_ in _documents_under(root, old)
    }
    _check_paths_still_resolve(root, moving)
    os.rename(source, target)
    return new_relative


def rename_folder(root: str, relative_path: str, new_name: str) -> str:
    """Gives a folder a new name; returns its new relative path."""
    name = _clean_name(new_name)
    parent = os.path.dirname(relative_path.strip("/"))
    new_relative = "/".join(part_ for part_ in (parent, name) if part_)
    return _move_folder_to(root, relative_path, new_relative)


def move_folder(root: str, relative_path: str, destination: str) -> str:
    """Moves a folder into another folder ("" is the root of the project)."""
    old = relative_path.strip("/")
    new_parent = destination.strip("/")
    _inside(root, old, "folder")
    if new_parent == old or new_parent.startswith(old + "/"):
        raise StrictDocException("A folder cannot move into itself.")
    if new_parent == os.path.dirname(old):
        raise StrictDocException(f"'{old}' is already in that folder.")
    new_relative = _destination(root, new_parent, os.path.basename(old))
    return _move_folder_to(root, old, new_relative)


def move_document(root: str, relative_path: str, destination: str) -> str:
    """Moves a document into a folder ("" is the root of the project)."""
    old = relative_path.strip("/")
    source = _inside(root, old, "document")
    if not os.path.isfile(source) or not old.endswith(DOCUMENT_EXTENSION):
        raise StrictDocException(f"'{old}' is not a document.")
    new_parent = destination.strip("/")
    if new_parent == os.path.dirname(old):
        raise StrictDocException(f"'{old}' is already in that folder.")
    new_relative = _destination(root, new_parent, os.path.basename(old))
    target = os.path.join(os.path.realpath(root), new_relative)
    if os.path.lexists(target):
        raise StrictDocException(f"'{new_relative}' exists already.")
    _check_paths_still_resolve(root, {old: new_relative})
    _keep_folder(root, os.path.dirname(old))
    os.rename(source, target)
    return new_relative


def blocking_files(root: str, relative_path: str) -> List[str]:
    """The files of a folder that keep it from being deleted (not markers)."""
    folder = _inside(root, relative_path.strip("/"), "folder")
    if not os.path.isdir(folder):
        raise StrictDocException(f"'{relative_path}' is not a folder.")
    found: List[str] = []
    for folder_, _, files_ in os.walk(folder):
        for file_ in files_:
            if file_ != MARKER:
                found.append(
                    os.path.relpath(
                        os.path.join(folder_, file_), folder
                    ).replace(os.sep, "/")
                )
    return sorted(found)


def delete_folder(root: str, relative_path: str) -> None:
    """Deletes a folder that has no file but its markers."""
    old = relative_path.strip("/")
    if old == "":
        raise StrictDocException("The project itself cannot be deleted.")
    blocking = blocking_files(root, old)
    if blocking:
        raise StrictDocException(
            f"The folder is not empty: move or delete '{blocking[0]}' first."
        )
    folder = _inside(root, old, "folder")
    for folder_, _, files_ in os.walk(folder, topdown=False):
        for file_ in files_:
            os.remove(os.path.join(folder_, file_))
        os.rmdir(folder_)
