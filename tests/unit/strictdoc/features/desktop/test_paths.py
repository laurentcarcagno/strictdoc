"""
@relation(SDOC-SRS-1225, scope=file)
"""

import os
from pathlib import Path
from typing import Any

import platformdirs
import pytest

from strictdoc.features.desktop.paths import (
    get_cache_dir,
    get_project_cache_dir,
    get_project_fingerprint,
    get_project_output_dir,
    get_project_sdoc_cache_dir,
)


@pytest.fixture(autouse=True)
def user_folders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # platformdirs reads XDG_* only on Linux, so the functions are replaced.
    def fake_folder(kind: str) -> Any:
        def get_folder(appname: str, *args: Any, **kwargs: Any) -> str:
            del args, kwargs
            return str(tmp_path / kind / appname)

        return get_folder

    monkeypatch.setattr(platformdirs, "user_cache_dir", fake_folder("cache"))
    monkeypatch.setattr(platformdirs, "user_config_dir", fake_folder("config"))
    monkeypatch.setattr(platformdirs, "user_data_dir", fake_folder("data"))
    return tmp_path


def test_001_fingerprint_is_stable(tmp_path: Path) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()

    fingerprint = get_project_fingerprint(str(project_path))

    assert fingerprint == get_project_fingerprint(str(project_path))
    assert len(fingerprint) == 16


def test_002_fingerprint_ignores_the_form_of_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_path = tmp_path / "project"
    project_path.mkdir()
    monkeypatch.chdir(tmp_path)

    assert get_project_fingerprint("project") == get_project_fingerprint(
        str(project_path)
    )
    assert get_project_fingerprint(
        os.path.join(str(project_path), "..", "project")
    ) == get_project_fingerprint(str(project_path))


def test_003_two_projects_get_two_folders(tmp_path: Path) -> None:
    first_path = tmp_path / "first"
    second_path = tmp_path / "second"

    assert get_project_fingerprint(str(first_path)) != get_project_fingerprint(
        str(second_path)
    )
    assert get_project_cache_dir(str(first_path)) != get_project_cache_dir(
        str(second_path)
    )
    assert get_project_output_dir(str(first_path)) != get_project_output_dir(
        str(second_path)
    )


def test_004_project_folders_are_in_the_cache_of_the_user(
    tmp_path: Path,
) -> None:
    project_path = str(tmp_path / "project")
    project_cache_dir = get_project_cache_dir(project_path)

    assert project_cache_dir.parent == get_cache_dir() / "projects"
    assert get_project_output_dir(project_path) == project_cache_dir / "output"
    assert get_project_sdoc_cache_dir(project_path) == (
        project_cache_dir / "_cache"
    )
    assert get_cache_dir() == tmp_path / "cache" / "StrictDoc"
