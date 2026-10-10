import io
import os
import re
import shutil
import struct
import zipfile
import zlib
from typing import Dict, Optional

from fastapi.testclient import TestClient

from strictdoc.backend.docx.docx_web_service import check_upload
from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfig, ProjectFeature
from strictdoc.server.app import create_app
from tests.unit.strictdoc.backend.docx.docx_builder import (
    cell,
    paragraph,
    row,
    table,
    write_docx,
)

PATH_TO_THIS_TEST_FOLDER = os.path.dirname(os.path.abspath(__file__))


def _requirement_table(uid: str, text: str) -> str:
    return table(
        row(cell(paragraph(uid, style="ReqId"))),
        row(cell(paragraph("Title " + uid, style="ReqTitle"))),
        row(cell(paragraph("Version:")), cell(paragraph("V1"))),
        row(cell(paragraph(text, style="ReqText"))),
        row(cell(paragraph("Note"))),
    )


def _word_file(path: str, *tables: str) -> bytes:
    write_docx(path, [paragraph("Imported", style="Heading1"), *tables])
    with open(path, "rb") as file_:
        return file_.read()


def _client(
    tmp_path,
    activated: bool = True,
    with_profile: bool = True,
    profile: str = "profile.py",
    extra_files: Optional[Dict[str, bytes]] = None,
) -> TestClient:
    input_dir = os.path.join(str(tmp_path), "input")
    shutil.copytree(
        PATH_TO_THIS_TEST_FOLDER,
        input_dir,
        ignore=shutil.ignore_patterns("test_case.py", "__pycache__"),
    )
    for relative_path_, content_ in (extra_files or {}).items():
        target = os.path.join(input_dir, relative_path_)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as file_:
            file_.write(content_)
    server_config = ServerCommandConfig(
        debug=False,
        command="server",
        input_path=input_dir,
        output_path=os.path.join(str(tmp_path), "output"),
        config=None,
        reload=False,
        host="127.0.0.1",
        port=8001,
    )
    project_config: ProjectConfig = ProjectConfig.default_config()
    if activated:
        project_config.project_features.append(ProjectFeature.DOCX)
    if with_profile:
        project_config.docx_profile = os.path.join(input_dir, profile)
    project_config.integrate_server_config(server_config)
    return TestClient(create_app(project_config=project_config))


def _upload(name: str, data: bytes):
    return (name, data, "application/octet-stream")


def test_001_routes_answer_412_when_the_feature_is_off(tmp_path):
    client = _client(tmp_path, activated=False)
    assert (
        client.get("/actions/project_index/import_docx_form").status_code == 412
    )
    assert (
        client.get("/actions/project_index/export_docx_form").status_code == 412
    )
    response = client.post(
        "/actions/project_index/import_docx",
        files={"docx_file": _upload("a.docx", b"x")},
    )
    assert response.status_code == 412


def test_002_the_dialogs_open(tmp_path):
    client = _client(tmp_path)
    response = client.get("/actions/project_index/import_docx_form")
    assert response.status_code == 200
    assert "turbo-stream" in response.text
    assert "/actions/project_index/import_docx_preview" in response.text
    response = client.get("/actions/project_index/export_docx_form")
    assert response.status_code == 200
    assert "<option" in response.text and "Sample" in response.text


def test_003_the_tree_menu_offers_the_actions(tmp_path):
    client = _client(tmp_path)
    page = client.get("/index.html").text
    assert "tree-import-docx-action" in page
    assert "tree-export-docx-action" in page
    off = _client(tmp_path / "off", activated=False).get("/index.html").text
    assert "tree-import-docx-action" not in off


def test_004_preview_shows_the_report_and_writes_nothing(tmp_path):
    client = _client(tmp_path)
    data = _word_file(
        os.path.join(str(tmp_path), "Spec.docx"),
        _requirement_table("W-1", "The system shall stop."),
    )
    response = client.post(
        "/actions/project_index/import_docx_preview",
        files={"docx_file": _upload("Spec.docx", data)},
    )
    assert response.status_code == 200
    assert "Profile:" in response.text and "profile.py" in response.text
    assert "Word import: 1 requirement(s)" in response.text
    assert "Nothing was written" in response.text
    assert not os.path.exists(os.path.join(str(tmp_path), "input", "Spec.sdoc"))


