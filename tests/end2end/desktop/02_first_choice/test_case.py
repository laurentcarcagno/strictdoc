"""
@relation(SDOC-SRS-1230, scope=file)
@relation(SDOC-SRS-1231, scope=file)
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict

import pytest
from git import Actor, Repo

from strictdoc.features.desktop.settings import load_settings
from tests.end2end.desktop.desktop_test_server import DesktopTestServer
from tests.end2end.e2e_case import E2ECase
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

    def __init__(self, root: str, clone_url: str = "") -> None:
        self.root: str = root
        self.user_path: str = os.path.join(root, "user")
        self.empty_folder: str = os.path.join(root, "workspace")
        self.catalog_path: str = os.path.join(root, "catalog.json")
        self.remote_url: str = self._create_remote()
        self.write_catalog(clone_url if clone_url != "" else self.remote_url)

    def write_catalog(self, clone_url: str) -> None:
        with open(self.catalog_path, "w", encoding="utf-8") as file_:
            json.dump(
                [
                    {
                        "identifier": IDENTIFIER,
                        "title": "ISIS",
                        "display_path": "Satellites/ISIS",
                        "description": "",
                        "clone_url": clone_url,
                        "role": "author",
                    }
                ],
                file_,
            )

    def _create_remote(self) -> str:
        work_path = os.path.join(self.root, "work")
        os.makedirs(work_path)
        with open(
            os.path.join(work_path, "doc.sdoc"), "w", encoding="utf-8"
        ) as file_:
            file_.write(
                "[DOCUMENT]\n"
                f"TITLE: {DOCUMENT_TITLE}\n"
                "\n"
                "[REQUIREMENT]\n"
                "UID: REQ-1\n"
                "TITLE: Braking\n"
                "STATEMENT: The system shall brake.\n"
            )
        work_repo = Repo.init(work_path)
        work_repo.index.add(["doc.sdoc"])
        actor = Actor("Test", "test@example.org")
        work_repo.index.commit(
            "Add the document", author=actor, committer=actor
        )
        work_repo.close()
        bare_path = os.path.join(self.root, "remote.git")
        Repo.clone_from(work_path, bare_path, bare=True).close()
        return f"file://{bare_path}"


def _get_project_folders(user_path: str) -> Dict[str, str]:
    settings_path = os.path.join(
        user_path, "config", "StrictDoc", "settings.json"
    )
    return load_settings(Path(settings_path)).project_folders


@pytest.mark.skipif(
    sys.platform == "win32", reason="The user folders follow XDG variables."
)
class Test(E2ECase):
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
                assert _get_project_folders(workspace.user_path) == {}
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
                assert _get_project_folders(workspace.user_path) == {
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
                assert _get_project_folders(workspace.user_path) == {}

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
                assert _get_project_folders(workspace.user_path) == {
                    IDENTIFIER: new_folder
                }
