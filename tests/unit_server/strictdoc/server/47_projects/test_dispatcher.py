import re

from fastapi.testclient import TestClient

from tests.support.projects_fixture import (
    ALPHA_DOC,
    ALPHA_REQ,
    BETA_DOC,
    ROOT,
    as_user,
    client_for,
    clients,
    make_dispatcher,
)

ALPHA_ADMIN = as_user("alpha-admins", user="ann")
BETA_ADMIN = as_user("beta-admins", user="ben")
BOTH = as_user("alpha-authors", "beta-readers", user="bob")
NOBODY = as_user("other-group", user="nick")


def test_001_each_host_serves_its_own_project(tmp_path, monkeypatch):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    _, alpha, beta = clients(dispatcher)
    alpha_page = alpha.get("/alpha/alpha_doc.html", headers=ALPHA_ADMIN)
    assert alpha_page.status_code == 200
    assert (
        "Alpha spec" in alpha_page.text and "Beta spec" not in alpha_page.text
    )
    beta_page = beta.get("/beta/beta_doc.html", headers=BETA_ADMIN)
    assert beta_page.status_code == 200
    assert "Beta spec" in beta_page.text and "Alpha spec" not in beta_page.text


def test_002_a_path_of_one_project_is_not_found_on_the_other(
    tmp_path, monkeypatch
):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    _, alpha, beta = clients(dispatcher)
    both = as_user("alpha-admins", "beta-admins", user="root")
    assert alpha.get("/beta/beta_doc.html", headers=both).status_code == 404
    assert beta.get("/alpha/alpha_doc.html", headers=both).status_code == 404
    assert alpha.get("/UID/BETA-1", headers=both).status_code == 404
    assert beta.get("/UID/ALPHA-1", headers=both).status_code == 404


def test_003_an_unknown_host_is_a_bare_404(tmp_path, monkeypatch):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    for host in (
        "gamma." + ROOT,
        "evil.example",
        "alpha." + ROOT + ".evil.example",
        "xalpha." + ROOT,
        "localhost",
    ):
        response = client_for(dispatcher, host).get("/", headers=ALPHA_ADMIN)
        assert response.status_code == 404, host
        assert response.text == "Not found"
        assert "alpha" not in response.text.lower()


def test_004_the_host_is_matched_without_its_port_and_case(
    tmp_path, monkeypatch
):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    client = client_for(dispatcher, f"ALPHA.{ROOT}:8443")
    assert (
        client.get("/alpha/alpha_doc.html", headers=ALPHA_ADMIN).status_code
        == 200
    )


def test_005_the_health_check_answers_on_every_host(tmp_path, monkeypatch):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    for host in (ROOT, "alpha." + ROOT, "whatever.example"):
        response = client_for(dispatcher, host).get("/healthz")
        assert (response.status_code, response.text) == (200, "ok")


def test_006_a_user_of_one_project_has_no_access_to_the_other(
    tmp_path, monkeypatch
):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    _, alpha, beta = clients(dispatcher)
    assert (
        alpha.get("/alpha/alpha_doc.html", headers=ALPHA_ADMIN).status_code
        == 200
    )
    # The same user, the other project: no group there.
    assert (
        beta.get("/beta/beta_doc.html", headers=ALPHA_ADMIN).status_code == 403
    )
    assert beta.get("/", headers=ALPHA_ADMIN).status_code == 403
    assert alpha.get("/alpha/alpha_doc.html", headers=NOBODY).status_code == 403


def test_007_roles_are_the_ones_of_each_project(tmp_path, monkeypatch):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    _, alpha, beta = clients(dispatcher)
    who_alpha = alpha.get("/whoami", headers=BOTH).json()
    who_beta = beta.get("/whoami", headers=BOTH).json()
    assert who_alpha["role"] == "author"
    assert who_beta["role"] == "reader"


def test_008_the_portal_lists_only_the_projects_of_the_user(
    tmp_path, monkeypatch
):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    portal, _, _ = clients(dispatcher)

    def slugs(headers):
        response = portal.get("/", headers=headers)
        assert response.status_code == 200
        return re.findall(r'data-slug="([^"]+)"', response.text), response.text

    assert slugs(ALPHA_ADMIN)[0] == ["alpha"]
    assert slugs(BETA_ADMIN)[0] == ["beta"]
    assert slugs(BOTH)[0] == ["alpha", "beta"]
    found, page = slugs(NOBODY)
    assert found == [] and "not a member of any project" in page


def test_009_the_portal_shows_role_title_documents_and_link(
    tmp_path, monkeypatch
):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    portal, _, _ = clients(dispatcher)
    page = portal.get("/", headers=BOTH).text
    assert "Alpha program" in page and "Beta program" in page
    assert re.search(r"<td>author</td>\s*<td>1</td>", page)
    assert re.search(r"<td>reader</td>\s*<td>1</td>", page)
    assert f'href="http://alpha.{ROOT}/"' in page


def test_010_the_portal_needs_a_trusted_proxy(tmp_path, monkeypatch):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    direct = TestClient(
        dispatcher,
        base_url=f"http://{ROOT}",
        client=("203.0.113.9", 1234),
        raise_server_exceptions=False,
    )
    assert direct.get("/", headers=ALPHA_ADMIN).status_code == 401
    assert direct.get("/alpha/x", headers=ALPHA_ADMIN).status_code == 401
    alpha_direct = TestClient(
        dispatcher,
        base_url=f"http://alpha.{ROOT}",
        client=("203.0.113.9", 1234),
        raise_server_exceptions=False,
    )
    assert alpha_direct.get("/", headers=ALPHA_ADMIN).status_code == 401


def test_011_a_server_without_a_login_proxy_shows_every_project(
    tmp_path, monkeypatch
):
    dispatcher = make_dispatcher(tmp_path, monkeypatch, proxy=False)
    portal, alpha, _ = clients(dispatcher, proxy=False)
    page = portal.get("/").text
    assert re.findall(r'data-slug="([^"]+)"', page) == ["alpha", "beta"]
    assert alpha.get("/alpha/alpha_doc.html").status_code == 200


def test_012_constants_are_distinct():
    assert ALPHA_DOC != BETA_DOC and ALPHA_REQ
