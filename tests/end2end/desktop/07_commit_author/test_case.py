"""
@relation(SDOC-SRS-1238, scope=file)
"""

import os
import sys
import tempfile
import time
from typing import Tuple

import pytest
from git import Actor, Repo

from tests.end2end.desktop.desktop_case import DesktopCase
from tests.end2end.desktop.desktop_test_server import DesktopTestServer
from tests.end2end.desktop.fake_gitlab import (
    CLIENT_ID,
    DEVELOPER,
    DISPLAY_NAME,
    GROUP_PATH,
    USER_ID,
    USERNAME,
    FakeGitLab,
)
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)

DOCUMENT_TITLE = "Document of GitLab"
SEED_AUTHOR = Actor("Seed", "seed@example.org")

SIGN_IN = '[data-testid="sign-in"]'
OPEN_BUTTON = '[data-testid="catalog-project-open"]'
FOLDER_INPUT = '[data-testid="folder-input"]'
FOLDER_SUBMIT = '[data-testid="folder-submit"]'
WAIT_SECONDS = 30.0


def _create_remote(root: str) -> str:
    """
    A bare repository of a project that commits what the application writes
    (the feature GIT is on), with one document and one requirement.
    """
    work_path = os.path.join(root, "remote_work")
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
    with open(
        os.path.join(work_path, "strictdoc_config.py"), "w", encoding="utf-8"
    ) as file_:
        file_.write(
            "from strictdoc.core.project_config import ProjectConfig\n"
            "from strictdoc.features.git_config.config import GitConfig\n"
            "\n"
            "\n"
            "def create_config() -> ProjectConfig:\n"
            "    return ProjectConfig(\n"
            '        project_title="Commit author",\n'
            '        project_features=["GIT"],\n'
            "        git=GitConfig(push_on_tag=False),\n"
            "    )\n"
        )
    work_repo = Repo.init(work_path)
    work_repo.index.add(["doc.sdoc", "strictdoc_config.py"])
    work_repo.index.commit("Seed", author=SEED_AUTHOR, committer=SEED_AUTHOR)
    work_repo.close()
    bare_path = os.path.join(root, "remote.git")
    Repo.clone_from(work_path, bare_path, bare=True).close()
    return f"file://{bare_path}"


def _get_last_commit(folder: str) -> Tuple[str, str, int]:
    """The author name and email of the last commit, and the commit count."""
    repo = Repo(folder)
    try:
        commit = repo.head.commit
        count = len(list(repo.iter_commits()))
        return str(commit.author.name), str(commit.author.email), count
    finally:
        repo.close()


@pytest.mark.skipif(
    sys.platform == "win32", reason="The user folders follow XDG variables."
)
class Test(DesktopCase):
    """
    A node that the user edits in a project of GitLab is committed in the
    working copy with the user who signed in as author, whatever the author
    that the project configuration would name.
    """

    def test_001_the_commit_has_the_signed_in_user_as_author(self) -> None:
        email = "jeanne.dupont@example.org"

        name, address, count = self._edit_node_of_project(
            user_email=email, public_email="", commit_email=""
        )

        assert count == 2
        assert (name, address) == (DISPLAY_NAME, email)

    def test_002_a_private_email_gives_the_public_email(self) -> None:
        name, address, _ = self._edit_node_of_project(
            user_email="", public_email="public@example.org", commit_email=""
        )

        assert (name, address) == (DISPLAY_NAME, "public@example.org")

    def test_003_no_email_gives_the_noreply_address_of_gitlab(self) -> None:
        name, address, _ = self._edit_node_of_project(
            user_email="", public_email="", commit_email=""
        )

        assert (name, address) == (
            DISPLAY_NAME,
            f"{USER_ID}-{USERNAME}@users.noreply.localhost",
        )

    def _edit_node_of_project(
        self, *, user_email: str, public_email: str, commit_email: str
    ) -> Tuple[str, str, int]:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with tempfile.TemporaryDirectory() as root:
            remote_url = _create_remote(root)
            workspace = os.path.join(root, "workspace")
            os.makedirs(workspace)
            with FakeGitLab() as fake_gitlab:
                fake_gitlab.user_email = user_email
                fake_gitlab.public_email = public_email
                fake_gitlab.commit_email = commit_email
                fake_gitlab.add_project(
                    1, "ISIS", remote_url, DEVELOPER, subgroup="satellites"
                )
                with DesktopTestServer(
                    input_path=test_setup.path_to_sandbox,
                    gitlab_url=fake_gitlab.url,
                    oauth_client_id=CLIENT_ID,
                    gitlab_projects_root=GROUP_PATH,
                ) as test_server:
                    self.open(test_server.get_start_url())
                    self.click(SIGN_IN)
                    self.click(OPEN_BUTTON)
                    self.type(FOLDER_INPUT, workspace)
                    self.click(FOLDER_SUBMIT)
                    self.assert_text(DOCUMENT_TITLE)
                    assert _get_last_commit(workspace)[2] == 1

                    screen_document = Screen_ProjectIndex(
                        self
                    ).do_click_on_first_document()
                    screen_document.assert_on_screen_document()
                    requirement = screen_document.get_node(1)
                    form = requirement.do_open_form_edit_requirement()
                    form.do_fill_in_field_title("Emergency braking")
                    form.do_form_submit()
                    requirement.assert_requirement_title(
                        "Emergency braking", "1"
                    )

                    # The application commits the document when it saves it.
                    deadline = time.monotonic() + WAIT_SECONDS
                    while _get_last_commit(workspace)[2] < 2:
                        assert time.monotonic() < deadline, "No commit."
                        time.sleep(0.2)
                    return _get_last_commit(workspace)
