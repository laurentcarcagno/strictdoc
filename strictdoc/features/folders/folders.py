"""
Folders of a project, to organise its documents.

StrictDoc shows a folder in the project tree only when a document is in it. A
folder that a person creates is empty at first, so it carries a marker file
(``.sdoc-folder``): the tree shows the folders that have one. The marker is not a
document and is never read as one (it has no document extension).
"""

import os
import re
import shutil
from typing import Iterator, List, Sequence, Tuple, Union

from strictdoc.core.file_system.file_tree import Folder
from strictdoc.helpers.exception import StrictDocException

MARKER = ".sdoc-folder"

_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_RESERVED = ("_assets", "output", "Output", "word")
MAX_DEPTH = 8

# The input folders of the project: one path, or a list of paths.
Roots = Union[str, Sequence[str]]


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


def create_folder(roots: Roots, relative_path: str) -> List[str]:
    """
    Creates the folder (and the missing levels above it), each with the
    marker. Returns the paths of the folders that did not exist. With several
    input folders, the first level of the path is the name of one of them.
    Raises StrictDocException when it exists, or when a file is in the way.
    """
    path = clean_folder_path(relative_path)
    real_roots = _roots(roots)
    segments = path.split("/")
    prefix = ""
    base = real_roots[0]
    if len(real_roots) > 1:
        base = _root_named(real_roots, segments[0], relative_path)
        prefix = segments[0] + "/"
        segments = segments[1:]
        if len(segments) == 0:
            raise StrictDocException(f"The folder '{path}' already exists.")
    created: List[str] = []
    current = base
    parts: List[str] = []
    for segment_ in segments:
        parts.append(segment_)
        current = os.path.join(current, segment_)
        if os.path.islink(current) or (
            os.path.exists(current) and not os.path.isdir(current)
        ):
            raise StrictDocException(
                f"'{prefix}{'/'.join(parts)}' exists and is not a folder."
            )
        if not os.path.isdir(current):
            os.mkdir(current)
            created.append("/".join(parts))
    if len(created) == 0:
        raise StrictDocException(f"The folder '{path}' already exists.")
    for relative_ in created:
        marker = os.path.join(base, relative_, MARKER)
        with open(marker, "w", encoding="utf8"):
            pass
    return [prefix + relative_ for relative_ in created]


def folder_paths(folder: Folder, prefix: str = "") -> Iterator[str]:
    """
    The relative paths of the folders below a folder, that can hold
    documents (without the reserved ones). With several input folders,
    `prefix` is the name of the input folder and a slash.
    """
    for sub_ in folder.subfolder_trees:
        name = sub_.folder_name
        if name in _RESERVED or name.startswith((".", "_")):
            continue
        yield prefix + sub_.rel_path.rstrip("/")
        yield from folder_paths(sub_, prefix)


#
# Rename, move and delete.
#
# Paths are the ones of the project tree: relative to the input folder of the
# project ("specs/system", "specs/a.sdoc"; "" is the input folder itself). With
# several input folders, the first level is the name of one of them
# ("isis/specs/a.sdoc").
#

# The path of an include or an import is relative to the document that has it.
_INCLUDE = re.compile(
    r"^(\[DOCUMENT_FROM_FILE\]\s*\nFILE: *)(.+?)(\s*)$", re.MULTILINE
)
_IMPORT = re.compile(r"^(IMPORT_FROM_FILE: *)([^@\s].*?)(\s*)$", re.MULTILINE)
DOCUMENT_EXTENSION = ".sdoc"

Moves = List[Tuple[str, str]]


def _roots(roots: Roots) -> List[str]:
    """The real paths of the input folders (the files are not folders)."""
    given = [roots] if isinstance(roots, str) else list(roots)
    found: List[str] = []
    for root_ in given:
        real = os.path.realpath(root_)
        if os.path.isdir(real) and real not in found:
            found.append(real)
    if len(found) == 0:
        raise StrictDocException("The project has no input folder.")
    return found


def _root_named(real_roots: List[str], name: str, shown: str) -> str:
    matches = [root_ for root_ in real_roots if os.path.basename(root_) == name]
    if len(matches) != 1:
        raise StrictDocException(f"Invalid path '{shown}'.")
    return matches[0]


