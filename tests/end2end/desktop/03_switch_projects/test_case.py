"""
@relation(SDOC-SRS-1232, scope=file)
@relation(SDOC-SRS-1233, scope=file)
"""

import os
import shutil
import sys
import tempfile
import time
from typing import Dict

import pytest
from selenium.webdriver.common.by import By

from tests.end2end.desktop.desktop_projects import (
    add_document_to_remote,
    create_remote,
    write_catalog,
)
from tests.end2end.desktop.desktop_test_server import DesktopTestServer
from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)

FOLDER_INPUT = '[data-testid="folder-input"]'
FOLDER_SUBMIT = '[data-testid="folder-submit"]'
OPENED_MARK = '[data-testid="catalog-project-opened"]'

# The return to an open project must show its page in less than this.
SWITCH_LIMIT_SECONDS = 0.5
# How long the test waits for something that is not about the speed.
WAIT_SECONDS = 20


def _get_open_button(project_title: str) -> str:
    return (
        f'[data-name="{project_title.lower()}"] '
        '[data-testid="catalog-project-open"]'
    )


def _get_document_link(document_title: str) -> str:
    return (
        "//*[@data-testid='tree-file-link']"
        f"//*[contains(., '{document_title}')]"
    )


class Projects:
    """Two projects with their remote, their folder and the catalog."""

    def __init__(self, root: str) -> None:
        self.root: str = root
        self.user_path: str = os.path.join(root, "user")
        self.catalog_path: str = os.path.join(root, "catalog.json")
        self.remote_urls: Dict[str, str] = {}
        self.folders: Dict[str, str] = {}
        for name_ in ("Alpha", "Beta"):
            self.remote_urls[name_] = create_remote(
                root, name_.lower(), f"Document {name_}"
            )
            self.folders[name_] = os.path.join(root, f"folder_{name_}")
            os.makedirs(self.folders[name_])
        write_catalog(
            self.catalog_path,
            [
                {
                    "identifier": f"demo/{name_.lower()}",
                    "title": name_,
                    "display_path": f"Satellites/{name_}",
                    "clone_url": self.remote_urls[name_],
                }
                for name_ in ("Alpha", "Beta")
            ],
        )


