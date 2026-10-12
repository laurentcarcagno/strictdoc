import json
from pathlib import Path

from fastapi.testclient import TestClient

from strictdoc.features.projects.app import create_projects_app
from strictdoc.features.projects.directory import KeycloakDirectory
from strictdoc.features.projects.registry import ProjectSpec
from strictdoc.server.app import create_app
from tests.support.fake_keycloak import SECRET, FakeKeycloak
from tests.support.projects_fixture import (
    ALPHA_DOC,
    ALPHA_REQ,
    ROOT,
    as_user,
    client_for,
    make_dispatcher,
    make_specs,
    roles,
)

ROOT_ADMIN = as_user("platform-admins", user="root")
ANN = as_user("alpha-admins", user="ann")
CAROL = as_user(user="carol")
DAN = as_user(user="dan")
ERIC = as_user(user="eric")


def _dispatcher(tmp_path, monkeypatch, comments=False):
    return make_dispatcher(
        tmp_path,
        monkeypatch,
        platform_admins=["platform-admins"],
        comments=comments,
    )


def _create(portal, slug="gamma", title="Gamma program", headers=ROOT_ADMIN):
    return portal.post(
        "/_projects/create",
        data={"slug": slug, "title": title},
        headers=headers,
        follow_redirects=False,
    )


def test_001_an_administrator_creates_a_project(tmp_path, monkeypatch):
    dispatcher = _dispatcher(tmp_path, monkeypatch)
    portal = client_for(dispatcher, ROOT)
    assert "portal-create" in portal.get("/_projects", headers=ROOT_ADMIN).text

    response = _create(portal)
    assert response.status_code == 303
    # The new project becomes the current one.
    assert response.headers["location"] == "/_projects/select/gamma"

    folder = tmp_path / "data" / "gamma"
    assert (folder / "strictdoc.toml").is_file()
    # Word import and export are on in a new project.
    assert '"DOCX"' in (folder / "strictdoc.toml").read_text()
    store = json.loads((tmp_path / "output" / "projects.json").read_text())
    assert store["projects"]["gamma"]["title"] == "Gamma program"
    # The creator is its administrator.
    assert store["members"]["gamma"] == {"root": "administrator"}

    gamma = client_for(dispatcher, f"gamma.{ROOT}")
    assert gamma.get("/", headers=ROOT_ADMIN).status_code == 200
    assert "Gamma program" in portal.get("/_projects", headers=ROOT_ADMIN).text


def test_002_somebody_else_cannot_create_a_project(tmp_path, monkeypatch):
    dispatcher = _dispatcher(tmp_path, monkeypatch)
    portal = client_for(dispatcher, ROOT)
    assert "portal-create" not in portal.get("/_projects", headers=ANN).text
    assert _create(portal, headers=ANN).status_code == 403
    assert not (tmp_path / "data" / "gamma").exists()


def test_003_a_bad_or_used_name_is_refused(tmp_path, monkeypatch):
    dispatcher = _dispatcher(tmp_path, monkeypatch)
    portal = client_for(dispatcher, ROOT)
    for slug in ("Bad Name", "../x", "alpha", ""):
        response = _create(portal, slug=slug)
        assert response.status_code == 422, slug
        assert "portal-error" in response.text
    assert sorted(p.name for p in (tmp_path / "data").iterdir()) == [
        "alpha",
        "beta",
    ]


