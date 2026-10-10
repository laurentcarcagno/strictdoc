import html
from pathlib import Path

from tests.support.hierarchy_fixture import (
    ADMIN,
    SOFTWARE_DOC,
    SW_1,
    SW_2,
    SYS_2,
    SYSTEM_DOC,
    edit_form,
    form_values,
    save_with_parent,
    setup,
)


def _text(root: Path, name: str) -> str:
    return (root / "input" / name).read_text(encoding="utf8")


def test_001_enforce_refuses_a_parent_in_a_level_that_is_not_allowed(tmp_path):
    client, _ = setup(tmp_path, policy="enforce")
    # A software requirement may point to system, not to an input document.
    response = save_with_parent(client, SW_2, SOFTWARE_DOC, "DA-1")
    assert response.status_code == 422
    assert "may not have a parent in a 'input' document" in html.unescape(
        response.text
    )
    assert "DA-1" not in _text(tmp_path, "software.sdoc")


def test_002_enforce_accepts_an_allowed_parent(tmp_path):
    client, _ = setup(tmp_path, policy="enforce")
    response = save_with_parent(client, SW_2, SOFTWARE_DOC, "SYS-2")
    assert response.status_code == 200, response.text
    assert "VALUE: SYS-2" in _text(tmp_path, "software.sdoc")


def test_003_enforce_refuses_a_parent_in_a_higher_level_than_allowed(tmp_path):
    client, _ = setup(tmp_path, policy="enforce")
    # A system requirement may not point down to software.
    response = save_with_parent(client, SYS_2, SYSTEM_DOC, "SW-1")
    assert response.status_code == 422
    assert (
        "'system' node may not have a parent in a 'software'"
        in html.unescape(response.text)
    )


def test_004_policy_off_changes_nothing(tmp_path):
    client, _ = setup(tmp_path, policy="off")
    response = save_with_parent(client, SW_2, SOFTWARE_DOC, "DA-1")
    assert response.status_code == 200, response.text
    assert "VALUE: DA-1" in _text(tmp_path, "software.sdoc")


def test_005_warn_does_not_block_the_form(tmp_path):
    client, _ = setup(tmp_path, policy="warn")
    response = save_with_parent(client, SW_2, SOFTWARE_DOC, "DA-1")
    assert response.status_code == 200, response.text


def test_006_existing_relations_stay_valid_when_the_node_is_saved(tmp_path):
    client, _ = setup(tmp_path, policy="enforce")
    values = form_values(edit_form(client, SW_1, SOFTWARE_DOC, ADMIN))
    response = client.post(
        "/actions/document/update_requirement", data=values, headers=ADMIN
    )
    assert response.status_code == 200, response.text
