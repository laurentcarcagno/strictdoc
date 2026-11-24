"""
The application does not offer the comparison of Git revisions (DIFF), even
for a project that declares the feature.

@relation(SDOC-SRS-1248, scope=file)
"""

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from strictdoc.core.project_config import ProjectConfig, ProjectFeature
from strictdoc.features.desktop.local_server import (
    COMPARISON_PATHS,
    create_desktop_project_config,
    create_project_application,
)

CONFIGURATION = (
    "from strictdoc.core.project_config import ProjectConfig\n"
    "def create_config():\n"
    "    return ProjectConfig(\n"
    '        project_title="P",\n'
    '        project_features=["DIFF", "SEARCH"],\n'
    "    )\n"
)


def _create_config(
    root: Path, monkeypatch: pytest.MonkeyPatch, *, declares_diff: bool
) -> ProjectConfig:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(root / "xdg-config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(root / "xdg-cache"))
    monkeypatch.setenv("XDG_DATA_HOME", str(root / "xdg-data"))
    monkeypatch.delenv("STRICTDOC_AUTH_MODE", raising=False)
    project_path = root / "project"
    project_path.mkdir()
    (project_path / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: Doc\n")
    if declares_diff:
        (project_path / "strictdoc_config.py").write_text(CONFIGURATION)
    return create_desktop_project_config(
        input_path=str(project_path), port=None
    )


def test_001_the_feature_diff_is_removed_from_a_project_that_declares_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _create_config(tmp_path, monkeypatch, declares_diff=True)

    assert ProjectFeature.DIFF not in config.project_features
    assert config.is_activated_diff() is False
    # The other features of the project stay.
    assert ProjectFeature.SEARCH in config.project_features


def test_002_the_pages_of_the_comparison_answer_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _create_config(tmp_path, monkeypatch, declares_diff=True)
    application = create_project_application(config)
    client = TestClient(application)

    assert COMPARISON_PATHS == ("/diff", "/diff_result")
    for path_ in COMPARISON_PATHS:
        assert client.get(path_).status_code == 404
        assert (
            client.get(
                path_, params={"left_revision": "a", "right_revision": "b"}
            ).status_code
            == 404
        )
    # The document pages are served.
    assert client.get("/").status_code == 200


def test_003_a_project_that_does_not_declare_the_feature_has_the_same_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _create_config(tmp_path, monkeypatch, declares_diff=False)
    client = TestClient(create_project_application(config))

    for path_ in COMPARISON_PATHS:
        assert client.get(path_).status_code == 404
