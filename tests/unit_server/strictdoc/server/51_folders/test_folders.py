from tests.support.projects_fixture import (
    ROOT,
    as_user,
    client_for,
    make_dispatcher,
)

ANN = as_user("alpha-admins", user="ann")
EVE = as_user(user="eve")
PLATFORM = as_user("platform-admins", user="root")


def _alpha(tmp_path, monkeypatch):
    dispatcher = make_dispatcher(
        tmp_path, monkeypatch, platform_admins=["platform-admins"]
    )
    client = client_for(dispatcher, ROOT)
    client.cookies.set("sdoc_project", "alpha")
    for user, role in (("eve", "reader"), ("ben", "author")):
        client.post(
            "/actions/members/set",
            data={"user": user, "role": role},
            headers=ANN,
        )
    return client


def test_001_an_author_creates_nested_folders_that_the_tree_shows(
    tmp_path, monkeypatch
):
    client = _alpha(tmp_path, monkeypatch)
    ben = as_user(user="ben")
    form = client.get("/actions/project_index/new_folder", headers=ben)
    assert form.status_code == 200 and "folder_path" in form.text

    response = client.post(
        "/actions/project_index/create_folder",
        data={"folder_path": "specs/system"},
        headers=ben,
    )
    assert response.status_code == 200
    assert (tmp_path / "data" / "alpha" / "specs" / "system").is_dir()
    assert (tmp_path / "data" / "alpha" / "specs" / ".sdoc-folder").is_file()
    page = client.get("/fragments/project_tree", headers=ben).text
    assert "specs/" in page and "system/" in page


def test_002_a_reader_cannot_create_a_folder(tmp_path, monkeypatch):
    client = _alpha(tmp_path, monkeypatch)
    for method, path in (
        ("GET", "/actions/project_index/new_folder"),
        ("POST", "/actions/project_index/create_folder"),
    ):
        response = client.request(
            method, path, data={"folder_path": "nope"}, headers=EVE
        )
        assert response.status_code == 403
    assert not (tmp_path / "data" / "alpha" / "nope").exists()


def test_003_a_bad_name_or_an_existing_folder_is_reported(
    tmp_path, monkeypatch
):
    client = _alpha(tmp_path, monkeypatch)
    ben = as_user(user="ben")
    for bad in ("../x", "a b", "_assets", ""):
        response = client.post(
            "/actions/project_index/create_folder",
            data={"folder_path": bad},
            headers=ben,
        )
        assert response.status_code == 200
        assert (
            "sdoc-form-error" in response.text
            or "error" in response.text.lower()
        )
    assert sorted(p.name for p in (tmp_path / "data" / "alpha").iterdir()) == [
        "alpha_doc.sdoc"
    ]
    client.post(
        "/actions/project_index/create_folder",
        data={"folder_path": "docs"},
        headers=ben,
    )
    again = client.post(
        "/actions/project_index/create_folder",
        data={"folder_path": "docs"},
        headers=ben,
    )
    assert "already exists" in again.text


def test_004_a_new_document_goes_in_the_folder(tmp_path, monkeypatch):
    client = _alpha(tmp_path, monkeypatch)
    ben = as_user(user="ben")
    client.post(
        "/actions/project_index/create_folder",
        data={"folder_path": "docs"},
        headers=ben,
    )
    client.post(
        "/actions/project_index/create_document",
        data={"document_title": "T", "document_path": "docs/t.sdoc"},
        headers=ben,
    )
    text = (tmp_path / "data" / "alpha" / "docs" / "t.sdoc").read_text()
    # New documents are in Markdown.
    assert "MARKUP: Markdown" in text


def _with_docs_folder(client, ben):
    client.post(
        "/actions/project_index/create_folder",
        data={"folder_path": "docs"},
        headers=ben,
    )
    client.post(
        "/actions/project_index/create_document",
        data={"document_title": "T", "document_path": "docs/t.sdoc"},
        headers=ben,
    )


