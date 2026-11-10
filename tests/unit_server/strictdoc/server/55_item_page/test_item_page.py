"""
@relation(SDOC-SRS-213, scope=file)
"""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfig
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
    return TestClient(create_app(project_config=project_config))


def test_001_the_content_tab_shows_the_fields(client: TestClient) -> None:
    response = client.get("/item/REQ-2")

    assert response.status_code == 200
    assert 'data-testid="item-title"' in response.text
    assert "Child statement." in response.text
    assert 'data-testid="app-screen"' in response.text
    assert 'data-testid="item-back-to-document"' in response.text
    assert "#REQ-2" in response.text


def test_002_the_links_tab_groups_by_role(client: TestClient) -> None:
    response = client.get("/item/REQ-2?tab=links")

    assert response.status_code == 200
    assert response.text.count('data-testid="item-link-group"') == 1
    assert 'href="/item/REQ-1"' in response.text

    parent = client.get("/item/REQ-1?tab=links")
    assert 'href="/item/REQ-2"' in parent.text


def test_003_the_links_can_be_filtered_by_role(client: TestClient) -> None:
    response = client.get("/item/REQ-2?tab=links&role=child:Child")

    assert response.status_code == 200
    assert 'data-testid="item-link-group"' not in response.text


def test_004_disabled_tabs_say_why(client: TestClient) -> None:
    page = client.get("/item/REQ-1").text
    assert 'aria-disabled="true"' in page
    assert "The comments are not activated." in page

    history = client.get("/item/REQ-1?tab=history").text
    assert "Configuration management is not activated" in history


def test_005_an_unknown_item_is_not_found(client: TestClient) -> None:
    assert client.get("/item/NOPE").status_code == 404


def test_006_the_stable_link_still_redirects(client: TestClient) -> None:
    response = client.get("/UID/REQ-1", follow_redirects=False)

    assert response.status_code == 302
