import html
from pathlib import Path
from typing import Dict

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from httpx import Response

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.image_formats import MAX_IMAGE_SIZE_BYTES
from strictdoc.core.project_config import ProjectConfig, ProjectConfigLoader
from strictdoc.server.app import create_app

PATH_TO_THIS_TEST_FOLDER = Path(__file__).parent
DOCUMENT_MID = "398e37d756ea406f87ca83ec8e29c178"
TEXT_MID = "7a8e7ed4f4a94e9e8a8d7a0c21d1d001"
R1_MID = "a5c6b14d5ee443149687fb9be69a7ede"
R2_MID = "b6d7c25e6ff5541a9798c8af7bf8afef"

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
    b"\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _client(tmp_path: Path, markup: str = "Markdown") -> TestClient:
    input_path = tmp_path / "input"
    input_path.mkdir(parents=True)
    source = (PATH_TO_THIS_TEST_FOLDER / "document.sdoc").read_text(
        encoding="utf8"
    )
    if markup != "Markdown":
        source = source.replace("MARKUP: Markdown", f"MARKUP: {markup}")
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


def _edit_form(client: TestClient, node_mid: str) -> BeautifulSoup:
    response = client.get(
        "/actions/document/edit_requirement",
        params={"node_id": node_mid, "context_document_mid": DOCUMENT_MID},
    )
    assert response.status_code == 200
    return BeautifulSoup(response.text, "html.parser")


def _form_values(form: BeautifulSoup) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for input_ in form.find_all("input"):
        if input_.get("name") and input_.get("type") != "file":
            values[input_["name"]] = input_.get("value", "")
    for textarea in form.find_all("textarea"):
        if textarea.get("name"):
            # bs4 leaves the text of a textarea out of .text.
            values[textarea["name"]] = html.unescape(textarea.decode_contents())
    return values


def _statement_field_name(form: BeautifulSoup) -> str:
    editable = form.find(attrs={"data-testid": "form-field-STATEMENT"})
    assert editable is not None
    return editable.parent.find("textarea")["name"]


def _save(client: TestClient, node_mid: str, statement: str) -> Response:
    form = _edit_form(client, node_mid)
    values = _form_values(form)
    values[_statement_field_name(form)] = statement
    return client.post("/actions/document/update_requirement", data=values)


def _sdoc(tmp_path: Path) -> str:
    return (tmp_path / "input" / "document.sdoc").read_text(encoding="utf8")


def test_001_a_line_starting_with_the_closing_marker_is_rejected(tmp_path):
    client = _client(tmp_path)
    before = _sdoc(tmp_path)
    for node_mid in (R1_MID, TEXT_MID):
        response = _save(client, node_mid, "First line\n<<<\nsecond line")
        assert response.status_code == 422, node_mid
        assert "marks the end of a multiline field" in response.text
    assert _sdoc(tmp_path) == before


def test_002_an_indented_marker_is_accepted(tmp_path):
    client = _client(tmp_path)
    response = _save(client, R1_MID, "First line\n  <<< not at the start")
    assert response.status_code == 200
    assert "  <<< not at the start" in _sdoc(tmp_path)


def test_003_markdown_with_a_table_and_a_link_is_saved_unchanged(tmp_path):
    client = _client(tmp_path)
    statement = (
        "Start, see [LINK: R-2].\n\n"
        "| a | b |\n| --- | --- |\n| 1 | 2 |\n\n"
        "- one\n- two\n"
    )
    response = _save(client, R1_MID, statement)
    assert response.status_code == 200
    saved = _sdoc(tmp_path)
    assert "Start, see [LINK: R-2]." in saved
    assert "| a | b |\n| --- | --- |\n| 1 | 2 |" in saved
    assert "\\[LINK" not in saved

    page = client.get("/input/document.html").text
    assert "<table>" in page
    assert 'href="' in page and "R-2" in page


