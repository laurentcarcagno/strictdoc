"""
The screen of the settings, the language of the application, and the
protection of the forms.

@relation(SDOC-SRS-1252, scope=file)
"""

import json
import os
import time
from pathlib import Path
from typing import Any, List

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from strictdoc.features.desktop.application_language import (
    LANGUAGE_VARIABLE,
    apply_application_language,
    get_application_language,
    restore_application_language,
)
from strictdoc.features.desktop.git_access import GitAccess
from strictdoc.features.desktop.home_app import create_home_app
from strictdoc.features.desktop.local_server import (
    LocalServer,
    create_desktop_project_config,
    create_project_application,
)
from strictdoc.features.desktop.project_servers import ProjectServerManager
from strictdoc.features.desktop.session_token import (
    DesktopSessionMiddleware,
    SessionCredentials,
    get_session_cookie_name,
)
from strictdoc.features.desktop.settings import (
    DesktopSettings,
    load_settings,
    parse_settings_form,
    save_settings,
)
from strictdoc.features.git_config.git_service import Author
from strictdoc.features.i18n import i18n
from strictdoc.features.i18n.languages import get_language

PORT = 18081
HOST = f"127.0.0.1:{PORT}"
OWN_ORIGIN = f"http://{HOST}"
OTHER_ORIGIN = "http://127.0.0.1:18999"


@pytest.fixture(name="settings_path")
def fixture_settings_path(tmp_path: Path) -> Path:
    return tmp_path / "config" / "settings.json"


def _write(path: Path, content: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content), encoding="utf-8")


# The settings and their form.


@pytest.mark.parametrize(
    ("stored", "expected"),
    [("fr", "fr"), ("en", "en"), ("de", ""), ("", ""), (3, ""), (None, "")],
)
def test_001_the_language_is_read_without_failing(
    settings_path: Path, stored: Any, expected: str
) -> None:
    _write(settings_path, {"language": stored})

    assert load_settings(settings_path).language == expected


def test_002_the_language_and_the_interval_are_saved_together(
    settings_path: Path,
) -> None:
    save_settings(
        DesktopSettings(language="fr", sync_interval_minutes=9), settings_path
    )

    settings = load_settings(settings_path)

    assert (settings.language, settings.sync_interval_minutes) == ("fr", 9)


@pytest.mark.parametrize("interval", ["1", "5", "120", " 7 ", "007"])
def test_003_an_interval_in_the_limits_is_accepted(interval: str) -> None:
    form = parse_settings_form("", interval)

    assert form.errors == {}
    assert form.sync_interval_minutes == int(interval)


@pytest.mark.parametrize(
    "interval",
    ["0", "121", "-3", "+4", "2.5", "abc", "", "  ", "٣", "9" * 5000, "1e1"],
)
def test_004_an_interval_out_of_the_limits_is_refused_with_a_text(
    interval: str,
) -> None:
    form = parse_settings_form("fr", interval)

    assert list(form.errors) == ["sync_interval_minutes"]
    assert "from 1 to 120" in form.errors["sync_interval_minutes"]


@pytest.mark.parametrize("language", ["de", "FR", "français", "en;fr"])
def test_005_an_unknown_language_is_refused_with_a_text(language: str) -> None:
    form = parse_settings_form(language, "5")

    assert list(form.errors) == ["language"]
    assert form.errors["language"] == "Choose English or French."


def test_006_the_texts_of_the_errors_are_in_french() -> None:
    i18n.set_language("fr")

    form = parse_settings_form("de", "0")

    assert "anglais ou le français" in form.errors["language"]
    assert "nombre entier de minutes" in form.errors["sync_interval_minutes"]


# The language of the application.


def test_007_the_default_is_the_variable_then_english(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert get_application_language(DesktopSettings()) == "en"
    monkeypatch.setenv(LANGUAGE_VARIABLE, "fr")

    # Seen again: the variable that the user set is the default.
    assert get_application_language(DesktopSettings()) == "fr"
    assert get_application_language(DesktopSettings(language="en")) == "en"


def test_008_the_choice_is_the_language_of_the_process_and_of_the_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LANGUAGE_VARIABLE, "fr")

    apply_application_language(DesktopSettings(language="en"))
    assert (get_language(), os.environ[LANGUAGE_VARIABLE]) == ("en", "en")
    # With no choice, the variable that the application started with is back.
    apply_application_language(DesktopSettings())
    assert (get_language(), os.environ[LANGUAGE_VARIABLE]) == ("fr", "fr")