def test_010_an_author_renames_a_folder(tmp_path, monkeypatch):
    client = _alpha(tmp_path, monkeypatch)
    ben = as_user(user="ben")
    _with_docs_folder(client, ben)
    data = tmp_path / "data" / "alpha"

    form = client.get(
        "/actions/project_index/rename_folder",
        params={"path": "docs"},
        headers=ben,
    )
    assert form.status_code == 200 and "new_name" in form.text

    response = client.post(
        "/actions/project_index/rename_folder",
        data={"path": "docs", "new_name": "papers"},
        headers=ben,
    )
    assert response.status_code == 200
    assert (data / "papers" / "t.sdoc").is_file() and not (
        data / "docs"
    ).exists()
    page = client.get("/fragments/project_tree", headers=ben).text
    assert "papers/" in page and "docs/" not in page
    # The page that shows the old path asks where the document went.
    assert 'data-from="docs"' in response.text
    assert 'data-to="papers"' in response.text

    bad = client.post(
        "/actions/project_index/rename_folder",
        data={"path": "papers", "new_name": "a b"},
        headers=ben,
    )
    assert bad.status_code == 200 and "Invalid folder name" in bad.text
    assert (data / "papers").is_dir()


def test_011_the_tree_gives_what_a_move_needs(tmp_path, monkeypatch):
    client = _alpha(tmp_path, monkeypatch)
    ben = as_user(user="ben")
    _with_docs_folder(client, ben)
    page = client.get("/fragments/project_tree", headers=ben).text
    assert 'data-rel-path="docs/t.sdoc"' in page
    assert 'data-rel-path="alpha_doc.sdoc"' in page
    assert 'data-tree-node="folder"' in page


def test_012_documents_and_folders_move(tmp_path, monkeypatch):
    client = _alpha(tmp_path, monkeypatch)
    ben = as_user(user="ben")
    _with_docs_folder(client, ben)
    client.post(
        "/actions/project_index/create_folder",
        data={"folder_path": "archive"},
        headers=ben,
    )
    data = tmp_path / "data" / "alpha"

    moved = client.post(
        "/actions/project_index/move",
        data={"source": "alpha_doc.sdoc", "destination": "docs"},
        headers=ben,
    )
    assert moved.status_code == 200
    assert moved.json() == {
        "ok": True,
        "from": "alpha_doc.sdoc",
        "to": "docs/alpha_doc.sdoc",
    }
    assert (data / "docs" / "alpha_doc.sdoc").is_file()

    moved = client.post(
        "/actions/project_index/move",
        data={"source": "docs", "destination": "archive"},
        headers=ben,
    )
    assert moved.status_code == 200
    assert moved.json()["to"] == "archive/docs"
    assert (data / "archive" / "docs" / "t.sdoc").is_file()
    page = client.get("/fragments/project_tree", headers=ben).text
    assert 'data-rel-path="archive/docs/t.sdoc"' in page


def test_013_a_move_that_cannot_be_done_says_why(tmp_path, monkeypatch):
    client = _alpha(tmp_path, monkeypatch)
    ben = as_user(user="ben")
    _with_docs_folder(client, ben)
    data = tmp_path / "data" / "alpha"
    response = client.post(
        "/actions/project_index/move",
        data={"source": "docs", "destination": "docs"},
        headers=ben,
    )
    assert response.status_code == 422
    assert "itself" in response.json()["error"]
    response = client.post(
        "/actions/project_index/move",
        data={"source": "alpha_doc.sdoc", "destination": "nowhere"},
        headers=ben,
    )
    assert response.status_code == 422
    assert (data / "alpha_doc.sdoc").is_file()


def test_016_a_move_rewrites_the_includes_that_point_to_the_moved_folder(
    tmp_path, monkeypatch
):
    client = _alpha(tmp_path, monkeypatch)
    ben = as_user(user="ben")
    _with_docs_folder(client, ben)
    client.post(
        "/actions/project_index/create_folder",
        data={"folder_path": "archive"},
        headers=ben,
    )
    data = tmp_path / "data" / "alpha"
    (data / "main.sdoc").write_text(
        "[DOCUMENT]\nTITLE: Main\n\n[DOCUMENT_FROM_FILE]\nFILE: docs/t.sdoc\n",
        encoding="utf8",
    )
    moved = client.post(
        "/actions/project_index/move",
        data={"source": "docs", "destination": "archive"},
        headers=ben,
    )
    assert moved.status_code == 200
    assert "FILE: archive/docs/t.sdoc\n" in (data / "main.sdoc").read_text()


