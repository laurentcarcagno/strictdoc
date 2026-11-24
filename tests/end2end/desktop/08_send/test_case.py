"""
The changes that the user saves are sent to the server, and none is lost when
the server cannot be reached or when the application closes.

@relation(SDOC-SRS-1242, scope=file)
@relation(SDOC-SRS-1243, scope=file)
@relation(SDOC-SRS-1244, scope=file)
"""

import os
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Tuple

import pytest
from git import Actor, Repo

from tests.end2end.desktop.desktop_case import DesktopCase
from tests.end2end.desktop.desktop_test_server import DesktopTestServer
from tests.end2end.desktop.fake_gitlab import (
    CLIENT_ID,
    DEVELOPER,
    DISPLAY_NAME,
    GROUP_PATH,
    FakeGitLab,
)
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)

DOCUMENT_TITLE = "Document to send"
SEED_AUTHOR = Actor("Seed", "seed@example.org")

SIGN_IN = '[data-testid="sign-in"]'
SIGNED_IN_USER = '[data-testid="signed-in-user"]'
OPEN_BUTTON = '[data-testid="catalog-project-open"]'
FOLDER_INPUT = '[data-testid="folder-input"]'
FOLDER_SUBMIT = '[data-testid="folder-submit"]'
INDICATOR = '[data-testid="desktop-indicator"]'
UNSENT_MARK = '[data-testid="catalog-project-unsent"]'
WAIT_SECONDS = 30.0
# The queue tries again after a wait that grows up to one minute.
SEND_SECONDS = 120.0


def _create_remote(root: str) -> Tuple[str, str]:
    """
    A bare repository of a project with one document and one requirement. It
    returns the URL of the remote and the path of the bare repository.
    """
    work_path = os.path.join(root, "remote_work")
    os.makedirs(work_path)
    Path(work_path, "doc.sdoc").write_text(
        "[DOCUMENT]\n"
        f"TITLE: {DOCUMENT_TITLE}\n"
        "\n"
        "[REQUIREMENT]\n"
        "UID: REQ-1\n"
        "TITLE: Braking\n"
        "STATEMENT: The system shall brake.\n",
        encoding="utf-8",
    )
    work_repo = Repo.init(work_path, initial_branch="main")
    work_repo.index.add(["doc.sdoc"])
    work_repo.index.commit("Seed", author=SEED_AUTHOR, committer=SEED_AUTHOR)
    work_repo.close()
    bare_path = os.path.join(root, "remote.git")
    Repo.clone_from(work_path, bare_path, bare=True).close()
    return f"file://{bare_path}", bare_path


def _count_commits(path: str) -> int:
    repo = Repo(path)
    try:
        return len(list(repo.iter_commits("main")))
    finally:
        repo.close()


def _wait_for(condition: Callable[[], bool], seconds: float, why: str) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, why
        time.sleep(0.5)


@pytest.mark.skipif(
    sys.platform == "win32", reason="The user folders follow XDG variables."
)
class Test(DesktopCase):
    """
    The server of the project goes out of reach, the user saves, the
    application closes and starts again: the change is sent when the server
    is back, and the indicator tells what waits until then.
    """

    def test_001_a_change_waits_for_the_server_and_goes_after_a_restart(
        self,
    ) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with tempfile.TemporaryDirectory() as root:
            remote_url, bare_path = _create_remote(root)
            away_path = os.path.join(root, "remote-away.git")
            workspace = os.path.join(root, "workspace")
            os.makedirs(workspace)
            with _create_environment(remote_url) as (fake_gitlab, user_path):
                with self._create_server(
                    test_setup, fake_gitlab, user_path
                ) as test_server:
                    self.open(test_server.get_start_url())
                    self.click(SIGN_IN)
                    self.click(OPEN_BUTTON)
                    self.type(FOLDER_INPUT, workspace)
                    self.click(FOLDER_SUBMIT)
                    self.assert_text(DOCUMENT_TITLE)
                    assert _count_commits(workspace) == 1

                    # The server goes out of reach: its folder is renamed.
                    os.rename(bare_path, away_path)

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
                    # The save does not wait for the network: it is in the
                    # working copy.
                    _wait_for(
                        lambda: _count_commits(workspace) == 2,
                        WAIT_SECONDS,
                        "No commit.",
                    )
                    # The indicator tells that the change waits.
                    self.wait_for_element_visible(
                        INDICATOR, timeout=WAIT_SECONDS
                    )
                    assert (
                        self.get_attribute(INDICATOR, "data-state")
                        == "waiting_network"
                    )
                    text = self.get_text(INDICATOR)
                    assert "network" in text
                    assert "git" not in text.lower()

                # The application is closed: the change is in the working copy.
                assert _count_commits(workspace) == 2
                assert os.path.isdir(away_path)

                with self._create_server(
                    test_setup, fake_gitlab, user_path
                ) as test_server:
                    # The second launch is signed in with no new sign-in, and
                    # the home page marks the project: the queue read the
                    # folder, with no server of the project open.
                    self.open(test_server.get_start_url())
                    self.assert_text(DISPLAY_NAME, SIGNED_IN_USER)
                    self._wait_for_mark(is_expected=True)

                    # The server is back: the change goes with no action.
                    os.rename(away_path, bare_path)
                    _wait_for(
                        lambda: _count_commits(bare_path) == 2,
                        SEND_SECONDS,
                        "The change was not sent.",
                    )
                    self._wait_for_mark(is_expected=False)

                    self.click(OPEN_BUTTON)
                    self.assert_text(DOCUMENT_TITLE)
                    self.wait_for_element_not_visible(
                        INDICATOR, timeout=WAIT_SECONDS
                    )

    def _wait_for_mark(self, *, is_expected: bool) -> None:
        deadline = time.monotonic() + WAIT_SECONDS
        while True:
            self.refresh_page()
            self.assert_text(DISPLAY_NAME, SIGNED_IN_USER)
            if self.is_element_present(UNSENT_MARK) == is_expected:
                return
            assert time.monotonic() < deadline, "The mark is not as expected."
            time.sleep(0.5)

    def _create_server(
        self,
        test_setup: End2EndTestSetup,
        fake_gitlab: FakeGitLab,
        user_path: str,
    ) -> DesktopTestServer:
        return DesktopTestServer(
            input_path=test_setup.path_to_sandbox,
            gitlab_url=fake_gitlab.url,
            oauth_client_id=CLIENT_ID,
            gitlab_projects_root=GROUP_PATH,
            user_path=user_path,
        )


@contextmanager
def _create_environment(remote_url: str) -> Iterator[Tuple[FakeGitLab, str]]:
    """The fake GitLab and the user folder that two launches share."""
    with FakeGitLab() as fake_gitlab:
        fake_gitlab.add_project(
            1, "ISIS", remote_url, DEVELOPER, subgroup="satellites"
        )
        with tempfile.TemporaryDirectory() as user_path:
            yield fake_gitlab, user_path
