"""
The settings of the application: the language and the time between two
updates, changed in the screen of the settings and applied with no restart.

The language of the application is the one of the user. A project that is
declared in English is shown in the language of the application, and the home
screen stays in it when the project is opened.

@relation(SDOC-SRS-1252, scope=file)
"""

import os
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Callable, Tuple

import pytest
from git import Actor, Repo

from tests.end2end.desktop.desktop_case import DesktopCase
from tests.end2end.desktop.desktop_test_server import DesktopTestServer
from tests.end2end.desktop.fake_gitlab import (
    CLIENT_ID,
    DISPLAY_NAME,
    GROUP_PATH,
    MAINTAINER,
    FakeGitLab,
)
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)

DOCUMENT_TITLE = "Declared in English"
SEED_AUTHOR = Actor("Seed", "seed@example.org")
COLLEAGUE = Actor("Colleague", "colleague@example.org")

SIGN_IN = '[data-testid="sign-in"]'
OPEN_BUTTON = '[data-testid="catalog-project-open"]'
FOLDER_INPUT = '[data-testid="folder-input"]'
FOLDER_SUBMIT = '[data-testid="folder-submit"]'
SETTINGS_LINK = '[data-testid="settings-link"]'
LANGUAGE = '[data-testid="settings-language"]'
INTERVAL = '[data-testid="settings-interval"]'
SAVE = '[data-testid="settings-save"]'
SAVED = '[data-testid="settings-saved"]'
WAIT_SECONDS = 40.0


def _create_remote(root: str) -> Tuple[str, str]:
    """A bare repository of a project that declares the language English."""
    work_path = os.path.join(root, "remote_work")
    os.makedirs(work_path)
    Path(work_path, "strictdoc.toml").write_text(
        '[project]\ntitle = "Declared in English"\nlanguage = "en"\n',
        encoding="utf-8",
    )
    Path(work_path, "doc.sdoc").write_text(
        "[DOCUMENT]\n"
        "MID: 1d6c2b5f8a9e4e1fb7c3a0d4e5f60a11\n"
        f"TITLE: {DOCUMENT_TITLE}\n"
        "OPTIONS:\n"
        "  ENABLE_MID: True\n"
        "\n"
        "[REQUIREMENT]\n"
        "MID: 2e7d3c6a9b0f4f2ac8d4b1e5f6a70b22\n"
        "UID: REQ-1\n"
        "STATEMENT: The system shall brake.\n",
        encoding="utf-8",
    )
    work_repo = Repo.init(work_path, initial_branch="main")
    work_repo.index.add(["doc.sdoc", "strictdoc.toml"])
    work_repo.index.commit("Seed", author=SEED_AUTHOR, committer=SEED_AUTHOR)
    work_repo.close()
    bare_path = os.path.join(root, "remote.git")
    Repo.clone_from(work_path, bare_path, bare=True).close()
    return f"file://{bare_path}", bare_path


def _push_change_of_colleague(remote_url: str, root: str) -> None:
    path = os.path.join(root, f"colleague_{time.monotonic_ns()}")
    repo = Repo.clone_from(remote_url, path)
    document = Path(path, "doc.sdoc")
    document.write_text(
        document.read_text(encoding="utf-8").replace("brake", "brake hard"),
        encoding="utf-8",
    )
    repo.index.add(["doc.sdoc"])
    repo.index.commit("Change", author=COLLEAGUE, committer=COLLEAGUE)
    repo.git.push("origin", "main")
    repo.close()


def _wait_for(condition: Callable[[], Any], seconds: float, why: str) -> Any:
    deadline = time.monotonic() + seconds
    while True:
        found = condition()
        if found:
            return found
        assert time.monotonic() < deadline, why
        time.sleep(0.25)