def test_005_import_writes_the_sdoc_and_the_tree_shows_it(tmp_path):
    client = _client(tmp_path)
    data = _word_file(
        os.path.join(str(tmp_path), "Spec.docx"),
        _requirement_table("W-1", "The system shall stop."),
    )
    response = client.post(
        "/actions/project_index/import_docx",
        files={"docx_file": _upload("Spec.docx", data)},
    )
    assert response.status_code == 200
    assert "frame_project_tree" in response.text
    written = os.path.join(str(tmp_path), "input", "Spec.sdoc")
    with open(written, encoding="utf8") as file_:
        assert "The system shall stop." in file_.read()
    assert "Spec" in client.get("/index.html").text


def test_006_a_second_import_merges_by_uid(tmp_path):
    client = _client(tmp_path)
    path = os.path.join(str(tmp_path), "Spec.docx")
    first = _word_file(path, _requirement_table("W-1", "First text."))
    second = _word_file(path, _requirement_table("W-1", "Second text."))
    client.post(
        "/actions/project_index/import_docx",
        files={"docx_file": _upload("Spec.docx", first)},
    )
    response = client.post(
        "/actions/project_index/import_docx_preview",
        files={"docx_file": _upload("Spec.docx", second)},
    )
    assert "1 changed" in response.text
    assert "W-1 (STATEMENT)" in response.text


def test_007_an_upload_that_is_not_word_gives_an_error_in_the_dialog(tmp_path):
    client = _client(tmp_path)
    response = client.post(
        "/actions/project_index/import_docx_preview",
        files={"docx_file": _upload("a.docx", b"not a zip")},
    )
    assert response.status_code == 422
    assert "not a Word document" in response.text
    response = client.post(
        "/actions/project_index/import_docx",
        files={"docx_file": _upload("a.docx", b"")},
    )
    assert response.status_code == 422
    assert "empty" in response.text


def _document_mid(client: TestClient) -> str:
    form = client.get("/actions/project_index/export_docx_form").text
    return form.split('<option value="')[1].split('"')[0]


def test_008_export_downloads_a_new_word_file(tmp_path):
    client = _client(tmp_path)
    response = client.post(
        "/docx/export", data={"document_mid": _document_mid(client)}
    )
    assert response.status_code == 200
    assert "wordprocessingml.document" in response.headers["content-type"]
    assert 'filename="sample.docx"' in response.headers["content-disposition"]
    check_upload(response.content)
    assert b"R-1" in _document_xml(response.content)


def _document_xml(content: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(content)) as package_:
        return package_.read("word/document.xml")


def test_009_update_previews_and_downloads_tracked_changes(tmp_path):
    client = _client(tmp_path)
    mid = _document_mid(client)
    base = client.post("/docx/export", data={"document_mid": mid}).content
    # Same model: nothing to change.
    response = client.post(
        "/actions/project_index/export_docx_preview",
        data={"document_mid": mid},
        files={"base_file": _upload("base.docx", base)},
    )
    assert "0 added, 0 changed, 0 deleted, 1 unchanged" in response.text
    # An empty base means a fresh document.
    response = client.post(
        "/actions/project_index/export_docx_preview", data={"document_mid": mid}
    )
    assert "new Word document" in response.text
    # The base lacks the requirement: the update adds it.
    empty_base = _word_file(os.path.join(str(tmp_path), "empty.docx"))
    response = client.post(
        "/docx/export",
        data={"document_mid": mid},
        files={"base_file": _upload("empty.docx", empty_base)},
    )
    assert response.status_code == 200
    assert (
        'filename="sample_updated.docx"'
        in response.headers["content-disposition"]
    )
    assert b"<w:ins " in _document_xml(response.content)


