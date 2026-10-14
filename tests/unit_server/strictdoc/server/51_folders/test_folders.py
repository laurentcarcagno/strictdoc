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
