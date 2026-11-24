"""
Build the .deb package of the desktop application, inside a container.

"invoke release-desktop" starts a ubuntu:22.04 container (the glibc of the
oldest target: Ubuntu 22.04 and Debian 12), mounts the repository read-only
on /source and runs this script in it. The same script serves the CI. It
installs the build tools, builds the PyInstaller folder with build_onedir.py,
and packs it with dpkg-deb.

Layout of the package:
- /opt/strictdoc-desktop/                             the application
- /usr/bin/strictdoc-desktop                          the launcher
- /usr/share/applications/strictdoc-desktop.desktop   the menu entry
- /usr/share/icons/hicolor/scalable/apps/             the icon
- postrm: removes what the application wrote in /opt/strictdoc-desktop

@relation(SDOC-SRS-1256, scope=file)
@relation(SDOC-SRS-1258, scope=file)
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

PACKAGE_NAME = "strictdoc-desktop"
_HERE = Path(__file__).resolve().parent
# PyInstaller copies the shared library of Python into the application.
_BUILD_PACKAGES = [
    "python3",
    "python3-pip",
    f"libpython{sys.version_info.major}.{sys.version_info.minor}",
    "binutils",
    "ca-certificates",
]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the .deb package.")
    parser.add_argument("--source", type=Path, default=Path("/source"))
    parser.add_argument("--output", type=Path, default=Path("/output"))
    parser.add_argument("--work-dir", type=Path, default=Path("/build"))
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--skip-apt", action="store_true")
    parser.add_argument(
        "--windowed-program",
        action="store_true",
        help="Also build strictdoc-desktop (to try the Windows spec file).",
    )
    arguments = parser.parse_args(argv)

    source = arguments.source.resolve()
    work_dir = arguments.work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    version = get_debian_version(source / "strictdoc" / "__init__.py")
    tag = os.environ.get("CI_COMMIT_TAG")
    if tag is not None and tag != "":
        version = get_version_from_tag(tag, version)

    if not arguments.skip_apt:
        # The libraries of the package are installed too: PyInstaller starts
        # Qt to find its plugins, and finds none when a library is missing.
        _run(["apt-get", "update"])
        _run(
            ["apt-get", "install", "--yes", "--no-install-recommends"]
            + _BUILD_PACKAGES
            + get_runtime_packages(_HERE / "control.in")
        )
    venv_python = prepare_environment(source, work_dir, arguments.cache_dir)

    app_dir = work_dir / "application"
    command = [
        str(venv_python),
        str(source / "developer" / "desktop" / "build_onedir.py"),
        "--platform",
        "linux64",
        "--app-dir",
        str(app_dir),
        "--work-dir",
        str(work_dir / "pyinstaller"),
    ]
    if arguments.windowed_program:
        command.append("--windowed-program")
    if arguments.cache_dir is not None:
        command += ["--cache-dir", str(arguments.cache_dir / "tools")]
    _run(command, environment=_get_environment(arguments.cache_dir))

    arguments.output.mkdir(parents=True, exist_ok=True)
    package_path = build_package(app_dir, work_dir, arguments.output, version)
    size_mb = package_path.stat().st_size / (1024 * 1024)
    print(f"Package: {package_path} ({size_mb:.0f} MB)")  # noqa: T201
    return 0


def get_debian_version(init_path: Path) -> str:
    """The version of strictdoc.__version__, in the Debian syntax."""
    text = init_path.read_text(encoding="utf8")
    match = re.search(r'^__version__ = "([^"]+)"', text, re.MULTILINE)
    if match is None:
        raise RuntimeError(f"No __version__ in {init_path}.")
    # A pre-release sorts before the release: "0.31.0a1" -> "0.31.0~a1".
    return re.sub(r"(?<=\d)(a|b|rc|\.dev)(?=\d)", r"~\1", match.group(1))


def get_version_from_tag(tag: str, source_version: str) -> str:
    """
    The Debian version of a tag "desktop-v<version>[-<pre-release>]", for
    example "desktop-v0.30.2-rc1" gives "0.30.2~rc1". The base of the tag
    ("0.30.2") has to be the base of the version of the source, so that a
    package never carries a version that the code does not have.
    """
    match = re.fullmatch(r"desktop-v(\d+(?:\.\d+)*)(?:-([0-9A-Za-z.]+))?", tag)
    if match is None:
        raise RuntimeError(
            f"The tag {tag!r} is not of the form desktop-v<version>, for "
            "example desktop-v0.30.2 or desktop-v0.30.2-rc1."
        )
    base = match.group(1)
    source_base = source_version.split("~", maxsplit=1)[0]
    if base != source_base:
        raise RuntimeError(
            f"The tag {tag!r} says version {base}, but strictdoc.__version__ "
            f"is {source_base}. Fix the tag or the version, then build again."
        )
    if match.group(2) is None:
        return base
    return f"{base}~{match.group(2)}"


def get_runtime_packages(control_path: Path) -> List[str]:
    """
    The last choice of each entry of the Depends line of the control: the
    name that the build system (Ubuntu 22.04) has. The newer systems have the
    first choice, the name with the suffix t64. The t64 name goes first
    because on a system that has it, the old name can be a virtual package
    that a wrong library provides (liboss4-salsa-asound2 provides libasound2).
    """
    text = control_path.read_text(encoding="utf8")
    match = re.search(r"^Depends: (.+)$", text, re.MULTILINE)
    if match is None:
        raise RuntimeError(f"No Depends line in {control_path}.")
    return [
        entry_.split("|")[-1].strip()
        for entry_ in match.group(1).split(",")
        if entry_.strip() != ""
    ]


def prepare_environment(
    source: Path, work_dir: Path, cache_dir: Optional[Path]
) -> Path:
    """Install uv, then the locked dependencies in a virtual environment."""
    venv_dir = work_dir / "venv"
    environment = _get_environment(cache_dir)
    environment["UV_PROJECT_ENVIRONMENT"] = str(venv_dir)
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "uv",
        ],
        environment=environment,
    )
    _run(
        [
            sys.executable,
            "-m",
            "uv",
            "sync",
            "--frozen",
            "--no-install-project",
            "--no-python-downloads",
            "--python",
            sys.executable,
            "--group",
            "desktop",
            "--group",
            "pyinstaller",
        ],
        environment=environment,
        cwd=source,
    )
    return venv_dir / "bin" / "python"


def build_package(
    app_dir: Path, work_dir: Path, output: Path, version: str
) -> Path:
    package_root = work_dir / "package"
    shutil.rmtree(package_root, ignore_errors=True)
    install_dir = package_root / "opt" / PACKAGE_NAME
    install_dir.parent.mkdir(parents=True)
    shutil.copytree(app_dir, install_dir, symlinks=True)

    _install_file(
        _HERE / PACKAGE_NAME,
        package_root / "usr" / "bin" / PACKAGE_NAME,
        executable=True,
    )
    _install_file(
        _HERE / f"{PACKAGE_NAME}.desktop",
        package_root
        / "usr"
        / "share"
        / "applications"
        / f"{PACKAGE_NAME}.desktop",
    )
    _install_file(
        _HERE / f"{PACKAGE_NAME}.svg",
        package_root
        / "usr"
        / "share"
        / "icons"
        / "hicolor"
        / "scalable"
        / "apps"
        / f"{PACKAGE_NAME}.svg",
    )
    _normalize_permissions(package_root)

    installed_size_kb = _get_size_kb(package_root)
    control = (_HERE / "control.in").read_text(encoding="utf8")
    control = control.replace("@VERSION@", version).replace(
        "@INSTALLED_SIZE@", str(installed_size_kb)
    )
    control_dir = package_root / "DEBIAN"
    control_dir.mkdir()
    (control_dir / "control").write_text(control, encoding="utf8")
    control_dir.chmod(0o755)
    _install_file(_HERE / "postrm", control_dir / "postrm", executable=True)

    package_path = output / f"{PACKAGE_NAME}_{version}_amd64.deb"
    _run(
        [
            "dpkg-deb",
            "--root-owner-group",
            "--build",
            str(package_root),
            str(package_path),
        ]
    )
    return package_path


def _install_file(
    source: Path, destination: Path, executable: bool = False
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(0o755 if executable else 0o644)


def _normalize_permissions(root: Path) -> None:
    """Directories 755, programs 755, other files 644, whatever the umask."""
    for path_ in [root, *root.rglob("*")]:
        if path_.is_symlink():
            continue
        if path_.is_dir():
            path_.chmod(0o755)
        elif path_.stat().st_mode & 0o100:
            path_.chmod(0o755)
        else:
            path_.chmod(0o644)


def _get_size_kb(root: Path) -> int:
    total = 0
    for path_ in root.rglob("*"):
        if path_.is_file() and not path_.is_symlink():
            total += path_.stat().st_size
    return total // 1024 + 1


def _get_environment(cache_dir: Optional[Path]) -> Dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["DEBIAN_FRONTEND"] = "noninteractive"
    if cache_dir is not None:
        environment["UV_CACHE_DIR"] = str(cache_dir / "uv")
    return environment


def _run(
    command: List[str],
    environment: Optional[Dict[str, str]] = None,
    cwd: Optional[Path] = None,
) -> None:
    print(">>", " ".join(command), flush=True)  # noqa: T201
    subprocess.run(command, check=True, env=environment, cwd=cwd)


if __name__ == "__main__":
    sys.exit(main())