def _create_project(tmp_path: Path, language: str) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "strictdoc.toml").write_text(
        f'[project]\ntitle = "Project"\nlanguage = "{language}"\n'
        'path_to_doxygen = ""\n',
        encoding="utf-8",
    )
    (project / "doc.sdoc").write_text(
        "[DOCUMENT]\nTITLE: Doc\n\n[TEXT]\nSTATEMENT: Text.\n",
        encoding="utf-8",
    )
    return project


@pytest.mark.parametrize("declared", ["en", "fr", "de"])
def test_009_the_language_of_a_project_does_not_change_the_application(
    tmp_path: Path, declared: str
) -> None:
    apply_application_language(DesktopSettings(language="fr"))
    project = _create_project(tmp_path, declared)

    config = create_desktop_project_config(input_path=str(project), port=None)

    # Not even a language that does not exist stops the project from opening.
    assert config.language == "fr"
    assert get_language() == "fr"


def test_010_a_configuration_that_set_the_language_is_corrected() -> None:
    apply_application_language(DesktopSettings(language="fr"))
    i18n.set_language("en")

    restore_application_language()

    assert get_language() == "fr"


# The screen.


def _create_home_client(settings_path: Path) -> TestClient:
    credentials = SessionCredentials.create()
    application = create_home_app(settings_path=settings_path)
    application.add_middleware(
        DesktopSessionMiddleware,
        credentials=credentials,
        port=PORT,
        allowed_hosts=frozenset({HOST, f"localhost:{PORT}"}),
    )
    client = TestClient(application, base_url=OWN_ORIGIN)
    client.cookies.set(get_session_cookie_name(PORT), credentials.token)
    return client


def test_011_the_home_and_the_screen_have_the_way_to_the_settings(
    settings_path: Path,
) -> None:
    client = _create_home_client(settings_path)

    home = client.get("/").text
    screen = client.get("/settings").text

    assert 'data-testid="settings-link"' in home
    assert 'href="/settings"' in home
    assert 'data-testid="settings-form"' in screen
    assert 'data-testid="settings-link"' in screen
    assert 'data-testid="back-to-catalog"' in screen
    # The section of the AI servers: none yet, and no key to show.
    assert 'data-testid="settings-ai"' in screen
    assert 'data-testid="ai-none"' in screen
    assert 'name="sync_interval_minutes"' in screen
    assert 'value="5"' in screen


def test_012_a_good_form_is_saved_and_applied_without_a_restart(
    settings_path: Path,
) -> None:
    client = _create_home_client(settings_path)

    answer = client.post(
        "/settings",
        data={"language": "fr", "sync_interval_minutes": "12"},
        headers={"Origin": OWN_ORIGIN},
        follow_redirects=False,
    )

    assert answer.status_code == 303
    assert answer.headers["location"] == "/settings?saved=true"
    settings = load_settings(settings_path)
    assert (settings.language, settings.sync_interval_minutes) == ("fr", 12)
    assert get_language() == "fr"
    page = client.get("/settings?saved=true").text
    assert "Les réglages sont enregistrés." in page
    assert 'lang="fr"' in page
    assert 'value="12"' in page
    assert "Réglages" in client.get("/").text


def test_013_a_wrong_form_writes_nothing_and_says_why(
    settings_path: Path,
) -> None:
    client = _create_home_client(settings_path)

    answer = client.post(
        "/settings",
        data={"language": "de", "sync_interval_minutes": "500"},
        headers={"Origin": OWN_ORIGIN},
    )

    assert answer.status_code == 422
    assert 'data-testid="settings-language-error"' in answer.text
    assert 'data-testid="settings-interval-error"' in answer.text
    assert "from 1 to 120" in answer.text
    assert not settings_path.exists()
    assert get_language() == "en"


def test_014_a_wrong_form_keeps_the_saved_settings(settings_path: Path) -> None:
    save_settings(
        DesktopSettings(language="fr", sync_interval_minutes=8), settings_path
    )
    client = _create_home_client(settings_path)
    before = settings_path.read_text(encoding="utf-8")

    client.post(
        "/settings",
        data={"language": "fr", "sync_interval_minutes": "0"},
        headers={"Origin": OWN_ORIGIN},
    )

    assert settings_path.read_text(encoding="utf-8") == before