def tree_path(roots: Roots, absolute_path: str) -> str:
    """The path of the project tree of a file or a folder ("" if outside)."""
    real_roots = _roots(roots)
    real = os.path.realpath(absolute_path)
    for root_ in real_roots:
        if real == root_ or real.startswith(root_ + os.sep):
            relative = os.path.relpath(real, root_).replace(os.sep, "/")
            relative = "" if relative == "." else relative
            if len(real_roots) == 1:
                return relative
            return "/".join(
                part_ for part_ in (os.path.basename(root_), relative) if part_
            )
    return ""


def locate(roots: Roots, tree_path_: str, what: str = "folder") -> str:
    """
    The absolute path of a path of the project tree. It must exist and must
    not go out of the input folders (no "..", no link).
    """
    real_roots = _roots(roots)
    path = tree_path_.strip().replace("\\", "/").strip("/")
    segments = [] if path == "" else path.split("/")
    for segment_ in segments:
        if segment_ in ("", ".", "..") or "\0" in segment_:
            raise StrictDocException(f"Invalid {what} '{tree_path_}'.")
    if len(real_roots) == 1:
        current = real_roots[0]
    elif len(segments) == 0:
        raise StrictDocException(
            "The project has several input folders: choose one of them."
        )
    else:
        current = _root_named(real_roots, segments[0], tree_path_)
        segments = segments[1:]
    for segment_ in segments:
        current = os.path.join(current, segment_)
        if os.path.islink(current):
            raise StrictDocException(f"Invalid {what} '{tree_path_}'.")
    if not os.path.exists(current):
        raise StrictDocException(f"The {what} '{path}' does not exist.")
    return current


def _refuse_input_folder(roots: Roots, absolute_path: str, shown: str) -> None:
    if absolute_path in _roots(roots):
        raise StrictDocException(
            f"'{shown}' is an input folder of the project: it stays where it is."
        )


def _clean_name(name: str) -> str:
    text = name.strip()
    if "/" in text or "\\" in text:
        raise StrictDocException(
            "A folder name has no '/': use the move to change its place."
        )
    return clean_folder_path(text)


def _documents_under(base: str) -> List[str]:
    """The absolute paths of the documents in a folder, at any depth."""
    found: List[str] = []
    for folder_, dirs_, files_ in os.walk(base):
        dirs_[:] = [
            dir_
            for dir_ in dirs_
            if dir_ not in _RESERVED and not dir_.startswith((".", "_"))
        ]
        for file_ in files_:
            if file_.endswith(DOCUMENT_EXTENSION):
                found.append(os.path.join(folder_, file_))
    return sorted(found)


def _depth(roots: Roots, absolute_path: str) -> int:
    """The levels of folders of a path, below its input folder."""
    segments = [
        segment_
        for segment_ in tree_path(roots, absolute_path).split("/")
        if segment_
    ]
    return len(segments) - (1 if len(_roots(roots)) > 1 else 0)


def _mapped(path: str, moves: Moves) -> str:
    """Where a file or a folder is after the moves."""
    for old_, new_ in moves:
        if path == old_ or path.startswith(old_ + os.sep):
            return new_ + path[len(old_) :]
    return path


def _rewritten(text: str, document: str, moves: Moves) -> str:
    """The text of a document, with the paths of its includes and imports."""
    directory = os.path.dirname(document)
    new_directory = os.path.dirname(_mapped(document, moves))

    def rewrite(match: "re.Match[str]") -> str:
        target = os.path.normpath(os.path.join(directory, match.group(2)))
        new_path = os.path.relpath(
            _mapped(target, moves), new_directory
        ).replace(os.sep, "/")
        if new_path == os.path.relpath(target, directory).replace(os.sep, "/"):
            return match.group(0)
        return match.group(1) + new_path + match.group(3)

    return _IMPORT.sub(rewrite, _INCLUDE.sub(rewrite, text))


def _plan_rewrites(roots: Roots, moves: Moves) -> List[Tuple[str, str]]:
    """
    Documents include and import each other by relative paths. For each
    document that has such a path changed by the moves (the document moves, or
    its target does), the (old path, new text) with the path rewritten.
    """
    plan: List[Tuple[str, str]] = []
    documents: List[str] = []
    for root_ in _roots(roots):
        documents.extend(_documents_under(root_))
    for document_ in sorted(set(documents)):
        try:
            with open(document_, encoding="utf8", newline="") as file_:
                text = file_.read()
        except (OSError, UnicodeDecodeError):
            continue
        new_text = _rewritten(text, document_, moves)
        if new_text != text:
            plan.append((document_, new_text))
    return plan


