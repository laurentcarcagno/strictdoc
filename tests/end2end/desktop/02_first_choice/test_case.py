"""
@relation(SDOC-SRS-1230, scope=file)
@relation(SDOC-SRS-1231, scope=file)
"""

import os
import shutil
import sys
import tempfile

import pytest

from tests.end2end.desktop.desktop_case import DesktopCase
from tests.end2end.desktop.desktop_projects import (
    create_remote,
    get_project_folders,
    write_catalog,
)
from tests.end2end.desktop.desktop_test_server import DesktopTestServer
from tests.end2end.end2end_test_setup import End2EndTestSetup

IDENTIFIER = "demo/isis"
DOCUMENT_TITLE = "Cloned project document"

OPEN_BUTTON = '[data-testid="catalog-project-open"]'
FOLDER_INPUT = '[data-testid="folder-input"]'
FOLDER_SUBMIT = '[data-testid="folder-submit"]'
FOLDER_MESSAGE = '[data-testid="folder-message"]'
JOB_ERROR = '[data-testid="job-error"]'


class Workspace:
    """
    What a test needs outside the application: the remote of the project (a
    bare repository on the disk), the catalog that lists it, and the folders.
    """

    def __init__(self, root: str) -> None:
        self.root: str = root
        self.user_path: str = os.path.join(root, "user")
        self.empty_folder: str = os.path.join(root, "workspace")
        self.catalog_path: str = os.path.join(root, "catalog.json")
        self.remote_url: str = create_remote(root, "remote", DOCUMENT_TITLE)
        self.write_catalog(self.remote_url)

    def write_catalog(self, clone_url: str) -> None:
        write_catalog(
            self.catalog_path,
            [
                {
                    "identifier": IDENTIFIER,
                    "title": "ISIS",
                    "display_path": "Satellites/ISIS",
                    "clone_url": clone_url,
                }
            ],
        )


@pytest.mark.skipif(
    sys.platform == "win32", reason="The user folders follow XDG variables."
)
class Test(DesktopCase):
    """
    The first choice of a project: a folder that cannot be used is refused
    with a message, an empty folder receives the clone and the project opens;
    at the next launch, the project opens without a question.
    """

    def test_001_first_choice_then_second_launch(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)
        with tempfile.TemporaryDirectory() as root:
            workspace = Workspace(root)
            os.makedirs(workspace.empty_folder)
            not_empty_folder = os.path.join(root, "notes")
            os.makedirs(not_empty_folder)
            with open(
                os.path.join(not_empty_folder, "notes.txt"),
                "w",
                encoding="utf-8",
            ) as file_:
                file_.write("notes")

            with DesktopTestServer(
                input_path=test_setup.path_to_sandbox,
                fake_catalog_path=workspace.catalog_path,
                user_path=workspace.user_path,
            ) as test_server:
                self.open(test_server.get_start_url())
                self.click(OPEN_BUTTON)

                # A folder with other files is refused, and nothing is
                # remembered.
                self.type(FOLDER_INPUT, not_empty_folder)
                self.click(FOLDER_SUBMIT)
                self.assert_text("is not empty", FOLDER_MESSAGE)
                assert get_project_folders(workspace.user_path) == {}
                assert os.listdir(not_empty_folder) == ["notes.txt"]

                # An empty folder receives the clone, then the project opens.
                self.type(FOLDER_INPUT, workspace.empty_folder)
                self.click(FOLDER_SUBMIT)
                self.assert_text(DOCUMENT_TITLE)
                assert os.path.isfile(
                    os.path.join(workspace.empty_folder, "doc.sdoc")
                )
                assert os.path.isdir(
                    os.path.join(workspace.empty_folder, ".git")
                )
                assert get_project_folders(workspace.user_path) == {
                    IDENTIFIER: workspace.empty_folder
                }

            with DesktopTestServer(
                input_path=test_setup.path_to_sandbox,
                fake_catalog_path=workspace.catalog_path,
                user_path=workspace.user_path,
            ) as test_server:
                self.open(test_server.get_start_url())
                self.click(OPEN_BUTTON)

                # No question: the project is on the screen.
                self.assert_text(DOCUMENT_TITLE)
                self.assert_element_not_present(FOLDER_INPUT)

    def test_002_failed_clone_is_a_message_and_the_folder_stays_empty(
        self,
    ) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)
        with tempfile.TemporaryDirectory() as root:
            workspace = Workspace(root)
            workspace.write_catalog(f"file://{root}/absent.git")
            os.makedirs(workspace.empty_folder)

            with DesktopTestServer(
                input_path=test_setup.path_to_sandbox,
                fake_catalog_path=workspace.catalog_path,
                user_path=workspace.user_path,
            ) as test_server:
                self.open(test_server.get_start_url())
                self.click(OPEN_BUTTON)
                self.type(FOLDER_INPUT, workspace.empty_folder)
                self.click(FOLDER_SUBMIT)

                self.assert_text("The clone of the project failed", JOB_ERROR)
                assert os.listdir(workspace.empty_folder) == []
                assert get_project_folders(workspace.user_path) == {}

    def test_003_folder_that_disappeared_is_asked_again(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)
        with tempfile.TemporaryDirectory() as root:
            workspace = Workspace(root)
            os.makedirs(workspace.empty_folder)

            with DesktopTestServer(
                input_path=test_setup.path_to_sandbox,
                fake_catalog_path=workspace.catalog_path,
                user_path=workspace.user_path,
            ) as test_server:
                self.open(test_server.get_start_url())
                self.click(OPEN_BUTTON)
                self.type(FOLDER_INPUT, workspace.empty_folder)
                self.click(FOLDER_SUBMIT)
                self.assert_text(DOCUMENT_TITLE)

            shutil.rmtree(workspace.empty_folder)

            with DesktopTestServer(
                input_path=test_setup.path_to_sandbox,
                fake_catalog_path=workspace.catalog_path,
                user_path=workspace.user_path,
            ) as test_server:
                self.open(test_server.get_start_url())
                self.click(OPEN_BUTTON)

                self.assert_text("no longer exists", FOLDER_MESSAGE)
                # A new folder is chosen: the project opens again.
                new_folder = os.path.join(root, "new_workspace")
                os.makedirs(new_folder)
                self.type(FOLDER_INPUT, new_folder)
                self.click(FOLDER_SUBMIT)
                self.assert_text(DOCUMENT_TITLE)
                assert get_project_folders(workspace.user_path) == {
                    IDENTIFIER: new_folder
                }
