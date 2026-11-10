"""
@relation(SDOC-SRS-215, scope=file)
"""

import subprocess
from pathlib import Path
from typing import Tuple

from fastapi.testclient import TestClient

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import (
    ProjectConfig,
    ProjectConfigLoader,
    ProjectFeature,
)
from strictdoc.features.git_config.config import GitConfig
from strictdoc.server.app import create_app

VERSION_A1 = """[DOCUMENT]
TITLE: Versions

[REQUIREMENT]
UID: REQ-1
TITLE: First
STATEMENT: Alpha.

[REQUIREMENT]
UID: REQ-2
TITLE: Second
STATEMENT: Beta.
"""

VERSION_A2 = """[DOCUMENT]
TITLE: Versions

[REQUIREMENT]
UID: REQ-1
TITLE: First
STATEMENT: Alpha, reworded.

[REQUIREMENT]
UID: REQ-3
TITLE: Third
STATEMENT: Gamma.
"""


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _client(root: Path, feature: bool = True) -> Tuple[TestClient, str]:
    input_path = root / "input"
    input_path.mkdir()
    document = input_path / "doc.sdoc"
    _git(root, "init", "-q", "-b", "master")
    _git(root, "config", "user.name", "i")
    _git(root, "config", "user.email", "i@e")
    document.write_text(VERSION_A1, encoding="utf8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "first version")
    _git(root, "tag", "A1")
    document.write_text(VERSION_A2, encoding="utf8")
    _git(root, "commit", "-q", "-am", "second version")
    _git(root, "tag", "A2")
    config: ProjectConfig = ProjectConfigLoader.load_using_server_config(
        ServerCommandConfig(
            debug=False,
            command="server",
            input_path=str(input_path),
            output_path=str(root / "output"),
            config=None,
            reload=False,
            host="127.0.0.1",
            port=8001,
        )
    )
    if feature:
        config.project_features.append(ProjectFeature.GIT)
        config.git = GitConfig()
    app = create_app(project_config=config)
    index = app.state.project_context.export_action.traceability_index
    document_mid = index.document_tree.document_list[
        0
    ].reserved_mid.get_string_value()
    client = TestClient(app)
    return client, document_mid


def test_001_the_screens_need_the_git_feature(tmp_path: Path) -> None:
    client, document_mid = _client(tmp_path, feature=False)

    assert client.get(f"/versions/{document_mid}").status_code == 412


def test_002_the_tags_are_listed_latest_first(tmp_path: Path) -> None:
    client, document_mid = _client(tmp_path)

    page = client.get(f"/versions/{document_mid}").text

    table = page.split('data-testid="versions-table"')[1]
    assert table.index(">A2<") < table.index(">A1<")
    assert "second version" in page
    assert f"/versions/{document_mid}/A1" in page
    assert 'data-testid="versions-compare-form"' in page


def test_003_a_version_shows_the_items_as_they_were(tmp_path: Path) -> None:
    client, document_mid = _client(tmp_path)

    page = client.get(f"/versions/{document_mid}/A1").text

    assert 'data-testid="version-error"' not in page, page.split(
        'data-testid="version-error"'
    )[1][:300]
    assert "REQ-2" in page
    assert "REQ-3" not in page
    assert "Alpha." in page
    assert "Alpha, reworded." not in page


def test_004_the_comparison_lists_the_differences(tmp_path: Path) -> None:
    client, document_mid = _client(tmp_path)

    page = client.get(
        f"/versions/{document_mid}/compare?from_tag=A1&to_tag=A2"
    ).text

    assert "1 added, 1 removed, 1 changed, 0 unchanged" in " ".join(
        page.split()
    )
    assert "REQ-3" in page.split('data-testid="compare-added"')[1]
    assert "REQ-2" in page.split('data-testid="compare-removed"')[1]
    assert "+ Alpha, reworded." in page
    assert "- Alpha." in page


def test_005_unknown_tag_and_document_are_not_found(tmp_path: Path) -> None:
    client, document_mid = _client(tmp_path)

    assert client.get(f"/versions/{document_mid}/nope").status_code == 404
    assert client.get("/versions/unknown").status_code == 404


def test_006_a_missing_tag_says_so_instead_of_failing(tmp_path: Path) -> None:
    client, document_mid = _client(tmp_path)

    page = client.get(f"/versions/{document_mid}/B9").text

    assert 'data-testid="version-error"' in page
