"""
Build the folder of the desktop application with PyInstaller.

The folder holds the frozen strictdoc program and, in its "tools" sub-folder,
what the application needs on a computer that has nothing: the headless Chrome
and its chromedriver, a frozen html2pdf4doc program, and on Windows MinGit.
The Linux script (build_deb.py) and the Windows script
(windows/build_installer.ps1) both call this script, in a virtual environment
where StrictDoc, its "desktop" dependencies and PyInstaller are installed.

@relation(SDOC-SRS-1256, scope=file)
@relation(SDOC-SRS-1257, scope=file)
@relation(SDOC-SRS-1258, scope=file)
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

HERE = Path(__file__).resolve().parent
SOURCE_ROOT = HERE.parent.parent

_HIDDEN_IMPORTS = [
    "strictdoc.api",
    "strictdoc.backend.markdown.strictdoc_lexer",
    "strictdoc.core.statistics.metric",
    "strictdoc.export.html.generators.project_statistics",
    "strictdoc.export.html.generators.view_objects.project_statistics_view_object",
    "strictdoc.export.html.generators.view_objects.project_tree_stats",
    "strictdoc.server.app",
]

# The same folders as PYINSTALLER_PACKAGE_DATA_DIRS of tasks.py, and the
# folders of the desktop feature, which the code reads next to its modules.
_PACKAGE_DATA_DIRS = [
    "strictdoc/features/i18n/locales",
    "strictdoc/features/llm/prompts",
    "strictdoc/features/llm/golden",
    "strictdoc/features/projects/templates",
    "strictdoc/features/desktop/templates",
    "strictdoc/features/desktop/assets",
]


_SYSTEM_LIBRARY_PREFIXES = (
    "libnss3",
    "libnssutil3",
    "libsmime3",
    "libnspr4",
    "libplc4",
    "libplds4",
    "libfreebl",
    "libsndfile",
    "libFLAC",
    "libogg",
    "libvorbis",
    "libopus",
    "libpulse",
    "libasyncns",
)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the folder of the desktop application."
    )
    parser.add_argument(
        "--platform", choices=("linux64", "win64"), required=True
    )
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument(
        "--windowed-program",
        action="store_true",
        help="Build strictdoc-desktop too (always on for win64).",
    )
    arguments = parser.parse_args(argv)

    work_dir = arguments.work_dir.resolve()
    app_dir = arguments.app_dir.resolve()
    shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True)

    build_strictdoc(
        work_dir,
        with_windowed_program=(
            arguments.platform == "win64" or arguments.windowed_program
        ),
    )
    build_html2pdf4doc(work_dir, without_console=arguments.platform == "win64")

    shutil.rmtree(app_dir, ignore_errors=True)
    shutil.copytree(work_dir / "dist" / "strictdoc", app_dir)
    shutil.copytree(
        work_dir / "dist" / "html2pdf4doc",
        app_dir / "tools" / "html2pdf4doc",
    )
    if arguments.platform == "linux64":
        remove_system_libraries(app_dir)
    fetch_tools(arguments.platform, app_dir, arguments.cache_dir)
    return 0


def build_strictdoc(work_dir: Path, with_windowed_program: bool) -> None:
    """
    Build the folder of strictdoc.

    With the windowed program, the folder holds a second executable,
    strictdoc-desktop, without a console window, which runs "strictdoc
    desktop". Both share the libraries and the data of the folder.
    """
    sys.path.insert(0, str(SOURCE_ROOT))
    from strictdoc.core.environment import (  # noqa: PLC0415
        BINARY_HTML_STATIC_DIR,
        BINARY_HTML_TEMPLATES_DIR,
        HTML_STATIC_DIRS,
        HTML_TEMPLATE_DIRS,
    )

    data: List[Tuple[str, str]] = []
    for directory_ in HTML_TEMPLATE_DIRS:
        data.append((directory_, BINARY_HTML_TEMPLATES_DIR))
    for directory_ in HTML_STATIC_DIRS:
        data.append((directory_, BINARY_HTML_STATIC_DIR))
    for directory_ in _PACKAGE_DATA_DIRS:
        data.append((directory_, directory_))

    # window.py imports pywebview by its name at run time (importlib), so
    # PyInstaller does not see it. The sub-modules hold the engines (Qt,
    # WebView2).
    hidden_imports = [*_HIDDEN_IMPORTS, "webview"]
    main_script = SOURCE_ROOT / "strictdoc" / "cli" / "main.py"

    if with_windowed_program:
        spec_path = work_dir / "strictdoc.spec"
        spec_path.write_text(
            _get_spec(
                main_script=main_script,
                windowed_script=HERE / "strictdoc_desktop_entry.py",
                data=data,
                hidden_imports=hidden_imports,
            ),
            encoding="utf8",
        )
        command = _get_pyinstaller_command(None, work_dir, "strictdoc")
        command.append(str(spec_path))
        _run(command)
        return

    command = _get_pyinstaller_command("strictdoc", work_dir, "strictdoc")
    for name_ in hidden_imports:
        command += ["--hidden-import", name_]
    command += ["--collect-submodules", "webview"]
    for source_, destination_ in data:
        command += _get_data_option(source_, destination_)
    command.append(str(main_script))
    _run(command)


def build_html2pdf4doc(work_dir: Path, without_console: bool) -> None:
    command = _get_pyinstaller_command("html2pdf4doc", work_dir, "html2pdf4doc")
    if without_console:
        # The windowed application has no console: a program with one would
        # open a window at each export.
        command.append("--noconsole")
    command.append(str(HERE / "html2pdf4doc_entry.py"))
    _run(command)


def remove_system_libraries(app_dir: Path) -> None:
    """
    Remove the copies of system libraries that must come from the computer.

    PyInstaller copies the libraries of the build computer. Most work on the
    other targets, but these come in sets that must match the ones of the
    system: NSS loads its own parts by name (libsoftokn3) and the audio
    libraries chain on each other. The package depends on the system
    packages that hold them (control.in).
    """
    internal_dir = app_dir / "_internal"
    for path_ in sorted(internal_dir.iterdir()):
        if path_.is_dir() and path_.name == "nss":
            shutil.rmtree(path_)
        elif path_.is_file() and path_.name.startswith(
            _SYSTEM_LIBRARY_PREFIXES
        ):
            path_.unlink()


def fetch_tools(
    platform: str, app_dir: Path, cache_dir: Optional[Path]
) -> None:
    command = [
        sys.executable,
        str(HERE / "fetch_bundled_tools.py"),
        "--platform",
        platform,
        "--target",
        str(app_dir),
    ]
    if cache_dir is not None:
        command += ["--cache-dir", str(cache_dir)]
    _run(command)


def _get_pyinstaller_command(
    name: Optional[str], work_dir: Path, build_name: str
) -> List[str]:
    """The command of PyInstaller. Without a name, a spec file follows."""
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(work_dir / "dist"),
        "--workpath",
        str(work_dir / "build" / build_name),
    ]
    # A spec file brings its own options (PyInstaller refuses these ones).
    if name is not None:
        command += [
            "--additional-hooks-dir",
            str(SOURCE_ROOT / "developer" / "pyinstaller_hooks"),
            "--name",
            name,
            "--specpath",
            str(work_dir / "spec"),
        ]
    return command


def _get_spec(
    *,
    main_script: Path,
    windowed_script: Path,
    data: List[Tuple[str, str]],
    hidden_imports: List[str],
) -> str:
    """
    The spec file of a folder with two programs: strictdoc, with a console,
    and strictdoc-desktop, without one. The libraries and the data of the two
    are collected once, in the same folder.
    """
    datas = [
        (str(SOURCE_ROOT / source_), destination_)
        for source_, destination_ in data
    ]
    hooks_path = str(SOURCE_ROOT / "developer" / "pyinstaller_hooks")
    return f"""\
