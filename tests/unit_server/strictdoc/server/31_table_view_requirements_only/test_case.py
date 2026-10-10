import re
from pathlib import Path

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfig, ProjectConfigLoader
from strictdoc.server.app import create_app

PATH_TO_THIS_TEST_FOLDER = Path(__file__).parent


def _client(tmp_path: Path, content: str = "") -> TestClient:
    input_path = tmp_path / "input"
    input_path.mkdir()
    source = (PATH_TO_THIS_TEST_FOLDER / "document.sdoc").read_text(
        encoding="utf8"
    )
    if content:
        source = content
    (input_path / "document.sdoc").write_text(source, encoding="utf8")
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
    project_config: ProjectConfig = (
        ProjectConfigLoader.load_using_server_config(server_config)
    )
    return TestClient(create_app(project_config=project_config))


def _rows(page: str):
    soup = BeautifulSoup(page, "html.parser")
    return soup.select("table.content-view-table tbody tr[data-row-type]")


def test_001_the_table_view_lists_only_the_requirements(tmp_path):
    client = _client(tmp_path)
    response = client.get("/input/document-TABLE.html")
    assert response.status_code == 200
    rows = _rows(response.text)
    assert [row["data-row-type"] for row in rows] == [
        "REQUIREMENT",
        "REQUIREMENT",
    ]
    assert [row["data-node-mid"] for row in rows] == [
        "a5c6b14d5ee443149687fb9be69a7ede",
        "b6d7c25e6ff5541a9798c8af7bf8afef",
    ]
    # The table of contents next to it still lists the sections.
    table_text = (
        BeautifulSoup(response.text, "html.parser")
        .select_one("table.content-view-table")
        .get_text()
    )
    assert "A free paragraph" not in table_text
    assert "First section" not in table_text
    assert "The system shall start." in table_text


def test_002_the_add_menu_offers_no_section_or_text(tmp_path):
    client = _client(tmp_path)
    page = client.get("/input/document-TABLE.html").text
    assert "table-add-node-action-requirement-" in page
    assert not re.search(r"table-add-node-action-(section|text)-", page)


def test_003_a_document_without_requirement_shows_the_placeholder(tmp_path):
    only_text = (PATH_TO_THIS_TEST_FOLDER / "document.sdoc").read_text(
        encoding="utf8"
    )
    only_text = only_text[: only_text.index("[REQUIREMENT]")] + "[[/SECTION]]\n"
    client = _client(tmp_path, only_text)
    page = client.get("/input/document-TABLE.html").text
    assert "has no requirements" in page
    assert _rows(page) == []


def test_004_the_document_view_is_not_affected(tmp_path):
    client = _client(tmp_path)
    page = client.get("/input/document.html").text
    assert "A free paragraph" in page
    assert "First section" in page


def test_005_each_section_keeps_an_anchor_for_the_table_of_contents(tmp_path):
    client = _client(tmp_path)
    soup = BeautifulSoup(
        client.get("/input/document-TABLE.html").text, "html.parser"
    )
    anchor_rows = soup.select("tr.content-view__section-anchor-TR")
    assert len(anchor_rows) == 1
    anchor = anchor_rows[0].find("sdoc-anchor")
    assert anchor is not None
    # The anchor is placed just before the first requirement of the section.
    next_row = anchor_rows[0].find_next_sibling("tr")
    assert next_row["data-node-mid"] == "a5c6b14d5ee443149687fb9be69a7ede"
    # It is not a data row: the row toolbar, sorting and counting ignore it.
    assert anchor_rows[0].get("data-row-type") is None