def test_017_an_author_renames_a_document_and_a_reader_cannot(
    tmp_path, monkeypatch
):
    client = _alpha(tmp_path, monkeypatch)
    ben = as_user(user="ben")
    data = tmp_path / "data" / "alpha"
    form = client.get(
        "/actions/project_index/rename_document",
        params={"path": "alpha_doc.sdoc"},
        headers=ben,
    )
    assert form.status_code == 200 and "new_name" in form.text

    bad = client.post(
        "/actions/project_index/rename_document",
        data={"path": "alpha_doc.sdoc", "new_name": "a b"},
        headers=ben,
    )
    assert bad.status_code == 200 and "Invalid document name" in bad.text

    response = client.post(
        "/actions/project_index/rename_document",
        data={"path": "alpha_doc.sdoc", "new_name": "renamed"},
        headers=ben,
    )
    assert response.status_code == 200
    assert (data / "renamed.sdoc").is_file()
    assert not (data / "alpha_doc.sdoc").exists()
    assert 'data-to="renamed.sdoc"' in response.text
    page = client.get("/fragments/project_tree", headers=ben).text
    assert 'data-rel-path="renamed.sdoc"' in page

    for method in ("GET", "POST"):
        refused = client.request(
            method,
            "/actions/project_index/rename_document",
            params={"path": "renamed.sdoc"},
            data={"path": "renamed.sdoc", "new_name": "x"},
            headers=EVE,
        )
        assert refused.status_code == 403
    assert (data / "renamed.sdoc").is_file()


def test_014_only_an_administrator_deletes_an_empty_folder(
    tmp_path, monkeypatch
):
    client = _alpha(tmp_path, monkeypatch)
    ben = as_user(user="ben")
    client.post(
        "/actions/project_index/create_folder",
        data={"folder_path": "empty"},
        headers=ben,
    )
    _with_docs_folder(client, ben)
    data = tmp_path / "data" / "alpha"

    refused = client.delete(
        "/actions/project_index/delete_folder",
        params={"path": "empty", "confirmed": "1"},
        headers=ben,
    )
    assert refused.status_code == 403 and (data / "empty").is_dir()

    ask = client.delete(
        "/actions/project_index/delete_folder",
        params={"path": "empty"},
        headers=ANN,
    )
    assert ask.status_code == 200 and "confirmed=1" in ask.text
    assert (data / "empty").is_dir()

    done = client.delete(
        "/actions/project_index/delete_folder",
        params={"path": "empty", "confirmed": "1"},
        headers=ANN,
    )
    assert done.status_code == 200 and not (data / "empty").exists()

    full = client.delete(
        "/actions/project_index/delete_folder",
        params={"path": "docs", "confirmed": "1"},
        headers=ANN,
    )
    assert full.status_code == 422 and "t.sdoc" in full.text
    assert (data / "docs" / "t.sdoc").is_file()


def test_015_a_reader_cannot_rename_move_or_delete(tmp_path, monkeypatch):
    client = _alpha(tmp_path, monkeypatch)
    ben = as_user(user="ben")
    _with_docs_folder(client, ben)
    data = tmp_path / "data" / "alpha"
    for method, path, payload in (
        ("GET", "/actions/project_index/rename_folder", {"path": "docs"}),
        (
            "POST",
            "/actions/project_index/rename_folder",
            {"path": "docs", "new_name": "x"},
        ),
        (
            "POST",
            "/actions/project_index/move",
            {"source": "alpha_doc.sdoc", "destination": "docs"},
        ),
        (
            "DELETE",
            "/actions/project_index/delete_folder",
            {"path": "docs", "confirmed": "1"},
        ),
    ):
        kwargs = (
            {"params": payload}
            if method in ("GET", "DELETE")
            else {"data": payload}
        )
        response = client.request(method, path, headers=EVE, **kwargs)
        assert response.status_code == 403, path
    assert (data / "docs" / "t.sdoc").is_file()
    assert (data / "alpha_doc.sdoc").is_file()


def test_018_the_document_menu_exports_to_pdf_and_reqif(tmp_path, monkeypatch):
    dispatcher = make_dispatcher(
        tmp_path,
        monkeypatch,
        platform_admins=["platform-admins"],
        features=["REQIF", "HTML2PDF"],
    )
    client = client_for(dispatcher, ROOT)
    client.cookies.set("sdoc_project", "alpha")
    client.post(
        "/actions/members/set",
        data={"user": "eve", "role": "reader"},
        headers=ANN,
    )
    page = client.get("/fragments/project_tree", headers=EVE).text
    assert "tree-export-pdf-document-action" in page
    assert "/export_html2pdf/{mid}" in page
    assert "tree-export-reqif-document-action" in page

    mid = page.split('data-document-mid="')[1].split('"')[0]
    response = client.get(f"/reqif/export_document/{mid}", headers=EVE)
    assert response.status_code == 200
    assert 'filename="' in response.headers["content-disposition"]
    assert "export.reqif" not in response.headers["content-disposition"]
    assert "<REQ-IF" in response.text