def test_004_an_uploaded_image_is_stored_and_rendered(tmp_path):
    client = _client(tmp_path)
    upload = client.post(
        f"/actions/document/upload_asset?document_mid={DOCUMENT_MID}"
        f"&requirement_mid={R1_MID}",
        files=[("uploaded_files", ("pic.png", PNG, "image/png"))],
    )
    assert upload.status_code == 200
    uri = upload.json()["images"]["pic.png"]
    assert uri == f"./_assets/{R1_MID}/pic.png"
    assert (tmp_path / "input" / "_assets" / R1_MID / "pic.png").is_file()

    assert _save(client, R1_MID, f"Look:\n\n![pic]({uri})").status_code == 200
    assert f"![pic]({uri})" in _sdoc(tmp_path)
    page = client.get("/input/document.html").text
    assert f'<img src="{uri}"' in page


def test_005_an_image_larger_than_the_limit_is_refused(tmp_path):
    client = _client(tmp_path)
    response = client.post(
        f"/actions/document/upload_asset?document_mid={DOCUMENT_MID}"
        f"&requirement_mid={R1_MID}",
        files=[
            (
                "uploaded_files",
                ("big.png", b"0" * (MAX_IMAGE_SIZE_BYTES + 1), "image/png"),
            )
        ],
    )
    assert response.status_code == 400
    assert "larger than 10 MB" in response.json()["detail"]
    assert not (tmp_path / "input" / "_assets" / R1_MID / "big.png").exists()


def test_006_an_untouched_node_saved_again_does_not_change_the_file(tmp_path):
    client = _client(tmp_path)
    form = _edit_form(client, R2_MID)
    values = _form_values(form)
    before = _sdoc(tmp_path)
    response = client.post("/actions/document/update_requirement", data=values)
    assert response.status_code == 200
    assert "See [LINK: R-1] for the start." in _sdoc(tmp_path)
    assert _sdoc(tmp_path).count("[LINK: R-1]") == before.count("[LINK: R-1]")


def test_007_markdown_documents_get_the_wysiwyg_editor_for_the_content(
    tmp_path,
):
    client = _client(tmp_path)
    for node_mid in (R1_MID, TEXT_MID):
        form = _edit_form(client, node_mid)
        editor = form.find("sdoc-markdown-editor")
        assert editor is not None, node_mid
        assert editor["data-testid"] == "form-field-STATEMENT"
        assert "upload_asset" in editor["data-upload-url"]
        assert f"requirement_mid={node_mid}" in editor["data-upload-url"]
        assert editor.parent.find("textarea")["hidden"] is not None
        assert (
            form.find(
                "sdoc-contenteditable",
                attrs={"data-testid": "form-field-STATEMENT"},
            )
            is None
        )

    # The plain editor remains for the other multiline fields.
    form = _edit_form(client, R1_MID)
    rationale = form.find(attrs={"data-testid": "form-field-RATIONALE"})
    assert rationale.name == "sdoc-contenteditable"


def test_008_the_editor_textarea_carries_the_markdown_unchanged(tmp_path):
    client = _client(tmp_path)
    form = _edit_form(client, R2_MID)
    textarea = form.find("sdoc-markdown-editor").parent.find("textarea")
    assert html.unescape(textarea.decode_contents()).strip() == (
        "See [LINK: R-1] for the start."
    )


def test_009_other_markups_keep_the_plain_editor(tmp_path):
    for markup in ("RST", "Text", "HTML"):
        client = _client(tmp_path / markup, markup)
        form = _edit_form(client, R1_MID)
        assert form.find("sdoc-markdown-editor") is None, markup
        statement = form.find(attrs={"data-testid": "form-field-STATEMENT"})
        assert statement.name == "sdoc-contenteditable", markup
        page = client.get("/input/document.html").text
        assert "milkdown" not in page, markup


def test_010_the_page_loads_the_bundle_only_for_markdown(tmp_path):
    client = _client(tmp_path)
    page = client.get("/input/document.html").text
    assert "milkdown/milkdown.js" in page
    assert "milkdown/milkdown.css" in page
    assert client.get("/_static/milkdown/milkdown.js").status_code == 200