def test_004_the_administrator_adds_members_who_read_everything(
    tmp_path, monkeypatch
):
    dispatcher = _dispatcher(tmp_path, monkeypatch)
    portal = client_for(dispatcher, ROOT)
    _create(portal)
    gamma = client_for(dispatcher, f"gamma.{ROOT}")

    # Nobody knows carol yet.
    assert gamma.get("/", headers=CAROL).status_code == 403
    assert "gamma" not in portal.get("/_projects", headers=CAROL).text

    response = gamma.post(
        "/actions/members/set",
        data={"user": " Carol ", "role": "reader"},
        headers=ROOT_ADMIN,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert gamma.get("/", headers=CAROL).status_code == 200
    assert 'data-slug="gamma"' in portal.get("/_projects", headers=CAROL).text
    assert "carol" in gamma.get("/members", headers=ROOT_ADMIN).text

    # A reader writes nothing and does not manage the members.
    assert (
        gamma.post(
            "/actions/members/set",
            data={"user": "dan", "role": "author"},
            headers=CAROL,
        ).status_code
        == 403
    )
    assert gamma.get("/members", headers=CAROL).status_code == 403

    gamma.post(
        "/actions/members/remove", data={"user": "carol"}, headers=ROOT_ADMIN
    )
    assert gamma.get("/", headers=CAROL).status_code == 403


def test_005_a_project_is_isolated_from_the_members_of_another(
    tmp_path, monkeypatch
):
    dispatcher = _dispatcher(tmp_path, monkeypatch)
    portal = client_for(dispatcher, ROOT)
    _create(portal)
    gamma = client_for(dispatcher, f"gamma.{ROOT}")
    alpha = client_for(dispatcher, f"alpha.{ROOT}")
    gamma.post(
        "/actions/members/set",
        data={"user": "carol", "role": "author"},
        headers=ROOT_ADMIN,
    )
    assert alpha.get("/", headers=CAROL).status_code == 403
    assert (
        alpha.post(
            "/actions/members/set",
            data={"user": "carol", "role": "administrator"},
            headers=CAROL,
        ).status_code
        == 403
    )


def test_006_an_author_creates_a_document_and_names_its_reviewers(
    tmp_path, monkeypatch
):
    dispatcher = _dispatcher(tmp_path, monkeypatch)
    portal = client_for(dispatcher, ROOT)
    _create(portal)
    gamma = client_for(dispatcher, f"gamma.{ROOT}")
    for user, role in (("carol", "author"), ("dan", "reader")):
        gamma.post(
            "/actions/members/set",
            data={"user": user, "role": role},
            headers=ROOT_ADMIN,
        )
    form = {
        "document_title": "Spec",
        "document_path": "spec.sdoc",
        "reviewers": "Dan, dan",
    }
    # A reader may not create a document.
    assert (
        gamma.post(
            "/actions/project_index/create_document", data=form, headers=DAN
        ).status_code
        == 403
    )
    assert (
        "reviewers"
        in gamma.get("/actions/project_index/new_document", headers=CAROL).text
    )

    # Only members can be named.
    refused = gamma.post(
        "/actions/project_index/create_document",
        data={**form, "reviewers": "dan, zoe"},
        headers=CAROL,
    )
    assert "Not members of the project: zoe" in refused.text
    assert not (tmp_path / "data" / "gamma" / "spec.sdoc").exists()

    created = gamma.post(
        "/actions/project_index/create_document", data=form, headers=CAROL
    )
    assert created.status_code == 200
    text = (tmp_path / "data" / "gamma" / "spec.sdoc").read_text()
    assert "REVIEWERS: dan" in text


def test_007_only_the_reviewers_of_a_document_comment_on_it(
    tmp_path, monkeypatch
):
    dispatcher = _dispatcher(tmp_path, monkeypatch, comments=True)
    alpha = client_for(dispatcher, f"alpha.{ROOT}")
    for user, role in (
        ("carol", "reader"),
        ("dan", "reader"),
        ("eric", "author"),
    ):
        alpha.post(
            "/actions/members/set",
            data={"user": user, "role": role},
            headers=ANN,
        )

    def comment(headers):
        return alpha.post(
            "/actions/comments/add",
            data={"node_mid": ALPHA_REQ, "body": "Check this."},
            headers=headers,
        )

    # Nobody is named: a reader cannot, an author can.
    assert comment(CAROL).status_code == 403
    assert comment(ERIC).status_code == 200

    # The author names carol: she can, dan still cannot.
    named = alpha.post(
        "/actions/reviewers/set",
        data={"document_mid": ALPHA_DOC, "reviewers": "carol"},
        headers=ERIC,
        follow_redirects=False,
    )
    assert named.status_code == 303
    assert comment(CAROL).status_code == 200
    assert comment(DAN).status_code == 403
    text = (Path(tmp_path) / "data" / "alpha" / "alpha_doc.sdoc").read_text()
    assert "REVIEWERS: carol" in text
    assert "Check this." in text

    # The page tells the browser who may comment, and a reader cannot name.
    page = alpha.get("/alpha/alpha_doc.html", headers=CAROL).text
    assert 'data-reviewers="carol"' in page
    assert (
        alpha.post(
            "/actions/reviewers/set",
            data={"document_mid": ALPHA_DOC, "reviewers": "dan"},
            headers=CAROL,
        ).status_code
        == 403
    )
    # A name that is not a member is refused.
    refused = alpha.post(
        "/actions/reviewers/set",
        data={"document_mid": ALPHA_DOC, "reviewers": "zoe"},
        headers=ERIC,
    )
    assert refused.status_code == 422


def test_008_the_projects_and_members_survive_a_restart(tmp_path, monkeypatch):
    dispatcher = _dispatcher(tmp_path, monkeypatch)
    portal = client_for(dispatcher, ROOT)
    _create(portal)
    client_for(dispatcher, f"gamma.{ROOT}").post(
        "/actions/members/set",
        data={"user": "carol", "role": "reader"},
        headers=ROOT_ADMIN,
    )

    again = create_projects_app(
        create_app=create_app,
        specs=dispatcher_specs(tmp_path),
        root_host=ROOT,
        output_root=str(tmp_path / "output"),
        audit_root=str(tmp_path / "audit"),
        data_root=str(tmp_path / "data"),
        platform_admin_groups=["platform-admins"],
    )
    assert "gamma" in again.projects
    assert (
        client_for(again, f"gamma.{ROOT}").get("/", headers=CAROL).status_code
        == 200
    )


def dispatcher_specs(root):

    return [
        ProjectSpec(
            slug=slug,
            title=f"{slug} program",
            path=str(root / "data" / slug),
            roles=roles(slug),
        )
        for slug in ("alpha", "beta")
    ]


def test_009_a_project_created_while_running_gets_its_lifespan(
    tmp_path, monkeypatch
):
    dispatcher = _dispatcher(tmp_path, monkeypatch)

    with TestClient(dispatcher):
        portal = client_for(dispatcher, ROOT)
        _create(portal)
        assert "gamma" in dispatcher.projects
        assert dispatcher._stack is not None
    assert dispatcher._stack is None


def _with_directory(tmp_path, monkeypatch, keycloak):
    monkeypatch.setenv("STRICTDOC_AUTH_MODE", "proxy")
    monkeypatch.setenv("STRICTDOC_TRUSTED_PROXIES", "10.89.2.0/24")
    return create_projects_app(
        create_app=create_app,
        specs=make_specs(tmp_path),
        root_host=ROOT,
        output_root=str(tmp_path / "output"),
        audit_root=str(tmp_path / "audit"),
        data_root=str(tmp_path / "data"),
        platform_admin_groups=["platform-admins"],
        directory=KeycloakDirectory(
            base_url=keycloak.url,
            realm="infra",
            client_id="strictdoc-directory",
            client_secret=SECRET,
        ),
    )


def test_010_the_members_page_suggests_and_checks_keycloak_accounts(
    tmp_path, monkeypatch
):
    users = [
        {
            "username": "carol",
            "firstName": "Carol",
            "lastName": "Dupont",
            "email": "carol@example.org",
            "enabled": True,
        },
    ]
    with FakeKeycloak(users) as keycloak:
        dispatcher = _with_directory(tmp_path, monkeypatch, keycloak)
        alpha = client_for(dispatcher, f"alpha.{ROOT}")
        page = alpha.get("/members", headers=ANN).text
        assert "<option value='carol'>Carol Dupont carol@example.org" in page
        # An account that does not exist is refused, a real one accepted.
        refused = alpha.post(
            "/actions/members/set",
            data={"user": "zoe", "role": "reader"},
            headers=ANN,
        )
        assert refused.status_code == 422
        assert "not an account of the login server" in refused.text
        assert (
            alpha.post(
                "/actions/members/set",
                data={"user": "carol", "role": "reader"},
                headers=ANN,
                follow_redirects=False,
            ).status_code
            == 303
        )
        # Somebody who is not an administrator of the project sees nothing.
        assert alpha.get("/members", headers=CAROL).status_code == 403


def test_012_when_keycloak_is_down_the_name_is_typed_by_hand(
    tmp_path, monkeypatch
):
    with FakeKeycloak([]) as keycloak:
        keycloak.down = True
        dispatcher = _with_directory(tmp_path, monkeypatch, keycloak)
        alpha = client_for(dispatcher, f"alpha.{ROOT}")
        assert "does not answer" in alpha.get("/members", headers=ANN).text
        assert (
            alpha.post(
                "/actions/members/set",
                data={"user": "carol", "role": "reader"},
                headers=ANN,
                follow_redirects=False,
            ).status_code
            == 303
        )


def test_011_without_keycloak_the_page_still_works(tmp_path, monkeypatch):
    dispatcher = _dispatcher(tmp_path, monkeypatch)
    alpha = client_for(dispatcher, f"alpha.{ROOT}")
    page = alpha.get("/members", headers=ANN).text
    assert "directory-users" in page
    assert (
        alpha.post(
            "/actions/members/set",
            data={"user": "anyone", "role": "reader"},
            headers=ANN,
            follow_redirects=False,
        ).status_code
        == 303
    )
