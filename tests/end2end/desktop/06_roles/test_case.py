"""
@relation(SDOC-SRS-1237, scope=file)
@relation(SDOC-SRS-1240, scope=file)
"""

import os
import sys
import tempfile

import pytest

from tests.end2end.desktop.desktop_case import DesktopCase
from tests.end2end.desktop.desktop_projects import create_remote
from tests.end2end.desktop.desktop_test_server import DesktopTestServer
from tests.end2end.desktop.fake_gitlab import (
    CLIENT_ID,
    DEVELOPER,
    DISPLAY_NAME,
    GROUP_PATH,
    REPORTER,
    FakeGitLab,
)
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)

IDENTIFIER = "1"
DOCUMENT_TITLE = "Document of GitLab"

SIGN_IN = '[data-testid="sign-in"]'
SIGN_IN_REQUIRED = '[data-testid="catalog-sign-in-required"]'
SIGNED_IN_USER = '[data-testid="signed-in-user"]'
PROJECT = '[data-testid="catalog-project"]'
PROJECT_TITLE = ".catalog__project_title"
PROJECT_ROLE = ".catalog__project_role"
OPEN_BUTTON = '[data-testid="catalog-project-open"]'
FOLDER_INPUT = '[data-testid="folder-input"]'
FOLDER_SUBMIT = '[data-testid="folder-submit"]'
MESSAGE = '[data-testid="message-text"]'
EDIT_ACTION = '[data-testid="node-edit-action"]'
DELETE_ACTION = '[data-testid="document-delete-action"]'


def _create_folder(root: str) -> str:
    """An empty folder, for the clone of the project."""
    folder = os.path.join(root, "workspace")
    os.makedirs(folder)
    return folder


@pytest.mark.skipif(
    sys.platform == "win32", reason="The user folders follow XDG variables."
)
class Test(DesktopCase):
    """
    The catalog is the one of GitLab, with the projects of the signed-in user.
    The role in a project follows the access level that GitLab gives: the
    actions that the role does not allow are disabled, and a project that the
    user cannot see any more does not open.
    """

    def test_001_a_reader_sees_the_actions_of_an_author_disabled(
        self,
    ) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with tempfile.TemporaryDirectory() as root:
            remote_url = create_remote(root, "remote", DOCUMENT_TITLE)
            with FakeGitLab() as fake_gitlab:
                fake_gitlab.add_project(
                    1, "ISIS", remote_url, REPORTER, subgroup="satellites"
                )
                with self._create_server(
                    test_setup, fake_gitlab
                ) as test_server:
                    self.open(test_server.get_start_url())

                    # Before the sign-in the catalog asks for it, and GitLab
                    # was not asked for any project.
                    self.assert_element(SIGN_IN_REQUIRED)
                    assert fake_gitlab.project_request_count == 0
                    self.click(SIGN_IN)
                    self.assert_text(DISPLAY_NAME, SIGNED_IN_USER)

                    # The project of the group, with the role that the access
                    # level Reporter gives.
                    self.assert_text("ISIS", PROJECT_TITLE)
                    # The page shows the role in capital letters.
                    self.assert_text("READER", PROJECT_ROLE)
                    self.click(OPEN_BUTTON)
                    self.type(FOLDER_INPUT, _create_folder(root))
                    self.click(FOLDER_SUBMIT)
                    self.assert_text(DOCUMENT_TITLE)

                    screen_project_index = Screen_ProjectIndex(self)
                    screen_document = (
                        screen_project_index.do_click_on_first_document()
                    )
                    screen_document.assert_on_screen_document()

                    # The edit action is on the page, disabled, with the reason.
                    self.wait_for_element_present(
                        f'{EDIT_ACTION}[aria-disabled="true"]'
                    )
                    assert (
                        self.get_attribute(
                            EDIT_ACTION, "title", hard_fail=False
                        )
                        == "Needs the author role"
                    )

                    # The buttons of the login proxy are not there: the log out
                    # goes to a page that only the proxy has, and the audit log
                    # exists only behind it.
                    self.assert_element_absent('[data-testid="nav-logout"]')
                    self.assert_element_absent('[data-testid="nav-audit"]')

                    # A click on it opens no form.
                    self.execute_script(
                        f"document.querySelector('{EDIT_ACTION}').click()"
                    )
                    self.sleep(1)
                    self.assert_element_absent(
                        '[data-testid="form-cancel-action"]'
                    )

    def test_002_a_developer_edits_and_does_not_delete(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with tempfile.TemporaryDirectory() as root:
            remote_url = create_remote(root, "remote", DOCUMENT_TITLE)
            with FakeGitLab() as fake_gitlab:
                fake_gitlab.add_project(
                    1, "ISIS", remote_url, DEVELOPER, subgroup="satellites"
                )
                with self._create_server(
                    test_setup, fake_gitlab
                ) as test_server:
                    self.open(test_server.get_start_url())
                    self.click(SIGN_IN)
                    self.assert_text("AUTHOR", PROJECT_ROLE)
                    self.click(OPEN_BUTTON)
                    self.type(FOLDER_INPUT, _create_folder(root))
                    self.click(FOLDER_SUBMIT)
                    self.assert_text(DOCUMENT_TITLE)
                    screen_document = Screen_ProjectIndex(
                        self
                    ).do_click_on_first_document()
                    screen_document.assert_on_screen_document()

                    # The author role allows the edit and not the delete.
                    self.wait_for_element_present(
                        f'{DELETE_ACTION}[aria-disabled="true"]'
                    )
                    assert (
                        self.get_attribute(
                            DELETE_ACTION, "title", hard_fail=False
                        )
                        == "Needs the administrator role"
                    )
                    self.assert_element_absent(
                        f'{EDIT_ACTION}[aria-disabled="true"]'
                    )

    def test_003_a_project_that_the_user_cannot_see_any_more_does_not_open(
        self,
    ) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with tempfile.TemporaryDirectory() as root:
            remote_url = create_remote(root, "remote", DOCUMENT_TITLE)
            with FakeGitLab() as fake_gitlab:
                fake_gitlab.add_project(
                    1, "ISIS", remote_url, REPORTER, subgroup="satellites"
                )
                with self._create_server(
                    test_setup, fake_gitlab
                ) as test_server:
                    self.open(test_server.get_start_url())
                    self.click(SIGN_IN)
                    self.click(OPEN_BUTTON)
                    self.type(FOLDER_INPUT, _create_folder(root))
                    self.click(FOLDER_SUBMIT)
                    self.assert_text(DOCUMENT_TITLE)

                    # The rights are removed in GitLab. The home screen no
                    # longer lists the project, and a request to open it
                    # (a page that was loaded before) says why it does not.
                    self.open(test_server.get_home_url())
                    self.assert_element(PROJECT)
                    del fake_gitlab.access_levels[1]
                    self.execute_script(
                        "document.querySelector('.catalog__open').submit()"
                    )
                    self.assert_text(
                        "You no longer have access to this project.", MESSAGE
                    )
                    self.open(test_server.get_home_url())
                    self.assert_element_absent(PROJECT)

    @staticmethod
    def _create_server(
        test_setup: End2EndTestSetup, fake_gitlab: FakeGitLab
    ) -> DesktopTestServer:
        return DesktopTestServer(
            input_path=test_setup.path_to_sandbox,
            gitlab_url=fake_gitlab.url,
            oauth_client_id=CLIENT_ID,
            gitlab_projects_root=GROUP_PATH,
        )
