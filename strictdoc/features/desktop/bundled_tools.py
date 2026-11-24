"""
The tools that the package of the desktop application carries.

The package holds a "tools" folder next to the executable: a headless Chrome
and its chromedriver for the PDF export, a frozen html2pdf4doc program that
starts them, and on Windows a Git (MinGit). When
the folder or a tool is missing, the application uses what the computer has.

@relation(SDOC-SRS-1257, scope=file)
@relation(SDOC-SRS-1258, scope=file)
"""

import os
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, Mapping, Optional

TOOLS_DIR_VARIABLE = "STRICTDOC_DESKTOP_TOOLS_DIR"
_TOOLS_FOLDER_NAME = "tools"


@dataclass(frozen=True)
class BundledTools:
    chrome_binary: Optional[Path]
    chromedriver: Optional[Path]
    git: Optional[Path]
    html2pdf4doc: Optional[Path]


def get_tools_dir() -> Optional[Path]:
    """
    The "tools" folder of the package, if there is one.

    The variable STRICTDOC_DESKTOP_TOOLS_DIR gives the folder in the tests. In
    a frozen application the folder is next to the executable.
    """
    folder = os.environ.get(TOOLS_DIR_VARIABLE)
    if folder is not None and folder != "":
        return Path(folder)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / _TOOLS_FOLDER_NAME
    return None


def find_bundled_tools() -> BundledTools:
    """The paths of the tools of the package that exist."""
    tools_dir = get_tools_dir()
    if tools_dir is None:
        return BundledTools(None, None, None, None)
    suffix = ".exe" if sys.platform == "win32" else ""
    return BundledTools(
        chrome_binary=_existing_file(
            tools_dir
            / "chrome-headless-shell"
            / f"chrome-headless-shell{suffix}"
        ),
        chromedriver=_existing_file(
            tools_dir / "chromedriver" / f"chromedriver{suffix}"
        ),
        git=_existing_file(tools_dir / "mingit" / "cmd" / f"git{suffix}"),
        html2pdf4doc=_existing_file(
            tools_dir / "html2pdf4doc" / f"html2pdf4doc{suffix}"
        ),
    )


def use_bundled_git(git_path: Path) -> None:
    """
    Make GitPython and the commands of the application use the embedded Git.

    The folder of the program goes first in PATH, for the calls that start
    "git" by its name.
    """
    # Before the import: GitPython refuses to load when Git is missing.
    os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")
    import git  # noqa: PLC0415

    git.refresh(str(git_path))
    _put_first_in_path(git_path.parent)


def refresh_git() -> None:
    """
    Ask GitPython to find Git again, with the library path of the system: it
    runs "git version" with the environment of the process.
    """
    os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")
    import git  # noqa: PLC0415

    with system_library_path():
        git.refresh()


def use_bundled_html2pdf4doc(html2pdf4doc_path: Path) -> None:
    """
    Put the frozen html2pdf4doc program first in PATH.

    The PDF export starts "html2pdf4doc" by its name, and a frozen application
    has no such program in the environment of the computer.
    """
    _put_first_in_path(html2pdf4doc_path.parent)


def get_library_path_overrides() -> Dict[str, str]:
    """
    The library path that a program of the system needs, when it differs from
    the one of this process.

    A frozen application on Linux sets LD_LIBRARY_PATH to its own folder, and
    keeps the original value in LD_LIBRARY_PATH_ORIG. A program of the system
    (Git) that inherits the folder of the package loads the libraries of the
    package in place of its own. The value is empty when the variable was not
    set: an empty path loads nothing more. The environment of this process
    stays as it is: the Qt WebEngine process needs it.
    """
    if not getattr(sys, "frozen", False) or sys.platform == "win32":
        return {}
    return {"LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH_ORIG", "")}


def get_system_program_environment(
    environment: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    """
    A copy of the environment (by default the one of this process) for a
    program of the system: without the library path of the package.
    """
    result = dict(os.environ if environment is None else environment)
    for name_, value_ in get_library_path_overrides().items():
        if value_ == "":
            result.pop(name_, None)
        else:
            result[name_] = value_
    return result


@contextmanager
def system_library_path() -> Iterator[None]:
    """
    Run a block with the library path of the system in the environment of the
    process, then put the one of the package back.

    GitPython runs "git version" with the environment of the process when it
    is imported and when it is refreshed. This is for those two moments, at
    the start of the application, before any window exists: the Qt WebEngine
    process needs the library path of the package for the rest of the run.
    """
    overrides = get_library_path_overrides()
    saved = {name_: os.environ.get(name_) for name_ in overrides}
    for name_, value_ in overrides.items():
        if value_ == "":
            os.environ.pop(name_, None)
        else:
            os.environ[name_] = value_
    try:
        yield
    finally:
        for name_, old_value_ in saved.items():
            if old_value_ is None:
                os.environ.pop(name_, None)
            else:
                os.environ[name_] = old_value_


def get_hidden_window_flags() -> int:
    """
    The "creationflags" of subprocess for a program of the system. On Windows
    the windowed application has no console, and a console program would open
    a window of its own.
    """
    if sys.platform == "win32":
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
    return 0


def _put_first_in_path(folder: Path) -> None:
    os.environ["PATH"] = os.pathsep.join(
        [str(folder), os.environ.get("PATH", "")]
    )


def _existing_file(path: Path) -> Optional[Path]:
    return path if path.is_file() else None
