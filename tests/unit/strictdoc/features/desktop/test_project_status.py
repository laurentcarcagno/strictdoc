"""
The status of the changes that are not sent: the texts, the route of the
server of a project, and the indicator of its pages.

@relation(SDOC-SRS-1242, scope=file)
@relation(SDOC-SRS-1244, scope=file)
@relation(SDOC-SRS-1248, scope=file)
"""

import json
import re
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pytest
from git import Actor, Repo
from jinja2 import BaseLoader, Environment
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from strictdoc.features.desktop.git_access import GitAccess
from strictdoc.features.desktop.local_server import (
    LocalServer,
    create_desktop_project_config,
    create_project_application,
)
from strictdoc.features.desktop.project_status import (
    INDICATOR_GLOBAL,
    STATUS_PATH,
    ProjectStatus,
    ProjectStatusMiddleware,
    SendState,
    get_project_status,
    get_state_text,
)
from strictdoc.features.desktop.send_queue import SendQueue
from strictdoc.features.git_config.git_service import Author
from strictdoc.features.i18n import i18n
from strictdoc.features.roles.principal import Principal
from strictdoc.features.roles.route_roles import check_routes_classified
from strictdoc.server.app import create_app

SEED = Actor("Seed", "seed@example.org")
AUTHOR = Author("Jeanne Dupont", "jeanne@example.org")
# The words of the tool that shares the changes, and of its messages.
FORBIDDEN_WORDS = re.compile(
    r"\b(git|gitlab|commit|commits|push|pull|branch|merge|rebase|fatal|remote|"
    r"origin|repository|fetch)\b",
    re.IGNORECASE,
)


@pytest.fixture(name="restore_language", autouse=True)
def fixture_restore_language() -> Iterator[None]:
    yield
    i18n.set_language(i18n.DEFAULT_LANGUAGE)


@pytest.mark.parametrize("language", ["en", "fr"])
@pytest.mark.parametrize(
    "state", [state_ for state_ in SendState if state_ is not SendState.IDLE]
)
def test_001_the_text_of_a_state_names_no_tool_and_no_message_of_it(
    state: SendState, language: str
) -> None:
    i18n.set_language(language)

    text = get_state_text(state)

    assert text != ""
    assert FORBIDDEN_WORDS.search(text) is None, text


def test_002_the_texts_are_translated_and_idle_has_none() -> None:
    english = {state_: get_state_text(state_) for state_ in SendState}
    i18n.set_language("fr")
    french = {state_: get_state_text(state_) for state_ in SendState}

    assert english[SendState.IDLE] == ""
    assert french[SendState.IDLE] == ""
    for state_ in SendState:
        if state_ is not SendState.IDLE:
            assert french[state_] != english[state_], state_
    assert french[SendState.NOT_SAVED] == (
        "Votre dernière modification n'a pas été enregistrée."
    )


def test_003_a_change_that_was_not_saved_comes_before_the_rest() -> None:
    waiting = ProjectStatus(SendState.WAITING_NETWORK, 2)

    assert get_project_status("", waiting) == waiting
    assert get_project_status("", None) == ProjectStatus(SendState.IDLE)
    failed = get_project_status("the commit failed", waiting)
    assert failed.state is SendState.NOT_SAVED
    assert failed.count == 2
    assert get_project_status("x", None).state is SendState.NOT_SAVED


def test_004_the_middleware_answers_the_route_of_the_status_only() -> None:
    application = Starlette(
        routes=[
            Route("/page", lambda _: PlainTextResponse("page")),
            Route(
                STATUS_PATH,
                lambda _: PlainTextResponse("a route"),
                methods=["POST"],
            ),
        ]
    )
    client = TestClient(
        ProjectStatusMiddleware(
            application,
            get_status=lambda: ProjectStatus(SendState.WAITING_NETWORK, 3),
        )
    )

    answer = client.get(STATUS_PATH)

    assert answer.status_code == 200
    assert answer.headers["cache-control"] == "no-store"
    assert answer.json() == {
        "state": "waiting_network",
        "count": 3,
        "message": "Waiting for the network to share your changes.",
        "title": "Changes not sent",
    }
    assert client.get("/page").text == "page"
    # Only the read of the status is the middleware's.
    assert client.post(STATUS_PATH).text == "a route"