def test_010_export_errors_are_clear(tmp_path):
    client = _client(tmp_path)
    response = client.post(
        "/actions/project_index/export_docx_preview",
        data={"document_mid": "unknown"},
    )
    assert response.status_code == 422
    assert "Select a document" in response.text
    mid = _document_mid(client)
    response = client.post(
        "/docx/export",
        data={"document_mid": mid},
        files={"base_file": _upload("x.docx", b"junk")},
    )
    assert response.status_code == 422
    assert "not a Word" in response.text
    assert (
        client.post("/docx/export", data={"document_mid": "x"}).status_code
        == 404
    )


def test_011_a_file_with_no_requirement_is_refused_unless_allowed(tmp_path):
    client = _client(tmp_path, with_profile=False)
    data = _word_file(
        os.path.join(str(tmp_path), "Spec.docx"),
        _requirement_table("W-1", "The system shall stop."),
    )
    files = {"docx_file": _upload("Spec.docx", data)}
    preview = client.post(
        "/actions/project_index/import_docx_preview", files=files
    )
    assert "Profile: generic" in preview.text
    assert "WARNING: No requirement found" in preview.text
    written = os.path.join(str(tmp_path), "input", "Spec.sdoc")

    refused = client.post("/actions/project_index/import_docx", files=files)
    assert refused.status_code == 422
    assert "Nothing was imported" in refused.text
    assert not os.path.exists(written)

    allowed = client.post(
        "/actions/project_index/import_docx",
        files=files,
        data={"allow_empty": "true"},
    )
    assert allowed.status_code == 200
    assert os.path.exists(written)


def test_012_a_markdown_profile_imports_markdown_and_exports_it_back(tmp_path):
    client = _client(tmp_path, profile="profile_markdown.py")
    data = _word_file(
        os.path.join(str(tmp_path), "Spec.docx"),
        _requirement_table("W-1", "Use snake_case and 1 &lt; 2."),
    )
    response = client.post(
        "/actions/project_index/import_docx",
        files={"docx_file": _upload("Spec.docx", data)},
    )
    assert response.status_code == 200
    with open(os.path.join(str(tmp_path), "input", "Spec.sdoc")) as file_:
        written = file_.read()
    assert "MARKUP: Markdown" in written
    assert "Use snake_case and 1 \\< 2." in written

    form = client.get("/actions/project_index/export_docx_form").text
    mids = [part.split('"')[0] for part in form.split('<option value="')[1:]]
    exported = [
        client.post("/docx/export", data={"document_mid": mid_})
        for mid_ in mids
    ]
    assert any(b"1 &lt; 2." in _document_xml(r.content) for r in exported)


def test_013_the_export_embeds_the_images_of_a_markdown_document(tmp_path):
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return (
            struct.pack(">I", len(data))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\x00" + b"\x10\x80\x20" * 4) * 4))
        + chunk(b"IEND", b"")
    )
    document = (
        "[DOCUMENT]\nTITLE: Images\nOPTIONS:\n  MARKUP: Markdown\n\n"
        "[REQUIREMENT]\nUID: I-1\nSTATEMENT: >>>\nLook:\n\n"
        "![p](./_assets/pic.png)\n<<<\n"
    )
    client = _client(
        tmp_path,
        profile="profile_markdown.py",
        extra_files={
            "images.sdoc": document.encode("utf8"),
            "_assets/pic.png": png,
        },
    )
    form = client.get("/actions/project_index/export_docx_form").text
    options = re.findall(r'<option value="([^"]+)">([^<]+)</option>', form)
    mid = next(mid_ for mid_, title_ in options if title_ == "Images")
    response = client.post("/docx/export", data={"document_mid": mid})
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as package_:
        media = [n for n in package_.namelist() if n.startswith("word/media/")]
        assert len(media) == 1
        assert package_.read(media[0]) == png
        assert b"<w:drawing>" in package_.read("word/document.xml")
