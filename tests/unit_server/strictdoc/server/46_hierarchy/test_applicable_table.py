import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfigLoader
from strictdoc.server.app import create_app
from tests.support.hierarchy_fixture import ADMIN, SOFTWARE_DOC, write_project

PROFILE = """from strictdoc.backend.docx.docx_profile import (
    DocxProfile,
    DocxRequirementTable,
)


def create_profile():
    return DocxProfile(
        heading_styles={"Heading1": 1},
        requirement_table=DocxRequirementTable(
            id_style="ReqId",
            title_style="ReqTitle",
            meta_rows={},
            text_style="ReqText",
            note_label="Note",
        ),
        applicable_documents_table=TABLE,
    )
"""


def _client(root: Path, table: bool, applicable: bool = True):
    input_path = root / "input"
    write_project(input_path)
    (input_path / "profile.py").write_text(
        PROFILE.replace("TABLE", str(table)), encoding="utf8"
    )
    config = ProjectConfigLoader.load_using_server_config(
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
    config.project_features.append("DOCX")
    config.docx_profile = "profile.py"
    if applicable:
        config.applicable_documents = {"DA1": "da", "DA9": "inputs/none"}
    config.auth_mode = "proxy"
    config.trusted_proxies = ["10.89.2.0/24"]
    config.roles = {"administrator": ["t-admins"]}
    return TestClient(
        create_app(project_config=config),
        client=("10.89.2.7", 40000),
        raise_server_exceptions=False,
    )


def _document_xml(content: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(content)) as package_:
        xml = package_.read("word/document.xml").decode("utf8")
    ET.fromstring(xml)
    return xml


def _export(client) -> str:
    response = client.post(
        "/docx/export", data={"document_mid": SOFTWARE_DOC}, headers=ADMIN
    )
    assert response.status_code == 200, response.text
    return _document_xml(response.content)


def _texts(xml: str):
    return re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)


def test_001_a_fresh_export_starts_with_the_applicable_documents(tmp_path):
    xml = _export(_client(tmp_path, table=True))
    texts = _texts(xml)
    assert "Applicable documents" in texts
    for header in ("Ref", "Title", "Reference", "Issuer", "Revision", "Date"):
        assert header in texts
    for value in ("DA1", "Customer specification", "SPEC-1", "Customer", "B"):
        assert value in texts
    # The table comes before the requirements of the document.
    assert xml.index("<w:tbl>") < xml.index("SW-1")
    # A name that matches no document is left out.
    assert "DA9" not in texts


def test_002_the_table_is_off_by_default(tmp_path):
    texts = _texts(_export(_client(tmp_path, table=False)))
    assert "Applicable documents" not in texts


def test_003_without_applicable_documents_there_is_no_table(tmp_path):
    texts = _texts(_export(_client(tmp_path, table=True, applicable=False)))
    assert "Applicable documents" not in texts
