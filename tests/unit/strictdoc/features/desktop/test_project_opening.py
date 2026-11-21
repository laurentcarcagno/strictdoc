"""
@relation(SDOC-SRS-1230, scope=file)
@relation(SDOC-SRS-1231, scope=file)
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pytest
from git import Actor, Repo
from starlette.testclient import TestClient

from strictdoc.features.desktop import window
from strictdoc.features.desktop.home_app import create_home_app
from strictdoc.features.desktop.project_opener import ProjectOpener
from strictdoc.features.desktop.settings import (
    DesktopSettings,
    load_settings,
    save_settings,
)
from strictdoc.features.i18n import i18n

IDENTIFIER = "demo/isis"
START_URL = "http://127.0.0.1:5999/__desktop/start?code=abc"


class FakeProjectServer:
    def __init__(self, folder: str) -> None:
        self.folder: str = folder
        self.is_running: bool = False
        self.start_url: str = START_URL

    def start(self) -> None:
        self.is_running = True

    def wait_until_ready(self) -> None:
        # The folder holds the project when the server starts.
        assert os.path.isfile(os.path.join(self.folder, "doc.sdoc"))

    def stop(self) -> None:
        self.is_running = False


class Environment:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path: Path = tmp_path
        self.settings_path: Path = tmp_path / "config" / "settings.json"
        self.servers: List[FakeProjectServer] = []
        self.clone_url: str = self._create_bare_repository()
        self._write_catalog(self.clone_url)
        self.opener: ProjectOpener = ProjectOpener(
            server_factory=self._create_server,
            settings_path=self.settings_path,
        )
        self.application = create_home_app(
            settings_path=self.settings_path, opener=self.opener
        )

    def write_catalog(self, clone_url: str) -> None:
        self._write_catalog(clone_url)

    def get_project_folders(self) -> Dict[str, str]:
        return load_settings(self.settings_path).project_folders

    def _create_server(self, folder: str) -> FakeProjectServer:
        server = FakeProjectServer(folder)
        self.servers.append(server)
        return server

    def _create_bare_repository(self) -> str:
        work_path = self.tmp_path / "work"
        work_path.mkdir()
        (work_path / "doc.sdoc").write_text("[DOCUMENT]\nTITLE: Doc\n")
        work_repo = Repo.init(work_path)
        work_repo.index.add(["doc.sdoc"])
        actor = Actor("Test", "test@example.org")
        work_repo.index.commit(
            "Add the document", author=actor, committer=actor
        )
        work_repo.close()
        bare_path = self.tmp_path / "remote.git"
        Repo.clone_from(str(work_path), str(bare_path), bare=True).close()
        return f"file://{bare_path}"

    def _write_catalog(self, clone_url: str) -> None:
        catalog_path = self.tmp_path / "catalog.json"
        catalog_path.write_text(
            json.dumps(
                [
                    {
                        "identifier": IDENTIFIER,
                        "title": "ISIS",
                        "display_path": "Satellites/ISIS",
                        "description": "",
                        "clone_url": clone_url,
                        "role": "author",
                    }
                ]
            ),
            encoding="utf-8",
        )
        save_settings(
            DesktopSettings(
                catalog_provider="fake", fake_catalog_path=str(catalog_path)
            ),
            self.settings_path,
        )


@pytest.fixture(name="environment")
def fixture_environment(tmp_path: Path) -> Environment:
    return Environment(tmp_path)


@pytest.fixture(name="client")
def fixture_client(environment: Environment) -> Iterator[TestClient]:
    # The context manager runs the shutdown of the application.
    with TestClient(environment.application, follow_redirects=False) as client_:
        yield client_


def _wait_for_job(client: TestClient, job_url: str) -> Dict[str, Any]:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        status: Dict[str, Any] = client.get(job_url + "/status").json()
        if status["state"] != "running":
            return status
        time.sleep(0.05)
    raise AssertionError("The job did not end.")


def _post_folder(client: TestClient, folder: Optional[str]) -> Any:
    data = {"identifier": IDENTIFIER}
    if folder is not None:
        data["folder"] = folder
    return client.post("/projects/folder", data=data)


def test_001_first_choice_asks_for_a_folder(client: TestClient) -> None:
    response = client.post("/projects/open", data={"identifier": IDENTIFIER})

    assert response.status_code == 200
    assert 'data-testid="folder-input"' in response.text
    assert 'data-testid="folder-message"' not in response.text


def test_002_folder_that_is_not_empty_is_refused_and_nothing_is_written(
    client: TestClient, environment: Environment, tmp_path: Path
) -> None:
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "notes.txt").write_text("notes")

    response = _post_folder(client, str(folder))

    assert response.status_code == 200
    assert 'data-testid="folder-message"' in response.text
    assert "is not empty" in response.text
    assert environment.get_project_folders() == {}
    assert environment.servers == []
    assert os.listdir(folder) == ["notes.txt"]


def test_003_empty_folder_gets_the_clone_and_is_remembered(
    client: TestClient, environment: Environment, tmp_path: Path
) -> None:
    folder = tmp_path / "workspace"
    folder.mkdir()

    response = _post_folder(client, str(folder))

    assert response.status_code == 303
    job_url = response.headers["location"]
    assert job_url.startswith("/jobs/")
    page = client.get(job_url)
    assert 'data-testid="job-cloning"' in page.text
    status = _wait_for_job(client, job_url)
    assert status["state"] == "done"
    assert status["url"] == START_URL
    assert (folder / "doc.sdoc").is_file()
    assert environment.get_project_folders() == {IDENTIFIER: str(folder)}
    assert [server_.folder for server_ in environment.servers] == [str(folder)]


def test_004_known_folder_opens_without_a_question(
    client: TestClient, environment: Environment, tmp_path: Path
) -> None:
    folder = tmp_path / "workspace"
    folder.mkdir()
    job_url = _post_folder(client, str(folder)).headers["location"]
    _wait_for_job(client, job_url)

    response = client.post("/projects/open", data={"identifier": IDENTIFIER})

    assert response.status_code == 303
    second_job_url = response.headers["location"]
    assert second_job_url != job_url
    # The folder holds the clone: nothing to clone, only to open.
    assert 'data-testid="job-opening"' in client.get(second_job_url).text
    status = _wait_for_job(client, second_job_url)
    assert status["state"] == "done"
    assert environment.get_project_folders() == {IDENTIFIER: str(folder)}
    # The previous server of the project was stopped.
    assert [server_.is_running for server_ in environment.servers] == [
        False,
        True,
    ]


def test_005_folder_that_disappeared_is_said_and_asked_again(
    client: TestClient, environment: Environment, tmp_path: Path
) -> None:
    missing_folder = tmp_path / "gone"
    save_settings(
        DesktopSettings(
            catalog_provider="fake",
            fake_catalog_path=str(tmp_path / "catalog.json"),
            project_folders={IDENTIFIER: str(missing_folder)},
        ),
        environment.settings_path,
    )

    response = client.post("/projects/open", data={"identifier": IDENTIFIER})

    assert response.status_code == 200
    assert "no longer exists" in response.text
    assert str(missing_folder) in response.text
    assert 'data-testid="folder-input"' in response.text


def test_006_failed_clone_is_a_message_and_leaves_the_folder_empty(
    client: TestClient, environment: Environment, tmp_path: Path
) -> None:
    environment.write_catalog(f"file://{tmp_path}/absent.git")
    folder = tmp_path / "workspace"
    folder.mkdir()

    job_url = _post_folder(client, str(folder)).headers["location"]
    status = _wait_for_job(client, job_url)

    assert status["state"] == "failed"
    assert status["message"].startswith("The clone of the project failed")
    assert os.listdir(folder) == []
    assert environment.get_project_folders() == {}
    assert environment.servers == []


def test_007_folder_with_the_clone_of_the_project_is_used_as_it_is(
    client: TestClient, environment: Environment, tmp_path: Path
) -> None:
    folder = tmp_path / "existing"
    Repo.clone_from(environment.clone_url, str(folder)).close()

    response = _post_folder(client, str(folder))

    assert response.status_code == 303
    assert (
        'data-testid="job-opening"'
        in client.get(response.headers["location"]).text
    )
    assert _wait_for_job(client, response.headers["location"])["state"] == (
        "done"
    )


def test_008_unknown_project_is_a_message(client: TestClient) -> None:
    response = client.post("/projects/open", data={"identifier": "unknown"})

    assert response.status_code == 200
    assert "The project is not in the catalog." in response.text


def test_009_dialog_of_the_window_gives_the_folder(
    client: TestClient,
    environment: Environment,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / "chosen"
    folder.mkdir()
    monkeypatch.setattr(window, "is_window_open", lambda: True)
    monkeypatch.setattr(
        window, "choose_folder", lambda _initial_folder: str(folder)
    )

    response = client.post("/projects/open", data={"identifier": IDENTIFIER})

    assert response.status_code == 303
    job_url = response.headers["location"]
    assert _wait_for_job(client, job_url)["state"] == "done"
    assert environment.get_project_folders() == {IDENTIFIER: str(folder)}


def test_010_cancelled_dialog_goes_back_to_the_catalog(
    client: TestClient,
    environment: Environment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(window, "is_window_open", lambda: True)
    monkeypatch.setattr(window, "choose_folder", lambda _initial_folder: None)

    response = client.post("/projects/open", data={"identifier": IDENTIFIER})

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert environment.get_project_folders() == {}


def test_011_refused_folder_of_the_dialog_offers_the_dialog_again(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "notes.txt").write_text("notes")
    monkeypatch.setattr(window, "is_window_open", lambda: True)
    monkeypatch.setattr(
        window, "choose_folder", lambda _initial_folder: str(folder)
    )

    response = client.post("/projects/open", data={"identifier": IDENTIFIER})

    assert response.status_code == 200
    assert "is not empty" in response.text
    assert 'data-testid="folder-choose"' in response.text
    assert 'data-testid="folder-input"' not in response.text


def test_012_empty_field_asks_for_a_path(client: TestClient) -> None:
    response = _post_folder(client, "  ")

    assert response.status_code == 200
    assert "Enter the path of a folder." in response.text


def test_013_servers_of_the_projects_stop_with_the_application(
    environment: Environment, tmp_path: Path
) -> None:
    folder = tmp_path / "workspace"
    folder.mkdir()
    with TestClient(environment.application, follow_redirects=False) as client:
        job_url = _post_folder(client, str(folder)).headers["location"]
        assert _wait_for_job(client, job_url)["state"] == "done"
        assert environment.servers[0].is_running

    assert not environment.servers[0].is_running


def test_014_unknown_job(client: TestClient) -> None:
    assert client.get("/jobs/unknown").headers["location"] == "/"
    assert client.get("/jobs/unknown/status").status_code == 404


def test_015_screens_are_in_french_when_the_language_is_french(
    client: TestClient, tmp_path: Path
) -> None:
    i18n.set_language("fr")
    try:
        ask_page = client.post(
            "/projects/open", data={"identifier": IDENTIFIER}
        )
        folder = tmp_path / "notes"
        folder.mkdir()
        (folder / "notes.txt").write_text("notes")
        refused_page = _post_folder(client, str(folder))
        empty_folder = tmp_path / "workspace"
        empty_folder.mkdir()
        job_url = _post_folder(client, str(empty_folder)).headers["location"]
        job_page = client.get(job_url)
        _wait_for_job(client, job_url)
    finally:
        i18n.set_language(i18n.DEFAULT_LANGUAGE)

    assert "Dossier du projet ISIS" in ask_page.text
    assert "Utiliser ce dossier" in ask_page.text
    assert "n&#39;est pas vide" in refused_page.text
    assert "Clonage du projet ISIS" in job_page.text
    assert "Retour au catalogue" in job_page.text