def _apply(moves: Moves, plan: List[Tuple[str, str]]) -> None:
    """Moves the files, then writes the documents with their new paths."""
    for old_, new_ in moves:
        shutil.move(old_, new_)
    for document_, text_ in plan:
        with open(
            _mapped(document_, moves), "w", encoding="utf8", newline=""
        ) as file_:
            file_.write(text_)


def _destination(roots: Roots, destination: str, name: str) -> str:
    """The absolute path of `name` in the destination folder (checked)."""
    folder = locate(roots, destination, "destination folder")
    if not os.path.isdir(folder):
        raise StrictDocException(
            f"The destination '{destination}' is not a folder."
        )
    return os.path.join(folder, name)


def _keep_folder(roots: Roots, folder: str) -> None:
    """A folder that loses its last document stays in the tree."""
    if folder in _roots(roots):
        return
    marker = os.path.join(folder, MARKER)
    if not os.path.exists(marker):
        with open(marker, "w", encoding="utf8"):
            pass


def _move_folder_to(roots: Roots, source: str, target: str) -> str:
    if not os.path.isdir(source):
        raise StrictDocException(
            f"'{tree_path(roots, source)}' is not a folder."
        )
    deepest = max(
        (
            len(os.path.relpath(folder_, source).split(os.sep))
            for folder_, _, _ in os.walk(source)
            if folder_ != source
        ),
        default=0,
    )
    if _depth(roots, os.path.dirname(target)) + 1 + deepest > MAX_DEPTH:
        raise StrictDocException(f"At most {MAX_DEPTH} levels of folders.")
    if os.path.lexists(target):
        raise StrictDocException(
            f"'{tree_path(roots, target)}' exists already."
        )
    moves = [(source, target)]
    plan = _plan_rewrites(roots, moves)
    if os.path.dirname(target) != os.path.dirname(source):
        _keep_folder(roots, os.path.dirname(source))
    _apply(moves, plan)
    return tree_path(roots, target)


def rename_folder(roots: Roots, relative_path: str, new_name: str) -> str:
    """Gives a folder a new name; returns its new path."""
    name = _clean_name(new_name)
    source = locate(roots, relative_path)
    _refuse_input_folder(roots, source, relative_path.strip("/"))
    return _move_folder_to(
        roots, source, os.path.join(os.path.dirname(source), name)
    )


def move_folder(roots: Roots, relative_path: str, destination: str) -> str:
    """
    Moves a folder into another folder ("" is the project, if it has one input
    folder).
    """
    old = relative_path.strip("/")
    source = locate(roots, old)
    _refuse_input_folder(roots, source, old)
    folder = _destination(roots, destination, os.path.basename(source))
    parent = os.path.dirname(folder)
    if parent == source or parent.startswith(source + os.sep):
        raise StrictDocException("A folder cannot move into itself.")
    if parent == os.path.dirname(source):
        raise StrictDocException(f"'{old}' is already in that folder.")
    return _move_folder_to(roots, source, folder)


def move_document(roots: Roots, relative_path: str, destination: str) -> str:
    """Moves a document into a folder."""
    old = relative_path.strip("/")
    source = locate(roots, old, "document")
    if not os.path.isfile(source) or not old.endswith(DOCUMENT_EXTENSION):
        raise StrictDocException(f"'{old}' is not a document.")
    target = _destination(roots, destination, os.path.basename(source))
    if os.path.dirname(target) == os.path.dirname(source):
        raise StrictDocException(f"'{old}' is already in that folder.")
    if os.path.lexists(target):
        raise StrictDocException(
            f"'{tree_path(roots, target)}' exists already."
        )
    moves = [(source, target)]
    plan = _plan_rewrites(roots, moves)
    _keep_folder(roots, os.path.dirname(source))
    _apply(moves, plan)
    return tree_path(roots, target)


def blocking_files(roots: Roots, relative_path: str) -> List[str]:
    """The files of a folder that keep it from being deleted (not markers)."""
    folder = locate(roots, relative_path.strip("/"))
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


def delete_folder(roots: Roots, relative_path: str) -> None:
    """Deletes a folder that has no file but its markers."""
    old = relative_path.strip("/")
    folder = locate(roots, old)
    _refuse_input_folder(roots, folder, old or "the project")
    blocking = blocking_files(roots, old)
    if blocking:
        raise StrictDocException(
            f"The folder is not empty: move or delete '{blocking[0]}' first."
        )
    for folder_, _, files_ in os.walk(folder, topdown=False):
        for file_ in files_:
            os.remove(os.path.join(folder_, file_))
        os.rmdir(folder_)
