"""
@relation(SDOC-SRS-1229, scope=file)
"""

import os
import sys
from typing import List

import pytest
from selenium.webdriver.common.keys import Keys

from tests.end2end.desktop.desktop_test_server import DesktopTestServer
from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup

WELCOME = '[data-testid="home-welcome"]'
FOLDER = '[data-testid="catalog-folder"]'
PROJECT = '[data-testid="catalog-project"]'
SEARCH = '[data-testid="catalog-search"]'
NO_MATCH = '[data-testid="catalog-no-match"]'
FOLDER_NAME = ".catalog__folder_name"
PROJECT_TITLE = ".catalog__project_title"
PROJECT_ROLE = ".catalog__project_role"


@pytest.mark.skipif(
    sys.platform == "win32", reason="The user folders follow XDG variables."
)
class Test(E2ECase):
    """
    The first launch of the application: no project is open, the welcome
    message and the catalog are shown, and the search filters the catalog.
    """

    def test_001_first_launch_shows_the_catalog(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with DesktopTestServer(
            input_path=test_setup.path_to_sandbox,
            fake_catalog_path=os.path.join(
                test_setup.path_to_sandbox, "catalog.json"
            ),
        ) as test_server:
            self.open(test_server.get_start_url())

            # No project has ever been opened.
            self.assert_element(WELCOME)
            self.assert_text("StrictDoc", "h1")
            self.assert_text("Welcome to StrictDoc", WELCOME)

            # The tree: two folders, three projects, the role of each one.
            assert len(self.find_visible_elements(FOLDER)) == 2
            assert len(self.find_visible_elements(PROJECT)) == 3
            assert self._get_texts(FOLDER_NAME) == ["Lanceurs", "Satellites"]
            assert self._get_texts(PROJECT_TITLE) == [
                "Ariane",
                "ISIS",
                "Pleiades",
            ]
            assert self._get_texts(PROJECT_ROLE) == [
                "reader",
                "administrator",
                "author",
            ]

            # The search keeps the projects whose name contains the text, and
            # the folders that still hold one.
            self.type(SEARCH, "ari")
            self.wait_for_element_not_visible(NO_MATCH)
            assert len(self.find_visible_elements(PROJECT)) == 1
            assert len(self.find_visible_elements(FOLDER)) == 1
            assert self._get_visible_texts(PROJECT_TITLE) == ["Ariane"]

            self.type(SEARCH, "zzz")
            self.wait_for_element_visible(NO_MATCH)
            assert len(self.find_visible_elements(PROJECT)) == 0

            # Erasing the text with the keyboard, as a user does.
            self.send_keys(SEARCH, Keys.BACKSPACE * 3)
            self.wait_for_element_not_visible(NO_MATCH)
            assert len(self.find_visible_elements(PROJECT)) == 3

    def test_002_the_texts_follow_the_language(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with DesktopTestServer(
            input_path=test_setup.path_to_sandbox,
            fake_catalog_path=os.path.join(
                test_setup.path_to_sandbox, "catalog.json"
            ),
            language="fr",
        ) as test_server:
            self.open(test_server.get_start_url())

            self.assert_text("Bienvenue dans StrictDoc", WELCOME)
            self.assert_text("Projets", "h2")
            assert self._get_texts(PROJECT_ROLE) == [
                "lecteur",
                "administrateur",
                "auteur",
            ]
            self.assert_attribute(
                SEARCH, "placeholder", "Rechercher un projet par nom"
            )

    def test_003_a_catalog_that_fails_shows_a_message(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with DesktopTestServer(
            input_path=test_setup.path_to_sandbox,
            fake_catalog_path=os.path.join(
                test_setup.path_to_sandbox, "missing.json"
            ),
        ) as test_server:
            self.open(test_server.get_start_url())

            self.assert_text(
                "The catalog of projects cannot be shown.",
                '[data-testid="catalog-error"]',
            )
            self.assert_text("missing.json", '[data-testid="catalog-error"]')
            self.assert_text_not_visible("Traceback")

    def _get_texts(self, selector: str) -> List[str]:
        """
        The text of the elements as the page holds it. The page shows the
        roles in capital letters, which the text shown to the user changes.
        """
        texts: List[str] = self.execute_script(
            "return Array.from(document.querySelectorAll(arguments[0]))"
            ".map(function (element) {"
            "  return element.textContent.trim().replace(/\\s+/g, ' ');"
            "});",
            selector,
        )
        return texts

    def _get_visible_texts(self, selector: str) -> List[str]:
        return [
            element_.get_attribute("textContent").strip()
            for element_ in self.find_visible_elements(selector)
        ]
