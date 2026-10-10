"""A project with three levels: an input document, system and software."""

import html
from pathlib import Path
from typing import Dict, Optional, Tuple

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfig, ProjectConfigLoader
from strictdoc.features.hierarchy.levels import Level, validate_hierarchy
from strictdoc.server.app import create_app

LEVELS = [
    Level("input", label="Applicable documents"),
    Level("system", label="System requirements", parents=["input"]),
    Level("software", label="Software requirements", parents=["system"]),
]

INPUT_DOC = "1" * 32
SYSTEM_DOC = "2" * 32
SOFTWARE_DOC = "3" * 32
DA_1 = "a1" * 16
DA_2 = "a2" * 16
SYS_1 = "b1" * 16
SYS_2 = "b2" * 16
SW_1 = "c1" * 16
SW_2 = "c2" * 16
PROXY = ("10.89.2.7", 40000)
ROLE_GROUPS = {
    "administrator": ["t-admins"],
    "author": ["t-authors"],
    "reviewer": ["t-reviewers"],
    "reader": ["t-readers"],
}


def as_user(group: str, user: str = "u") -> Dict[str, str]:
    return {
        "X-Forwarded-Preferred-Username": user,
        "X-Forwarded-User": f"id-{user}",
        "X-Forwarded-Groups": group,
    }


ADMIN = as_user("t-admins", "adam")
AUTHOR = as_user("t-authors", "anna")
READER = as_user("t-readers", "ruth")


def _document(
    mid: str, title: str, kind: str, nodes: str, extra: str = ""
) -> str:
    return (
        f"[DOCUMENT]\nMID: {mid}\nTITLE: {title}\nOPTIONS:\n  ENABLE_MID: True\n"
        f"METADATA:\n  KIND: {kind}\n{extra}\n{nodes}"
    )


def _node(mid: str, uid: str, text: str, parent: Optional[str] = None) -> str:
    relations = (
        f"RELATIONS:\n- TYPE: Parent\n  VALUE: {parent}\n" if parent else ""
    )
    return (
        f"[REQUIREMENT]\nMID: {mid}\nUID: {uid}\nTITLE: {uid}\n"
        f"STATEMENT: >>>\n{text}\n<<<\n{relations}\n"
    )


def write_project(input_path: Path) -> None:
    input_path.mkdir(parents=True)
    (input_path / "da.sdoc").write_text(
        _document(
            INPUT_DOC,
            "Customer specification",
            "input",
            _node(DA_1, "DA-1", "The customer wants A.")
            + _node(DA_2, "DA-2", "The customer wants B."),
            "  ISSUER: Customer\n  REFERENCE: SPEC-1\n  REVISION: B\n",
        ),
        encoding="utf8",
    )
    (input_path / "system.sdoc").write_text(
        _document(
            SYSTEM_DOC,
            "System requirements",
            "system",
            _node(SYS_1, "SYS-1", "The system shall do A.", "DA-1")
            + _node(SYS_2, "SYS-2", "The system shall do B."),
        ),
        encoding="utf8",
    )
    (input_path / "software.sdoc").write_text(
        _document(
            SOFTWARE_DOC,
            "Software requirements",
            "software",
            _node(SW_1, "SW-1", "The software shall do A.", "SYS-1")
            + _node(SW_2, "SW-2", "The software shall do B."),
        ),
        encoding="utf8",
    )


def setup(
    root: Path,
    policy: str = "off",
    editable: bool = False,
    suspect: bool = False,
    hierarchy: bool = True,
) -> Tuple[TestClient, Path]:
    input_path = root / "input"
    write_project(input_path)
    server_config = ServerCommandConfig(
        debug=False,
        command="server",
        input_path=str(input_path),
        output_path=str(root / "output"),
        config=None,
        reload=False,
        host="127.0.0.1",
        port=8001,
    )
    config: ProjectConfig = ProjectConfigLoader.load_using_server_config(
        server_config
    )
    if hierarchy:
        config.document_hierarchy = LEVELS
        config.hierarchy_levels = validate_hierarchy(LEVELS)
    config.relation_policy = policy
    config.input_documents_editable = editable
    config.suspect_links = suspect
    config.auth_mode = "proxy"
    config.trusted_proxies = ["10.89.2.0/24"]
    config.roles = ROLE_GROUPS
    client = TestClient(
        create_app(project_config=config),
        client=PROXY,
        raise_server_exceptions=False,
    )
    return client, input_path


def edit_form(
    client: TestClient, node_mid: str, document_mid: str, headers=ADMIN
) -> BeautifulSoup:
    response = client.get(
        "/actions/document/edit_requirement",
        params={"node_id": node_mid, "context_document_mid": document_mid},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return BeautifulSoup(response.text, "html.parser")


def form_values(form: BeautifulSoup) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for input_ in form.find_all("input"):
        if input_.get("name") and input_.get("type") != "file":
            values[input_["name"]] = input_.get("value", "")
    for textarea in form.find_all("textarea"):
        if textarea.get("name"):
            values[textarea["name"]] = html.unescape(textarea.decode_contents())
    return values


def save_with_parent(
    client: TestClient,
    node_mid: str,
    document_mid: str,
    parent_uid: str,
    headers=ADMIN,
):
    """Posts the edit form of a node with one more Parent relation."""
    values = form_values(edit_form(client, node_mid, document_mid, headers))
    values["requirement[relations][new1][value]"] = parent_uid
    values["requirement[relations][new1][typerole]"] = "Parent"
    values["requirement[relations][new1][is_new]"] = "true"
    return client.post(
        "/actions/document/update_requirement", data=values, headers=headers
    )