# The server of a project.


class RecordingQueue(SendQueue):
    """A queue that notes what the server tells it, and sends nothing."""

    def __init__(self, status: ProjectStatus) -> None:
        super().__init__(
            git_access=GitAccess(),
            get_folders=dict,
            get_user_email=lambda: None,
            get_gitlab_url=lambda: "",
            get_role=lambda _: None,
        )
        self.notified: List[str] = []
        self.status: ProjectStatus = status

    def notify(self, folder: str) -> None:
        self.notified.append(folder)

    def get_status(self, folder: str) -> ProjectStatus:
        del folder
        return self.status


def _create_project(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("STRICTDOC_AUTH_MODE", raising=False)
    project_path = root / "project"
    project_path.mkdir()
    (project_path / "doc.sdoc").write_text(
        "[DOCUMENT]\nTITLE: Doc\n\n[REQUIREMENT]\nUID: REQ-1\n"
        "TITLE: Braking\nSTATEMENT: The system shall brake.\n"
    )
    repo = Repo.init(project_path, initial_branch="main")
    repo.index.add(["doc.sdoc"])
    repo.index.commit("Seed", author=SEED, committer=SEED)
    repo.close()
    return project_path


def _create_application(
    project_path: Path,
    queue: Optional[SendQueue] = None,
    role: Optional[str] = "administrator",
) -> Starlette:
    config = create_desktop_project_config(
        input_path=str(project_path),
        port=None,
        principal_provider=(
            (lambda: Principal(user="jdupont", role=role))
            if role is not None
            else (lambda: None)
        ),
    )
    return create_project_application(
        config, lambda: AUTHOR, GitAccess(), queue
    )


def test_005_the_server_answers_its_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_path = _create_project(tmp_path, monkeypatch)
    queue = RecordingQueue(ProjectStatus(SendState.UPDATE_NEEDED, 1))
    client = TestClient(_create_application(project_path, queue))

    answer = client.get(STATUS_PATH)

    assert answer.status_code == 200
    assert answer.json()["state"] == "update_needed"
    assert answer.json()["count"] == 1


def test_006_a_reader_sees_the_status_and_nobody_signed_in_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_path = _create_project(tmp_path, monkeypatch)

    reader = TestClient(_create_application(project_path, role="reader"))
    nobody = TestClient(_create_application(project_path, role=None))

    assert reader.get(STATUS_PATH).status_code == 200
    # The middleware of the principal refuses it, like any other request.
    assert nobody.get(STATUS_PATH).status_code == 401
    assert nobody.get("/").status_code == 401


def test_007_the_status_is_not_a_route_of_the_table_of_the_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_path = _create_project(tmp_path, monkeypatch)
    application = _create_application(project_path)

    paths = [getattr(route_, "path", "") for route_ in application.routes]

    assert not any(path_.startswith("/__desktop") for path_ in paths)
    # The server starts: every route has its role.
    check_routes_classified(application.routes)


def test_008_a_change_that_was_not_saved_is_in_the_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_path = _create_project(tmp_path, monkeypatch)
    application = _create_application(
        project_path,
        RecordingQueue(ProjectStatus(SendState.WAITING_NETWORK, 2)),
    )
    client = TestClient(application)
    committer = application.state.project_context.git_committer
    assert committer is not None

    committer.last_error = "the commit failed: fatal: something of Git"
    answer = client.get(STATUS_PATH).json()

    assert answer["state"] == "not_saved"
    assert answer["message"] == "Your last change was not saved."
    # The message of Git is never shown.
    assert "fatal" not in str(answer)
    assert answer["count"] == 2


def test_009_each_commit_of_the_server_goes_to_the_queue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_path = _create_project(tmp_path, monkeypatch)
    queue = RecordingQueue(ProjectStatus(SendState.IDLE))
    application = _create_application(project_path, queue)
    committer = application.state.project_context.git_committer
    assert committer is not None
    path = project_path / "doc.sdoc"
    path.write_text(path.read_text().replace("Braking", "Emergency braking"))

    committer.on_document_written(str(path))

    assert queue.notified == [committer.service.project_root]


def test_010_the_pages_of_the_application_have_the_indicator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_path = _create_project(tmp_path, monkeypatch)
    client = TestClient(_create_application(project_path))

    page = client.get("/").text

    assert 'data-testid="desktop-indicator"' in page
    assert STATUS_PATH in page
    assert "Changes not sent" in page


def test_011_the_page_of_the_web_server_is_the_same_to_the_character(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_path = _create_project(tmp_path, monkeypatch)
    config = create_desktop_project_config(
        input_path=str(project_path), port=None
    )
    # The web server: no function of the application is given to it.
    web_application = create_app(project_config=config)
    context = web_application.state.project_context
    environment = context.html_templates.jinja_environment().environment
    assert INDICATOR_GLOBAL not in environment.globals
    client = TestClient(web_application)
    pages = {path_: client.get(path_).text for path_ in ("/", "/doc.html")}
    assert "desktop-indicator" not in pages["/"]
    assert "desktop_indicator" not in pages["/"]
    # The reload that the server asks for is immediate, as it was, and the
    # code of the application that waits for an editor is not in the page.
    assert "      window.location.reload();\n" in pages["/"]
    assert "sdocDesktop" not in pages["/"]

    # The same pages, from the template without the line of the application.
    original_loader = environment.loader
    assert original_loader is not None

    class StrippedLoader(BaseLoader):
        def get_source(self, environment: Environment, template: str) -> Any:
            source, name, uptodate = original_loader.get_source(
                environment, template
            )
            if template in ("base.jinja.html", "websocket.jinja.html"):
                stripped = _strip_line_of_the_application(source)
                assert stripped != source, template
                source = stripped
            return source, name, None

    environment.loader = StrippedLoader()
    environment.cache.clear()
    stripped_pages = {
        path_: client.get(path_).text for path_ in ("/", "/doc.html")
    }

    assert pages == stripped_pages


def _strip_line_of_the_application(source: str) -> str:
    return re.sub(
        r"\{% if desktop_indicator is defined %\}.*?\{% endif %\}",
        "",
        source,
        flags=re.DOTALL,
    )


def test_012_the_route_is_behind_the_token_of_the_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_path = _create_project(tmp_path, monkeypatch)
    config = create_desktop_project_config(
        input_path=str(project_path),
        port=None,
        principal_provider=lambda: Principal(
            user="jdupont", role="administrator"
        ),
    )
    server = LocalServer(
        project_config=config,
        author_provider=lambda: AUTHOR,
        git_access=GitAccess(),
    )
    server.start()
    try:
        server.wait_until_ready()
        cookies = CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookies)
        )
        status_url = f"{server.url}{STATUS_PATH}"

        with pytest.raises(urllib.error.HTTPError) as error_info:
            opener.open(status_url, timeout=20)
        assert error_info.value.code == 403

        # The window follows the start URL, which gives it the cookie.
        opener.open(server.start_url, timeout=60).read()
        with opener.open(status_url, timeout=20) as answer_:
            body: Dict[str, Any] = json.loads(answer_.read())
        assert body["state"] == "idle"
    finally:
        server.stop()


def test_013_a_larger_project_has_the_indicator_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Three documents or more: the templates are compiled in advance, and
    # the template of the indicator is not among them.
    project_path = _create_project(tmp_path, monkeypatch)
    for name_ in ("second", "third"):
        (project_path / f"{name_}.sdoc").write_text(
            f"[DOCUMENT]\nTITLE: The {name_} document\n"
        )
    application = _create_application(project_path)
    context = application.state.project_context
    assert not context.is_small_project

    page = TestClient(application).get("/").text

    assert 'data-testid="desktop-indicator"' in page


def test_014_files_that_cannot_be_read_come_after_a_change_not_saved() -> None:
    waiting = ProjectStatus(SendState.WAITING_NETWORK, 2)

    unreadable = get_project_status("", waiting, is_index_outdated=True)
    failed = get_project_status("x", waiting, is_index_outdated=True)

    assert unreadable == ProjectStatus(SendState.UNREADABLE, 2)
    assert failed.state is SendState.NOT_SAVED
    assert get_project_status("", None, is_index_outdated=False) == (
        ProjectStatus(SendState.IDLE)
    )
