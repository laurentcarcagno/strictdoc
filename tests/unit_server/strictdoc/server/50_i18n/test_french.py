import pytest

from strictdoc.features.i18n.languages import set_language
from tests.support.projects_fixture import (
    ROOT,
    as_user,
    client_for,
    make_dispatcher,
)

ALPHA_ADMIN = as_user("alpha-admins", user="ann")


@pytest.fixture(name="french")
def fixture_french(monkeypatch):
    """A server in French; the process language goes back to English."""
    monkeypatch.setenv("STRICTDOC_LANGUAGE", "fr")
    yield
    set_language("en")


@pytest.mark.usefixtures("french")
def test_001_the_portal_and_the_project_speak_french(tmp_path, monkeypatch):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    portal = client_for(dispatcher, ROOT)
    page = portal.get("/_projects", headers=ALPHA_ADMIN).text
    assert '<html lang="fr">' in page
    assert '<span class="hem-label">Vos projets</span>' in page
    assert '<span class="nav__subtitle">Projets</span>' in page
    # Only the texts of the scripts are embedded in the page.
    assert "Your projects" not in page
    assert "<td>administrateur</td>" in page

    alpha = client_for(dispatcher, f"alpha.{ROOT}")
    document = alpha.get("/alpha/alpha_doc.html", headers=ALPHA_ADMIN).text
    assert "Accueil du projet" in document
    # The scripts get their texts: "Expand the sidebar" (nav.js).
    assert "window.SDOC_I18N" in document
    assert '"Expand the sidebar"' in document


@pytest.mark.usefixtures("french")
def test_002_the_role_names_are_french_and_the_form_posts_english(
    tmp_path, monkeypatch
):
    dispatcher = make_dispatcher(tmp_path, monkeypatch)
    alpha = client_for(dispatcher, f"alpha.{ROOT}")
    page = alpha.get("/members", headers=ALPHA_ADMIN).text
    assert '<option value="reviewer">relecteur</option>' in page
    response = alpha.post(
        "/actions/members/set",
        data={"user": "carol", "role": "reviewer"},
        headers=ALPHA_ADMIN,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "carol" in alpha.get("/members", headers=ALPHA_ADMIN).text
