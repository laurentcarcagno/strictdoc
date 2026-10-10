import json
import re
from pathlib import Path

from tests.support.hierarchy_fixture import (
    ADMIN,
    AUTHOR,
    READER,
    SOFTWARE_DOC,
    SW_1,
    SW_2,
    SYS_1,
    SYSTEM_DOC,
    edit_form,
    form_values,
    save_with_parent,
    setup,
)


def _baseline(input_path: Path) -> dict:
    return json.loads((input_path / "trace_baseline.json").read_text("utf8"))


def _create_baseline(client) -> None:
    response = client.post("/actions/suspect/baseline", headers=ADMIN)
    assert response.status_code in (200, 303), response.text


def _edit_statement(client, node_mid, document_mid, text, headers=ADMIN):
    form = edit_form(client, node_mid, document_mid, headers)
    values = form_values(form)
    name_key = next(
        k
        for k, v in values.items()
        if k.endswith("[name]") and v == "STATEMENT"
    )
    name = name_key.replace("[name]", "[value]")
    values[name] = text
    response = client.post(
        "/actions/document/update_requirement", data=values, headers=headers
    )
    assert response.status_code == 200, response.text


def _suspects(client, headers=ADMIN) -> str:
    response = client.get("/suspect_links", headers=headers)
    assert response.status_code == 200
    return response.text


def test_001_the_routes_need_the_option(tmp_path):
    client, _ = setup(tmp_path, suspect=False)
    assert client.get("/suspect_links", headers=ADMIN).status_code == 412
    assert (
        client.post("/actions/suspect/baseline", headers=ADMIN).status_code
        == 412
    )


def test_002_without_a_baseline_nothing_is_checked(tmp_path):
    client, input_path = setup(tmp_path, suspect=True)
    assert "No baseline yet" in _suspects(client)
    _edit_statement(client, SYS_1, SYSTEM_DOC, "The system shall do A, better.")
    assert "No baseline yet" in _suspects(client)
    assert not (input_path / "trace_baseline.json").exists()


def test_003_the_baseline_has_one_sorted_line_per_link(tmp_path):
    client, input_path = setup(tmp_path, suspect=True)
    _create_baseline(client)
    baseline = _baseline(input_path)
    assert sorted(baseline) == ["SW-1 < SYS-1", "SYS-1 < DA-1"]
    lines = (input_path / "trace_baseline.json").read_text("utf8").splitlines()
    assert len(lines) == 4 and all(len(v) == 40 for v in baseline.values())


def test_004_a_parent_edit_makes_its_children_suspect(tmp_path):
    client, _ = setup(tmp_path, suspect=True)
    _create_baseline(client)
    assert "0 suspect link(s)" in _suspects(client)
    _edit_statement(client, SYS_1, SYSTEM_DOC, "The system shall do A, better.")
    page = _suspects(client)
    assert "1 suspect link(s)" in page
    assert re.search(r">SYS-1</a>", page) and re.search(r">SW-1</a>", page)
    # SYS-1 itself answers DA-1, which did not change.
    assert not re.search(r"suspect-row.*?>SYS-1</a></td>", page, re.S)


def test_005_the_node_view_shows_a_badge(tmp_path):
    client, _ = setup(tmp_path, suspect=True)
    _create_baseline(client)
    _edit_statement(client, SYS_1, SYSTEM_DOC, "The system shall do A, better.")
    page = client.get("/input/software.html", headers=ADMIN).text
    assert 'data-testid="suspect-badge"' in page
    assert "Suspect: SYS-1" in page
    other = client.get("/input/system.html", headers=ADMIN).text
    assert 'data-testid="suspect-badge"' not in other


def test_006_clearing_a_link_takes_the_parent_as_reviewed(tmp_path):
    client, input_path = setup(tmp_path, suspect=True)
    _create_baseline(client)
    before = _baseline(input_path)["SW-1 < SYS-1"]
    _edit_statement(client, SYS_1, SYSTEM_DOC, "The system shall do A, better.")
    response = client.post(
        "/actions/suspect/clear",
        data={"child_uid": "SW-1", "parent_uid": "SYS-1"},
        headers=AUTHOR,
    )
    assert response.status_code in (200, 303)
    assert _baseline(input_path)["SW-1 < SYS-1"] != before
    assert "0 suspect link(s)" in _suspects(client)
    assert 'data-testid="suspect-badge"' not in (
        client.get("/input/software.html", headers=ADMIN).text
    )


def test_007_a_reader_cannot_clear_and_the_button_is_not_offered(tmp_path):
    client, input_path = setup(tmp_path, suspect=True)
    _create_baseline(client)
    _edit_statement(client, SYS_1, SYSTEM_DOC, "The system shall do A, better.")
    assert "suspect-clear" not in _suspects(client, READER)
    assert "suspect-clear" in _suspects(client, AUTHOR)
    before = _baseline(input_path)
    response = client.post(
        "/actions/suspect/clear",
        data={"child_uid": "SW-1", "parent_uid": "SYS-1"},
        headers=READER,
    )
    assert response.status_code == 403
    assert _baseline(input_path) == before


def test_008_only_an_administrator_creates_the_baseline(tmp_path):
    client, input_path = setup(tmp_path, suspect=True)
    response = client.post("/actions/suspect/baseline", headers=AUTHOR)
    assert response.status_code == 403
    assert not (input_path / "trace_baseline.json").exists()


def test_009_a_new_link_gets_its_baseline_entry_at_once(tmp_path):
    client, input_path = setup(tmp_path, suspect=True)
    _create_baseline(client)
    response = save_with_parent(client, SW_2, SOFTWARE_DOC, "SYS-1")
    assert response.status_code == 200, response.text
    assert "SW-2 < SYS-1" in _baseline(input_path)
    assert "0 suspect link(s)" in _suspects(client)


def test_010_a_removed_link_loses_its_entry(tmp_path):
    client, input_path = setup(tmp_path, suspect=True)
    _create_baseline(client)
    form = edit_form(client, SW_1, SOFTWARE_DOC, ADMIN)
    values = form_values(form)
    for key in list(values):
        if key.endswith("[value]") and "relations" in key:
            values[key] = ""
    response = client.post(
        "/actions/document/update_requirement", data=values, headers=ADMIN
    )
    assert response.status_code == 200, response.text
    assert "SW-1 < SYS-1" not in _baseline(input_path)
