"""
@relation(SDOC-SRS-214, scope=file)
"""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfig, ProjectFeature
from strictdoc.server.app import create_app

PATH_TO_THIS_TEST_FOLDER = Path(__file__).parent


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    input_path = tmp_path / "input"
    input_path.mkdir()
    shutil.copy(PATH_TO_THIS_TEST_FOLDER / "document.sdoc", input_path)
    server_config = ServerCommandConfig(
        debug=False,
        command="server",
        input_path=str(input_path),
        output_path=str(tmp_path / "output"),
        config=None,
        reload=False,
        host="127.0.0.1",
        port=8001,
    )
    project_config = ProjectConfig.default_config()
    project_config.integrate_server_config(server_config)
    project_config.project_features.append(ProjectFeature.SEARCH)
    return TestClient(create_app(project_config=project_config))


def test_001_an_exact_uid_opens_the_item(client: TestClient) -> None:
    response = client.get("/search?q=REQ-2", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == "/item/REQ-2"


def test_002_a_text_that_is_not_a_uid_searches(client: TestClient) -> None:
    response = client.get("/search?q=Alpha", follow_redirects=False)

    assert response.status_code == 200
    assert "Parent requirement" in response.text
    assert "Child requirement" not in response.text


def test_003_the_kind_facet_keeps_one_kind(client: TestClient) -> None:
    requirements = client.get("/search?kind=requirement").text
    sections = client.get("/search?kind=section").text

    assert "Parent requirement" in requirements
    assert "Section title" not in requirements
    assert "Section title" in sections
    assert "Parent requirement" not in sections


def test_004_the_status_facet_keeps_one_status(client: TestClient) -> None:
    page = client.get("/search?status=Draft").text

    assert "Child requirement" in page
    assert "Parent requirement" not in page


def test_005_the_links_facet_uses_the_parents(client: TestClient) -> None:
    without = client.get("/search?kind=requirement&links=without_parent").text
    with_parent = client.get("/search?links=with_parent").text

    assert "Parent requirement" in without
    assert "Child requirement" not in without
    assert "Child requirement" in with_parent
    assert "Parent requirement" not in with_parent


def test_006_a_facet_and_a_text_both_apply(client: TestClient) -> None:
    page = client.get("/search?q=statement&status=Active").text

    assert "Parent requirement" in page
    assert "Child requirement" not in page


def test_007_the_status_choices_come_from_the_project(
    client: TestClient,
) -> None:
    page = client.get("/search").text

    assert 'data-testid="search-facet-status"' in page
    assert '<option value="Active"' in page
    assert '<option value="Draft"' in page
