"""
A document without a MARKUP option is Markdown: its pages load the visual
editor of the fields, whose element the forms use.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfigLoader
from strictdoc.server.app import create_app

NO_MARKUP = """[DOCUMENT]
TITLE: No markup option

[TEXT]
STATEMENT: >>>
Hello.
<<<
"""

HTML_MARKUP = """[DOCUMENT]
TITLE: In HTML
OPTIONS:
  MARKUP: HTML

[TEXT]
STATEMENT: >>>
<p>Hello.</p>
<<<
"""


def _page(tmp_path: Path, text: str) -> str:
    input_path = tmp_path / "input"
    input_path.mkdir()
    (input_path / "doc.sdoc").write_text(text, encoding="utf8")
    config = ProjectConfigLoader.load_using_server_config(
        ServerCommandConfig(
            debug=False,
            command="server",
            input_path=str(input_path),
            output_path=str(tmp_path / "output"),
            config=None,
            reload=False,
            host="127.0.0.1",
            port=8001,
        )
    )
    client = TestClient(create_app(project_config=config))
    return client.get("/input/doc.html").text


def test_001_a_document_without_markup_loads_the_markdown_editor(
    tmp_path: Path,
) -> None:
    page = _page(tmp_path, NO_MARKUP)

    assert "milkdown/milkdown.js" in page


def test_002_a_document_in_html_does_not_load_the_markdown_editor(
    tmp_path: Path,
) -> None:
    page = _page(tmp_path, HTML_MARKUP)

    assert "Hello" in page
    assert "milkdown/milkdown.js" not in page