from PyInstaller.utils.hooks import collect_submodules

datas = {datas!r}
hidden_imports = {hidden_imports!r} + collect_submodules("webview")
hooks_path = [{hooks_path!r}]

analysis_console = Analysis(
    [{str(main_script)!r}],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=hooks_path,
)
analysis_windowed = Analysis(
    [{str(windowed_script)!r}],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=hooks_path,
)
program_console = EXE(
    PYZ(analysis_console.pure),
    analysis_console.scripts,
    [],
    exclude_binaries=True,
    name="strictdoc",
    console=True,
)
program_windowed = EXE(
    PYZ(analysis_windowed.pure),
    analysis_windowed.scripts,
    [],
    exclude_binaries=True,
    name="strictdoc-desktop",
    console=False,
)
COLLECT(
    program_console,
    analysis_console.binaries,
    analysis_console.datas,
    program_windowed,
    analysis_windowed.binaries,
    analysis_windowed.datas,
    name="strictdoc",
)
"""


def _get_data_option(source: str, destination: str) -> List[str]:
    return [
        "--add-data",
        f"{SOURCE_ROOT / source}{os.pathsep}{destination}",
    ]


def _run(command: List[str]) -> None:
    print(">>", " ".join(command), flush=True)  # noqa: T201
    subprocess.run(command, check=True, cwd=SOURCE_ROOT)


if __name__ == "__main__":
    sys.exit(main())
