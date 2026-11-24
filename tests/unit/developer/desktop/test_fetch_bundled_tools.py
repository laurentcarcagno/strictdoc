"""
@relation(SDOC-SRS-1257, scope=file)
@relation(SDOC-SRS-1258, scope=file)
"""

import hashlib
import json
import os
import stat
import zipfile
from pathlib import Path
from typing import Tuple

import pytest

from developer.desktop import fetch_bundled_tools as script


def _make_manifest(
    tmp_path: Path, *, sha256_override: str = ""
) -> Tuple[Path, Path]:
    archive_path = tmp_path / "source" / "tool-linux64.zip"
    archive_path.parent.mkdir()
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("tool-linux64/readme.txt", "hello")
        executable = zipfile.ZipInfo("tool-linux64/tool")
        executable.external_attr = (stat.S_IFREG | 0o755) << 16
        archive.writestr(executable, "#!/bin/sh\n")
    sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    manifest = {
        "platforms": {
            "linux64": [
                {
                    "name": "tool",
                    "version": "1.0",
                    "url": archive_path.as_uri(),
                    "sha256": sha256_override or sha256,
                    "strip_components": 1,
                }
            ]
        }
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf8")
    return manifest_path, archive_path


def test_right_sum_extracts_the_archive(tmp_path: Path) -> None:
    manifest_path, _ = _make_manifest(tmp_path)
    target = tmp_path / "target"

    exit_code = script.main(
        [
            "--platform",
            "linux64",
            "--target",
            str(target),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--manifest",
            str(manifest_path),
        ]
    )

    assert exit_code == 0
    assert (target / "tools" / "tool" / "readme.txt").read_text(
        encoding="utf8"
    ) == "hello"
    assert os.access(target / "tools" / "tool" / "tool", os.X_OK)


def test_wrong_sum_is_refused_without_extraction(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path, _ = _make_manifest(tmp_path, sha256_override="0" * 64)
    target = tmp_path / "target"

    exit_code = script.main(
        [
            "--platform",
            "linux64",
            "--target",
            str(target),
            "--manifest",
            str(manifest_path),
        ]
    )

    assert exit_code != 0
    assert "wrong SHA-256 sum" in capsys.readouterr().err
    assert not (target / "tools").exists()


def test_unsafe_path_in_the_archive_is_refused(tmp_path: Path) -> None:
    archive_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("tool/../../escape.txt", "x")
    tool = {"name": "tool", "version": "1", "strip_components": 1}

    with pytest.raises(script.FetchError):
        script.extract_archive(tool, archive_path, tmp_path / "target")

    assert not (tmp_path / "escape.txt").exists()
    assert not (tmp_path / "target" / "tools" / "tool").exists()


def test_manifest_has_the_tools_of_each_platform() -> None:
    linux_names = {
        t_["name"] for t_ in script.load_tools(script.MANIFEST_PATH, "linux64")
    }
    windows_names = {
        t_["name"] for t_ in script.load_tools(script.MANIFEST_PATH, "win64")
    }

    assert linux_names == {"chrome-headless-shell", "chromedriver"}
    assert windows_names == {"chrome-headless-shell", "chromedriver", "mingit"}