@pytest.mark.skipif(
    sys.platform == "win32", reason="The user folders follow XDG variables."
)
class Test(DesktopCase):
    def test_001_a_project_in_english_does_not_change_the_french_of_the_user(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root:
            remote_url, _ = _create_remote(root)
            workspace = os.path.join(root, "workspace")
            os.makedirs(workspace)
            with ExitStack() as stack:
                home = self._start(stack, remote_url)

                # From the home screen, signed in or not, to the settings.
                self.open(home)
                self.click(SIGN_IN)
                self.assert_text(DISPLAY_NAME)
                self.click(SETTINGS_LINK)
                self.assert_element(LANGUAGE)
                # The sign-out is reachable from the settings too.
                self.assert_element('[data-testid="sign-out"]')
                self._save_settings("fr", "5")
                self.assert_text("Les réglages sont enregistrés.", SAVED)
                assert self.get_attribute("html", "lang") == "fr"

                # A project declared in English is shown in French, and the
                # home screen is still in French when the user comes back.
                self.click('[data-testid="back-to-catalog"]')
                self.click(OPEN_BUTTON)
                self.type(FOLDER_INPUT, workspace)
                self.click(FOLDER_SUBMIT)
                self.assert_text(DOCUMENT_TITLE)
                assert self.get_attribute("html", "lang") == "fr"
                assert "analyse" in self.get_text("body").lower()
                self.open(home)
                self.assert_text("Projets")
                assert self.get_attribute("html", "lang") == "fr"
                self.assert_element('[data-testid="sign-out"]')

    def test_002_the_pages_of_an_open_project_follow_the_language(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            remote_url, _ = _create_remote(root)
            workspace = os.path.join(root, "workspace")
            os.makedirs(workspace)
            with ExitStack() as stack:
                home = self._start(stack, remote_url)
                self.open(home)
                self.click(SIGN_IN)
                self.assert_text(DISPLAY_NAME)
                self.click(OPEN_BUTTON)
                self.type(FOLDER_INPUT, workspace)
                self.click(FOLDER_SUBMIT)
                self.assert_text(DOCUMENT_TITLE)
                Screen_ProjectIndex(self).do_click_on_first_document()
                self.assert_text("The system shall brake.")
                document_url = self.get_current_url()
                assert self.get_attribute("html", "lang") == "en"
                assert "analysis" in self.get_text("body").lower()

                # The language changes with the project open, with no restart.
                self.open(home + "settings")
                self._save_settings("fr", "5")
                self.assert_text("Les réglages sont enregistrés.", SAVED)

                # The page that the server made in English is made again.
                self.open(document_url)
                self.assert_text("The system shall brake.")
                assert self.get_attribute("html", "lang") == "fr"
                text = self.get_text("body").lower()
                assert "analyse" in text and "analysis" not in text

                # Back to the default, which is English here.
                self.open(home + "settings")
                self._save_settings("", "5")
                assert self.get_attribute("html", "lang") == "en"
                self.open(document_url)
                assert self.get_attribute("html", "lang") == "en"

    def test_003_the_interval_changes_with_no_restart(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            remote_url, _ = _create_remote(root)
            workspace = os.path.join(root, "workspace")
            os.makedirs(workspace)
            with ExitStack() as stack:
                home = self._start(stack, remote_url)
                self.open(home)
                self.click(SIGN_IN)
                self.assert_text(DISPLAY_NAME)
                self.click(OPEN_BUTTON)
                self.type(FOLDER_INPUT, workspace)
                self.click(FOLDER_SUBMIT)
                self.assert_text(DOCUMENT_TITLE)

                # A wrong number writes nothing and says why.
                self.open(home + "settings")
                self._save_settings(
                    "", "0", '[data-testid="settings-interval-error"]'
                )
                self.assert_text("from 1 to 120")

                # The project was opened with 5 minutes between two updates:
                # one minute applies to the timer that runs, with no restart.
                self.open(home + "settings")
                self._save_settings("", "1")
                _push_change_of_colleague(remote_url, root)
                _wait_for(
                    lambda: (
                        "brake hard"
                        in Path(workspace, "doc.sdoc").read_text(
                            encoding="utf-8"
                        )
                    ),
                    100,
                    "The project was not updated by its timer.",
                )

    # ---- What the tests do with the application

    def _start(self, stack: ExitStack, remote_url: str) -> str:
        fake_gitlab = stack.enter_context(FakeGitLab())
        fake_gitlab.add_project(
            1, "ISIS", remote_url, MAINTAINER, subgroup="satellites"
        )
        user_path = stack.enter_context(tempfile.TemporaryDirectory())
        test_setup = End2EndTestSetup(path_to_test_file=__file__)
        test_server = stack.enter_context(
            DesktopTestServer(
                input_path=test_setup.path_to_sandbox,
                gitlab_url=fake_gitlab.url,
                oauth_client_id=CLIENT_ID,
                gitlab_projects_root=GROUP_PATH,
                user_path=user_path,
            )
        )
        start_url: str = test_server.get_start_url()
        self.open(start_url)
        return f"http://127.0.0.1:{test_server.server_port}/"

    def _save_settings(
        self, language: str, interval: str, answer: str = SAVED
    ) -> None:
        """Fill the form, save it, and wait for the answer of the server."""
        self.assert_element(LANGUAGE)
        if language == "":
            # The first choice of the list is "Default".
            self.select_option_by_index(LANGUAGE, 0)
        else:
            self.select_option_by_value(LANGUAGE, language)
        self.type(INTERVAL, interval)
        self.click(SAVE)
        self.assert_element(answer)
