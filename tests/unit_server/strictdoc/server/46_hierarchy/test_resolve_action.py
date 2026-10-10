from pathlib import Path

from fastapi.testclient import TestClient

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfigLoader
from strictdoc.server.app import create_app
from tests.support.hierarchy_fixture import ADMIN, AUTHOR, write_project

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
            meta_rows={"Linked Req:": "LINKED_REQ"},
            text_style="ReqText",
            note_label="Note",
            relation_fields=["LINKED_REQ"],
        ),
    )
"""

DOCUMENT = """[DOCUMENT]
MID: 9999999999999999999999999999999a
TITLE: Flight requirements
OPTIONS:
  ENABLE_MID: True

[GRAMMAR]
ELEMENTS:
- TAG: REQUIREMENT
  FIELDS:
  - TITLE: MID
    TYPE: String
    REQUIRED: False
  - TITLE: UID
    TYPE: String
    REQUIRED: False
  - TITLE: LINKED_REQ
    TYPE: String
    REQUIRED: False
  - TITLE: TITLE
    TYPE: String
    REQUIRED: False
  - TITLE: STATEMENT
    TYPE: String
    REQUIRED: True
  RELATIONS:
  - TYPE: Parent

[REQUIREMENT]
MID: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1
UID: FLT-1
LINKED_REQ: [DA1] DA-1, DA-2 ; [DA1] DA-404
STATEMENT: >>>
The flight software shall do A.
<<<

[REQUIREMENT]
MID: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa2
UID: FLT-2
LINKED_REQ: -
STATEMENT: >>>
The flight software shall do B.
<<<
"""


def _client(root: Path, applicable=True):
    input_path = root / "input"
    write_project(input_path)
    (input_path / "flight.sdoc").write_text(DOCUMENT, encoding="utf8")
    (input_path / "profile.py").write_text(PROFILE, encoding="utf8")
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
    config.docx_profile = "profile.py"
    if applicable:
        config.applicable_documents = {"DA1": "da"}
    config.auth_mode = "proxy"
    config.trusted_proxies = ["10.89.2.0/24"]
    config.roles = {
        "administrator": ["t-admins"],
        "author": ["t-authors"],
        "reviewer": ["t-reviewers"],
        "reader": ["t-readers"],
    }
    return (
        TestClient(
            create_app(project_config=config),
            client=("10.89.2.7", 40000),
            raise_server_exceptions=False,
        ),
        input_path,
    )


def _run(client, apply):
    return client.post(
        "/actions/hierarchy/resolve_references",
        data={"apply": "true" if apply else "false"},
        headers=ADMIN,
    )


def test_001_a_preview_writes_nothing(tmp_path):
    client, input_path = _client(tmp_path)
    before = (input_path / "flight.sdoc").read_text(encoding="utf8")
    response = _run(client, apply=False)
    assert response.status_code == 200, response.text
    assert "2 link(s) to add" in response.text
    assert "DA-404" in response.text
    assert "Nothing was written." in response.text
    assert (input_path / "flight.sdoc").read_text(encoding="utf8") == before


def test_002_apply_adds_the_parent_relations_and_keeps_the_text(tmp_path):
    client, input_path = _client(tmp_path)
    response = _run(client, apply=True)
    assert response.status_code == 200, response.text
    text = (input_path / "flight.sdoc").read_text(encoding="utf8")
    assert "VALUE: DA-1" in text and "VALUE: DA-2" in text
    assert "LINKED_REQ: [DA1] DA-1, DA-2 ; [DA1] DA-404" in text
    assert "DA-404" in response.text


def test_003_a_second_run_finds_everything_linked(tmp_path):
    client, _ = _client(tmp_path)
    _run(client, apply=True)
    response = _run(client, apply=False)
    assert "0 link(s) to add" in response.text
    assert "2 already there" in response.text


def test_004_the_input_documents_are_not_touched(tmp_path):
    client, input_path = _client(tmp_path)
    before = (input_path / "da.sdoc").read_text(encoding="utf8")
    _run(client, apply=True)
    assert (input_path / "da.sdoc").read_text(encoding="utf8") == before


def test_005_only_an_administrator_may_run_it(tmp_path):
    client, _ = _client(tmp_path)
    response = client.post(
        "/actions/hierarchy/resolve_references",
        data={"apply": "true"},
        headers=AUTHOR,
    )
    assert response.status_code == 403


def test_006_without_applicable_documents_it_explains(tmp_path):
    client, _ = _client(tmp_path, applicable=False)
    response = _run(client, apply=False)
    assert response.status_code == 400
    assert "applicable_documents" in response.text
