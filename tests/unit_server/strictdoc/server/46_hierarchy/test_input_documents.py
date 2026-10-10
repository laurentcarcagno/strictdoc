import pytest

from tests.support.hierarchy_fixture import (
    ADMIN,
    AUTHOR,
    DA_1,
    INPUT_DOC,
    REVIEWER,
    SOFTWARE_DOC,
    SW_1,
    edit_form,
    form_values,
    setup,
)

WRITE_ROUTES = [
    ("/actions/document/create_requirement", "document_mid"),
    ("/actions/document/update_requirement", "requirement_mid"),
    ("/actions/table/delete_node", "node_id"),
    ("/actions/table/add_node", "node_mid"),
    ("/actions/table/update_node_field", "node_mid"),
    ("/actions/table/update_document_config_field", "document_mid"),
    ("/actions/table/update_document_custom_meta", "document_mid"),
    ("/actions/table/update_node_field_multiline", "node_mid"),
    ("/actions/table/update_node_comments", "node_mid"),
    ("/actions/table/update_node_relations", "node_mid"),
    ("/actions/document/delete_requirement", "node_id"),
    ("/actions/document/upload_asset", "document_mid"),
    ("/actions/document/move_node", "moved_node_mid"),
    ("/actions/document/move_node_across_documents", "moved_node_mid"),
    ("/actions/document/delete_document", "document_mid"),
    ("/actions/document/save_config", "document_mid"),
    ("/actions/document/save_included_document", "document_mid"),
    ("/actions/document/save_grammar", "document_mid"),
    ("/actions/document/save_grammar_element", "document_mid"),
]


DELETE_ROUTES = {
    "/actions/table/delete_node",
    "/actions/document/delete_requirement",
    "/actions/document/delete_document",
}


def _post(client, path, parameter, mid, headers):
    if path in DELETE_ROUTES:
        return client.delete(path, params={parameter: mid}, headers=headers)
    return client.post(path, data={parameter: mid}, headers=headers)


@pytest.mark.parametrize(("path", "parameter"), WRITE_ROUTES)
def test_001_every_write_route_refuses_an_input_document(
    tmp_path, path, parameter
):
    client, _ = setup(tmp_path)
    for mid in (INPUT_DOC, DA_1):
        response = _post(client, path, parameter, mid, ADMIN)
        assert response.status_code == 403, (path, mid, response.text)
        assert "input document" in response.text


@pytest.mark.parametrize(("path", "parameter"), WRITE_ROUTES)
def test_002_the_same_routes_do_not_refuse_other_documents(
    tmp_path, path, parameter
):
    client, _ = setup(tmp_path)
    response = _post(client, path, parameter, SOFTWARE_DOC, ADMIN)
    assert "input document" not in response.text


def test_003_the_input_document_is_unchanged_after_the_refusals(tmp_path):
    client, input_path = setup(tmp_path)
    before = (input_path / "da.sdoc").read_text(encoding="utf8")
    for path, parameter in WRITE_ROUTES:
        _post(client, path, parameter, DA_1, ADMIN)
    assert (input_path / "da.sdoc").read_text(encoding="utf8") == before


def test_004_a_form_to_edit_an_input_node_is_not_a_way_in(tmp_path):
    client, input_path = setup(tmp_path)
    before = (input_path / "da.sdoc").read_text(encoding="utf8")
    form = client.get(
        "/actions/document/edit_requirement",
        params={"node_id": DA_1, "context_document_mid": INPUT_DOC},
        headers=ADMIN,
    )
    assert form.status_code == 403
    response = client.post(
        "/actions/document/update_requirement",
        data={"requirement_mid": DA_1, "document_mid": INPUT_DOC},
        headers=ADMIN,
    )
    assert response.status_code == 403
    assert (input_path / "da.sdoc").read_text(encoding="utf8") == before


def test_005_the_page_of_an_input_document_has_no_edit_control(tmp_path):
    client, _ = setup(tmp_path)
    page = client.get("/input/da.html", headers=ADMIN)
    assert page.status_code == 200
    software = client.get("/input/software.html", headers=ADMIN)
    assert software.status_code == 200
    assert "edit_requirement" in software.text
    assert "edit_requirement" not in page.text
    assert "delete_requirement" not in page.text


def test_006_an_administrator_can_edit_when_the_project_allows_it(tmp_path):
    client, input_path = setup(tmp_path, editable=True)
    values = form_values(edit_form(client, DA_1, INPUT_DOC, ADMIN))
    response = client.post(
        "/actions/document/update_requirement", data=values, headers=ADMIN
    )
    assert response.status_code == 200, response.text


def test_007_an_author_cannot_edit_an_input_document_even_when_allowed(
    tmp_path,
):
    client, _ = setup(tmp_path, editable=True)
    response = client.get(
        "/actions/document/edit_requirement",
        params={"node_id": DA_1, "context_document_mid": INPUT_DOC},
        headers=AUTHOR,
    )
    assert response.status_code == 403


def test_008_other_documents_are_still_editable_by_an_author(tmp_path):
    client, _ = setup(tmp_path)
    values = form_values(edit_form(client, SW_1, SOFTWARE_DOC, AUTHOR))
    response = client.post(
        "/actions/document/update_requirement", data=values, headers=AUTHOR
    )
    assert response.status_code == 200, response.text


def test_009_a_reviewer_can_still_comment_on_an_input_document(tmp_path):
    client, input_path = setup(tmp_path, comments=True)
    response = client.post(
        "/actions/comments/add",
        data={"node_mid": DA_1, "body": "Is this testable?"},
        headers=REVIEWER,
    )
    assert response.status_code == 200, response.text
    text = (input_path / "da.sdoc").read_text(encoding="utf8")
    assert "Is this testable?" in text