def test_015_a_post_from_a_page_of_another_port_is_refused(
    settings_path: Path,
) -> None:
    client = _create_home_client(settings_path)
    data = {"language": "fr", "sync_interval_minutes": "2"}

    foreign = client.post(
        "/settings", data=data, headers={"Origin": OTHER_ORIGIN}
    )
    opaque = client.post("/settings", data=data, headers={"Origin": "null"})
    signout = client.post(
        "/sign-out", headers={"Origin": OTHER_ORIGIN}, follow_redirects=False
    )

    assert (foreign.status_code, opaque.status_code) == (403, 403)
    assert signout.status_code == 403
    assert not settings_path.exists()
    # The same address by its name is the server too.
    local = client.post(
        "/settings",
        data=data,
        headers={"Origin": f"http://localhost:{PORT}"},
        follow_redirects=False,
    )
    assert local.status_code == 303


def _create_middleware_client(origin_checks: List[str]) -> TestClient:
    def answer(request: Request) -> PlainTextResponse:
        origin_checks.append(request.method)
        return PlainTextResponse("done")

    credentials = SessionCredentials.create()
    application = Starlette(
        routes=[
            Route("/", answer, methods=["GET", "POST", "PUT", "DELETE"]),
        ]
    )
    application.add_middleware(
        DesktopSessionMiddleware,
        credentials=credentials,
        port=PORT,
        allowed_hosts=frozenset({HOST}),
    )
    client = TestClient(application, base_url=OWN_ORIGIN)
    client.cookies.set(get_session_cookie_name(PORT), credentials.token)
    return client


def test_016_only_the_requests_that_change_something_name_their_origin() -> (
    None
):
    reached: List[str] = []
    client = _create_middleware_client(reached)

    assert client.get("/", headers={"Origin": OTHER_ORIGIN}).status_code == 200
    assert client.post("/").status_code == 200
    assert client.post("/", headers={"Origin": OWN_ORIGIN}).status_code == 200
    for method_ in ("POST", "PUT", "DELETE"):
        refused = client.request(method_, "/", headers={"Origin": OTHER_ORIGIN})
        assert refused.status_code == 403, method_

    assert reached == ["GET", "POST", "POST"]


# No restart.


class FakeServer:
    start_url = "http://127.0.0.1:1/start"
    direct_url = "http://127.0.0.1:1/"
    is_bootstrapped = True

    def __init__(self) -> None:
        self.refreshed = 0

    def set_bootstrap_listener(self, listener: Any) -> None:
        pass

    def start(self) -> None:
        pass

    def wait_until_ready(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def refresh_pages(self) -> None:
        self.refreshed += 1


def test_017_the_timers_start_again_with_the_new_interval(
    settings_path: Path,
) -> None:
    save_settings(DesktopSettings(sync_interval_minutes=120), settings_path)
    server = FakeServer()
    manager = ProjectServerManager(
        server_factory=lambda *_: server,  # type: ignore[arg-type,return-value]
        updater=lambda _: False,
        settings_path=settings_path,
        eviction_delay_seconds=0,
    )
    manager.open("a", "/projects/a")
    assert _wait_for(lambda: "a" in manager._sync_timers)  # noqa: SLF001
    assert manager._sync_timers["a"].interval == 7200.0  # noqa: SLF001

    save_settings(DesktopSettings(sync_interval_minutes=1), settings_path)
    manager.apply_settings()

    assert manager._sync_timers["a"].interval == 60.0  # noqa: SLF001
    assert server.refreshed == 1
    manager.stop_all()


def _wait_for(condition: Any, seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_018_the_pages_that_a_project_server_kept_are_made_again(
    tmp_path: Path,
) -> None:
    project = _create_project(tmp_path, "en")
    config = create_desktop_project_config(input_path=str(project), port=None)
    server = LocalServer(project_config=config)
    application = create_project_application(
        config, lambda: Author("A", "a@example.org"), GitAccess()
    )
    server._application = application  # noqa: SLF001
    context = application.state.project_context
    index = context.export_action.traceability_index
    before = index.index_last_updated
    time.sleep(0.01)

    server.refresh_pages()

    assert index.index_last_updated > before
    # A server that is not started has nothing to refresh.
    LocalServer(project_config=config).refresh_pages()