@pytest.mark.skipif(
    sys.platform == "win32", reason="The user folders follow XDG variables."
)
class Test(E2ECase):
    """
    The user works on a project, goes back to the home screen, opens another
    project and comes back: the server of the first project still runs, so the
    return is immediate and the work is there.
    """

    def test_001_return_to_an_open_project_is_immediate(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)
        with tempfile.TemporaryDirectory() as root:
            projects = Projects(root)
            with DesktopTestServer(
                input_path=test_setup.path_to_sandbox,
                fake_catalog_path=projects.catalog_path,
                user_path=projects.user_path,
            ) as test_server:
                self.open(test_server.get_start_url())
                self._open_for_the_first_time(projects, "Alpha")
                self._create_document("Created in Alpha", "created_in_alpha")

                self.open(test_server.get_home_url())
                self.assert_element(OPENED_MARK)
                assert len(self.find_elements(OPENED_MARK)) == 1

                self._open_for_the_first_time(projects, "Beta")
                self.assert_element(
                    _get_document_link("Document Beta"), by=By.XPATH
                )
                assert not self.is_element_present(
                    _get_document_link("Created in Alpha"), by=By.XPATH
                )

                # Back to Alpha: the document of the work is there, at once.
                self.open(test_server.get_home_url())
                self.wait_for_element_present(OPENED_MARK)
                assert len(self.find_elements(OPENED_MARK)) == 2
                duration = self._measure_switch(
                    "Alpha", _get_document_link("Created in Alpha")
                )
                print(f"Switch to an open project: {duration:.3f} s.")  # noqa: T201
                assert duration < SWITCH_LIMIT_SECONDS

                # And back to Beta, which still runs too.
                self.open(test_server.get_home_url())
                self.wait_for_element_present(OPENED_MARK)
                duration = self._measure_switch(
                    "Beta", _get_document_link("Document Beta")
                )
                print(f"Switch to an open project: {duration:.3f} s.")  # noqa: T201
                assert duration < SWITCH_LIMIT_SECONDS

    def test_002_oldest_server_stops_above_the_number_to_keep(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)
        with tempfile.TemporaryDirectory() as root:
            projects = Projects(root)
            with DesktopTestServer(
                input_path=test_setup.path_to_sandbox,
                fake_catalog_path=projects.catalog_path,
                user_path=projects.user_path,
                kept_servers=1,
            ) as test_server:
                self.open(test_server.get_start_url())
                self._open_for_the_first_time(projects, "Alpha")
                self.open(test_server.get_home_url())
                self._open_for_the_first_time(projects, "Beta")
                self.assert_element(
                    _get_document_link("Document Beta"), by=By.XPATH
                )

                # The server of Alpha stops after the page of Beta is shown:
                # the catalog lists Alpha, then Beta.
                self.open(test_server.get_home_url())
                deadline = time.monotonic() + WAIT_SECONDS
                while (
                    len(self.find_elements(OPENED_MARK)) != 1
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.2)
                    self.open(test_server.get_home_url())
                assert [
                    element_.get_attribute("data-open")
                    for element_ in self.find_elements("[data-open]")
                ] == ["false", "true"]

                # Alpha opens again, with a new server and its work.
                self.click(_get_open_button("Alpha"))
                self.assert_element(
                    _get_document_link("Document Alpha"), by=By.XPATH
                )

    def test_003_project_is_updated_from_its_remote_in_the_background(
        self,
    ) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)
        with tempfile.TemporaryDirectory() as root:
            projects = Projects(root)
            with DesktopTestServer(
                input_path=test_setup.path_to_sandbox,
                fake_catalog_path=projects.catalog_path,
                user_path=projects.user_path,
            ) as test_server:
                self.open(test_server.get_start_url())
                self._open_for_the_first_time(projects, "Alpha")
                self.assert_element(
                    _get_document_link("Document Alpha"), by=By.XPATH
                )

                # A colleague adds a document to the remote.
                add_document_to_remote(
                    projects.remote_urls["Alpha"],
                    os.path.join(root, "colleague"),
                    "colleague.sdoc",
                    "Added by a colleague",
                )

                # Back to the project: the page does not wait for the update,
                # and the new document appears when the server has read it.
                self.open(test_server.get_home_url())
                self.click(_get_open_button("Alpha"))
                self.assert_element(
                    _get_document_link("Document Alpha"), by=By.XPATH
                )
                self.wait_for_element_present(
                    _get_document_link("Added by a colleague"),
                    by=By.XPATH,
                    timeout=WAIT_SECONDS,
                )
                assert os.path.isfile(
                    os.path.join(projects.folders["Alpha"], "colleague.sdoc")
                )

    def test_004_offline_project_opens_without_an_error(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)
        with tempfile.TemporaryDirectory() as root:
            projects = Projects(root)
            with DesktopTestServer(
                input_path=test_setup.path_to_sandbox,
                fake_catalog_path=projects.catalog_path,
                user_path=projects.user_path,
            ) as test_server:
                self.open(test_server.get_start_url())
                self._open_for_the_first_time(projects, "Alpha")

                # The remote is gone, as with no network.
                shutil.rmtree(projects.remote_urls["Alpha"][len("file://") :])

                self.open(test_server.get_home_url())
                self.click(_get_open_button("Alpha"))
                self.assert_element(
                    _get_document_link("Document Alpha"), by=By.XPATH
                )
                self.assert_text_not_visible("fatal")
                Screen_ProjectIndex(self).assert_on_screen()

    def _open_for_the_first_time(
        self, projects: Projects, project_title: str
    ) -> None:
        self.click(_get_open_button(project_title))
        self.type(FOLDER_INPUT, projects.folders[project_title])
        self.click(FOLDER_SUBMIT)
        self.assert_element(
            _get_document_link(f"Document {project_title}"), by=By.XPATH
        )

    def _create_document(self, title: str, file_name: str) -> None:
        screen_project_index = Screen_ProjectIndex(self)
        screen_project_index.assert_on_screen()
        form_add_document = (
            screen_project_index.do_open_modal_form_add_document()
        )
        form_add_document.do_fill_in_title(title)
        form_add_document.do_fill_in_path(f"{file_name}.sdoc")
        form_add_document.do_form_submit()
        self.open(self.get_current_url())
        screen_project_index.assert_on_screen()

    def _measure_switch(self, project_title: str, element_xpath: str) -> float:
        """
        The time between the click on the project in the catalog and the
        presence of an element of the page of the project.
        """
        started_at = time.monotonic()
        self.click(_get_open_button(project_title))
        deadline = started_at + WAIT_SECONDS
        while not self.is_element_present(element_xpath, by=By.XPATH):
            assert time.monotonic() < deadline, "The project page did not show."
        return time.monotonic() - started_at
