"""
@relation(SDOC-SRS-1256, scope=file)
"""

from pathlib import Path
from typing import Any, Dict, List

import pytest

from developer.desktop import build_deb

_CONTROL_PATH = Path(build_deb.__file__).resolve().parent / "control.in"


@pytest.mark.parametrize(
    ("version", "expected"),
    [("0.31.0", "0.31.0"), ("0.31.0a1", "0.31.0~a1"), ("1.0rc2", "1.0~rc2")],
)
def test_get_debian_version_sorts_a_prerelease_before_the_release(
    tmp_path: Path, version: str, expected: str
) -> None:
    init_path = tmp_path / "__init__.py"
    init_path.write_text(f'__version__ = "{version}"\n', encoding="utf8")

    assert build_deb.get_debian_version(init_path) == expected


def test_get_debian_version_fails_without_a_version(tmp_path: Path) -> None:
    init_path = tmp_path / "__init__.py"
    init_path.write_text("answer = 42\n", encoding="utf8")

    with pytest.raises(RuntimeError):
        build_deb.get_debian_version(init_path)


@pytest.mark.parametrize(
    ("tag", "source_version", "expected"),
    [
        ("desktop-v0.30.2", "0.30.2", "0.30.2"),
        ("desktop-v0.30.2-rc1", "0.30.2", "0.30.2~rc1"),
        ("desktop-v0.30.2-rc1", "0.30.2~a1", "0.30.2~rc1"),
    ],
)
def test_version_of_a_tag_sorts_a_prerelease_before_the_release(
    tag: str, source_version: str, expected: str
) -> None:
    assert build_deb.get_version_from_tag(tag, source_version) == expected


def test_a_tag_with_another_base_than_the_source_stops_the_build() -> None:
    with pytest.raises(RuntimeError, match="0.30.3.*0.30.2"):
        build_deb.get_version_from_tag("desktop-v0.30.3", "0.30.2")


def test_a_tag_of_another_form_stops_the_build() -> None:
    with pytest.raises(RuntimeError, match="desktop-v<version>"):
        build_deb.get_version_from_tag("v0.30.2", "0.30.2")


def test_runtime_packages_take_the_first_choice_and_include_git() -> None:
    packages = build_deb.get_runtime_packages(_CONTROL_PATH)

    assert "git" in packages
    assert "libasound2" in packages
    assert "libasound2t64" not in packages
    assert all("|" not in package_ for package_ in packages)


def test_built_package_has_control_launcher_menu_entry_and_postrm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = tmp_path / "application"
    application.mkdir()
    (application / "strictdoc").write_text("binary", encoding="utf8")
    commands: List[List[str]] = []

    def fake_run(command: List[str], **_: Any) -> None:
        commands.append(command)

    monkeypatch.setattr(build_deb, "_run", fake_run)

    package_path = build_deb.build_package(
        application, tmp_path / "work", tmp_path / "out", "1.2.3~a1"
    )

    assert package_path.name == "strictdoc-desktop_1.2.3~a1_amd64.deb"
    assert commands[0][0] == "dpkg-deb"
    root = tmp_path / "work" / "package"

    control_text = (root / "DEBIAN" / "control").read_text(encoding="utf8")
    fields: Dict[str, str] = {}
    for line_ in control_text.splitlines():
        if not line_.startswith(" ") and ": " in line_:
            key, value = line_.split(": ", 1)
            fields[key] = value
    assert fields["Package"] == "strictdoc-desktop"
    assert fields["Version"] == "1.2.3~a1"
    assert "@" not in fields["Installed-Size"]
    assert "git" in [entry_.strip() for entry_ in fields["Depends"].split(",")]

    assert (root / "opt" / "strictdoc-desktop" / "strictdoc").is_file()
    launcher = root / "usr" / "bin" / "strictdoc-desktop"
    assert launcher.stat().st_mode & 0o777 == 0o755
    assert "/opt/strictdoc-desktop/strictdoc desktop" in launcher.read_text(
        encoding="utf8"
    )
    menu_entry = (
        root / "usr" / "share" / "applications" / "strictdoc-desktop.desktop"
    )
    assert menu_entry.is_file()

    postrm = root / "DEBIAN" / "postrm"
    assert postrm.stat().st_mode & 0o777 == 0o755
    postrm_text = postrm.read_text(encoding="utf8")
    assert "rm -rf /opt/strictdoc-desktop" in postrm_text
    assert "remove | purge" in postrm_text
