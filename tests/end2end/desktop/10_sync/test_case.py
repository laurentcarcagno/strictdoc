"""
The synchronization of the application: what a colleague sends is received
without a question when it touches other nodes, and the window of the merge
opens by itself in the page when both changed the same node.

The project is shared with a colleague: another clone of the same server. The
user types in the WYSIWYG Markdown editor of a node; the update that the
colleague's push causes waits for the end of the typing (see 09_editing), then
the files are combined.

@relation(SDOC-SRS-1245, scope=file)
@relation(SDOC-SRS-1247, scope=file)
@relation(SDOC-SRS-1248, scope=file)
@relation(SDOC-SRS-1250, scope=file)
"""

import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, Tuple

import pytest
from git import Actor, Repo
from selenium.webdriver.common.keys import Keys

from strictdoc.features.desktop.settings import load_settings
from tests.end2end.desktop.desktop_case import DesktopCase
from tests.end2end.desktop.desktop_test_server import DesktopTestServer
from tests.end2end.desktop.fake_gitlab import (
    CLIENT_ID,
    DISPLAY_NAME,
    EMAIL,
    GROUP_PATH,
    MAINTAINER,
    FakeGitLab,
)
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.components.tree_context_menu import TreeContextMenu
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)

DOCUMENT_TITLE = "Shared document"
SEED_AUTHOR = Actor("Seed", "seed@example.org")
COLLEAGUE = Actor("Colleague", "colleague@example.org")
TYPED_TEXT = " Typed here."

SIGN_IN = '[data-testid="sign-in"]'
OPEN_BUTTON = '[data-testid="catalog-project-open"]'
FOLDER_INPUT = '[data-testid="folder-input"]'
FOLDER_SUBMIT = '[data-testid="folder-submit"]'
EDITOR = "sdoc-markdown-editor[data-ready=true] .ProseMirror"
INDICATOR = '[data-testid="desktop-indicator"]'
INDICATOR_ACTION = '[data-testid="desktop-indicator-action"]'
DIALOG = '[data-testid="sync-conflict-dialog"]'
KEEP_LOCAL = '[data-testid="sync-keep-local"]'
FINISH = '[data-testid="sync-finish"]'
ABORT = '[data-testid="sync-abort"]'
LATER = '[data-testid="form-cancel-action"]'
WAIT_SECONDS = 40.0
BANNED_WORDS = re.compile(
    r"\b(git|gitlab|commit|commits|push|pull|branch|merge|rebase|fatal|"
    r"origin|repository|fetch)\b",
    re.IGNORECASE,
)


def _create_remote(root: str) -> Tuple[str, str]:
    """A bare repository of a Markdown document with two requirements."""
    work_path = os.path.join(root, "remote_work")
    os.makedirs(work_path)
    Path(work_path, "doc.sdoc").write_text(
        "[DOCUMENT]\n"
        "MID: 1d6c2b5f8a9e4e1fb7c3a0d4e5f60a11\n"
        f"TITLE: {DOCUMENT_TITLE}\n"
        "OPTIONS:\n"
        "  ENABLE_MID: True\n"
        "  MARKUP: Markdown\n"
        "\n"
        "[REQUIREMENT]\n"
        "MID: 2e7d3c6a9b0f4f2ac8d4b1e5f6a70b22\n"
        "UID: REQ-1\n"
        "STATEMENT: >>>\n"
        "The system shall brake.\n"
        "<<<\n"
        "\n"
        "[REQUIREMENT]\n"
        "MID: 3f8e4d7bac104a3bd9e5c2f6a7b81c33\n"
        "UID: REQ-2\n"
        "STATEMENT: >>>\n"
        "The system shall steer.\n"
        "<<<\n",
        encoding="utf-8",
    )
    work_repo = Repo.init(work_path, initial_branch="main")
    work_repo.index.add(["doc.sdoc"])
    work_repo.index.commit("Seed", author=SEED_AUTHOR, committer=SEED_AUTHOR)
    work_repo.close()
    bare_path = os.path.join(root, "remote.git")
    Repo.clone_from(work_path, bare_path, bare=True).close()
    return f"file://{bare_path}", bare_path


def _push_change_of_colleague(
    remote_url: str, root: str, old_text: str, new_text: str
) -> None:
    """The colleague changes a sentence, commits and sends it."""
    path = os.path.join(root, f"colleague_{time.monotonic_ns()}")
    repo = Repo.clone_from(remote_url, path)
    document = Path(path, "doc.sdoc")
    text = document.read_text(encoding="utf-8")
    assert old_text in text
    document.write_text(text.replace(old_text, new_text), encoding="utf-8")
    repo.index.add(["doc.sdoc"])
    repo.index.commit("Change", author=COLLEAGUE, committer=COLLEAGUE)
    repo.git.push("origin", "main")
    repo.close()


def _read_document(folder: str) -> str:
    return Path(folder, "doc.sdoc").read_text(encoding="utf-8")


def _read_server(bare_path: str, name: str = "doc.sdoc") -> str:
    repo = Repo(bare_path)
    try:
        return str(repo.git.show(f"main:{name}", strip_newline_in_stdout=False))
    finally:
        repo.close()


def _count_parents(bare_path: str) -> int:
    repo = Repo(bare_path)
    try:
        return len(repo.commit("main").parents)
    finally:
        repo.close()


def _wait_for(condition: Callable[[], Any], seconds: float, why: str) -> Any:
    deadline = time.monotonic() + seconds
    while True:
        found = condition()
        if found:
            return found
        assert time.monotonic() < deadline, why
        time.sleep(0.25)


@contextmanager
def _create_environment(remote_url: str) -> Iterator[Tuple[FakeGitLab, str]]:
    with FakeGitLab() as fake_gitlab:
        fake_gitlab.add_project(
            1, "ISIS", remote_url, MAINTAINER, subgroup="satellites"
        )
        with tempfile.TemporaryDirectory() as user_path:
            yield fake_gitlab, user_path


@pytest.mark.skipif(
    sys.platform == "win32", reason="The user folders follow XDG variables."
)
class Test(DesktopCase):
    def test_001_the_same_node_opens_the_window_and_the_choice_is_sent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root:
            remote_url, bare_path = _create_remote(root)
            workspace = os.path.join(root, "workspace")
            os.makedirs(workspace)
            with self._open_project(remote_url, workspace) as test_server:
                form = self._open_editor_and_type(1)
                _push_change_of_colleague(
                    remote_url,
                    root,
                    "The system shall brake.",
                    "The system shall brake hard.",
                )
                self._trigger_update(test_server)
                # The typing ends: the update applies, and both changed the
                # same node. The window opens by itself in the page.
                form.do_form_submit()
                self._wait_for_window()

                # Nothing is sent while the merge waits, and the window has
                # no word of the tool.
                words = BANNED_WORDS.findall(self.get_text(DIALOG))
                assert words == [], words
                assert self.get_attribute(INDICATOR, "data-state") in (
                    "merge_waiting",
                    "idle",
                )
                assert "brake hard" in _read_server(bare_path)
                assert TYPED_TEXT.strip() not in _read_server(bare_path)

                # The user keeps his version. The choice is sent.
                self.click(KEEP_LOCAL)
                self.click(FINISH)
                _wait_for(
                    lambda: _count_parents(bare_path) == 2,
                    WAIT_SECONDS,
                    "The choice was not received by the server.",
                )
                repo = Repo(bare_path)
                head = repo.commit("main")
                assert head.author.email == EMAIL
                assert head.author.name == DISPLAY_NAME
                repo.close()
                assert TYPED_TEXT.strip() in _read_server(bare_path)
                assert "brake hard" not in _read_server(bare_path)
                assert _read_server(bare_path) == _read_document(workspace)
                self.assert_element_not_present(DIALOG)

    def test_002_other_nodes_are_combined_without_a_question(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            remote_url, bare_path = _create_remote(root)
            workspace = os.path.join(root, "workspace")
            os.makedirs(workspace)
            with self._open_project(remote_url, workspace) as test_server:
                form = self._open_editor_and_type(1)
                _push_change_of_colleague(
                    remote_url,
                    root,
                    "The system shall steer.",
                    "The system shall steer left.",
                )
                self._trigger_update(test_server)
                form.do_form_submit()

                # Both changes are in the server, in one merge made by the
                # user, and the window never opened.
                _wait_for(
                    lambda: _count_parents(bare_path) == 2,
                    WAIT_SECONDS,
                    "The combination was not received by the server.",
                )
                text = _read_server(bare_path)
                assert TYPED_TEXT.strip() in text and "steer left" in text
                repo = Repo(bare_path)
                assert repo.commit("main").author.email == EMAIL
                repo.close()
                assert _read_document(workspace) == text
                self.assert_element_not_present(DIALOG)
                self.assert_text("The system shall steer left.")

    def test_003_later_leaves_a_notice_that_opens_the_window_again(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root:
            remote_url, bare_path = _create_remote(root)
            workspace = os.path.join(root, "workspace")
            os.makedirs(workspace)
            with self._open_project(remote_url, workspace) as test_server:
                form = self._open_editor_and_type(1)
                _push_change_of_colleague(
                    remote_url,
                    root,
                    "The system shall brake.",
                    "The system shall brake hard.",
                )
                self._trigger_update(test_server)
                form.do_form_submit()
                self._wait_for_window()

                # "Later": the window closes, the notice stays.
                self.click(LATER)
                self.assert_element_not_visible(DIALOG)
                _wait_for(
                    lambda: (
                        self.get_attribute(INDICATOR, "data-state")
                        == "merge_waiting"
                        and self.is_element_visible(INDICATOR_ACTION)
                    ),
                    WAIT_SECONDS,
                    "The notice that reopens the window is not there.",
                )
                text = self.get_text(INDICATOR)
                assert BANNED_WORDS.findall(text) == [], text
                # The window does not come back by itself, and the button
                # of the notice opens it.
                time.sleep(6)
                self.assert_element_not_visible(DIALOG)
                self.click(INDICATOR_ACTION)
                self._wait_for_window()

                # Abandoned: the project is as it was, nothing is lost.
                self.click(ABORT)
                _wait_for(
                    lambda: (
                        self.get_attribute(INDICATOR, "data-state")
                        != "merge_waiting"
                    ),
                    WAIT_SECONDS,
                    "The merge still waits.",
                )
                assert TYPED_TEXT.strip() in _read_document(workspace)
                assert "brake hard" in _read_server(bare_path)

    def test_004_the_update_on_request_says_what_it_did_and_then_reloads(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root:
            remote_url, bare_path = _create_remote(root)
            workspace = os.path.join(root, "workspace")
            os.makedirs(workspace)
            with self._open_project(remote_url, workspace):
                Screen_ProjectIndex(self).do_click_on_first_document()
                _push_change_of_colleague(
                    remote_url,
                    root,
                    "The system shall steer.",
                    "The system shall steer left.",
                )

                # The menu of the project: the update, then its answer.
                menu = TreeContextMenu(self)
                menu.do_click_action("tree-update-action")
                _wait_for(
                    lambda: (
                        "The project was updated."
                        in self.get_text('[data-testid="update-message"]')
                    ),
                    WAIT_SECONDS,
                    "The window does not say that the project was updated.",
                )
                assert "steer left" in _read_document(workspace)
                # The page does not reload under the window.
                time.sleep(2)
                self.assert_element('[data-testid="update-dialog"]')

                # It follows the update when the window is closed.
                self.click(LATER)
                self.assert_text("The system shall steer left.")
                again = TreeContextMenu(self)
                again.do_click_action("tree-update-action")
                _wait_for(
                    lambda: (
                        "The project is up to date."
                        in self.get_text('[data-testid="update-message"]')
                    ),
                    WAIT_SECONDS,
                    "The window does not say that the project is up to date.",
                )

    # ---- What the tests do with the application

    def _wait_for_window(self) -> None:
        _wait_for(
            lambda: self.is_element_visible(DIALOG),
            WAIT_SECONDS,
            "The window of the merge did not open.",
        )

    def _open_project(
        self, remote_url: str, workspace: str
    ) -> "_RunningApplication":
        return _RunningApplication(self, remote_url, workspace)

    def _open_editor_and_type(self, node_number: int) -> Any:
        screen_document = Screen_ProjectIndex(self).do_click_on_first_document()
        screen_document.assert_on_screen_document()
        requirement = screen_document.get_node(node_number)
        form = requirement.do_open_form_edit_requirement()
        form.assert_on_form()
        self.wait_for_element(EDITOR)
        # In the middle of the window: a fixed element may cover the border.
        self.execute_script(
            "document.querySelector(arguments[0]).scrollIntoView("
            "{block: 'center'});",
            EDITOR,
        )
        editor = self.find_element(EDITOR)
        self.execute_script(
            "document.querySelector(arguments[0]).focus();", EDITOR
        )
        editor.send_keys(Keys.CONTROL, Keys.END)
        editor.send_keys(TYPED_TEXT)
        assert TYPED_TEXT.strip() in self.get_text(EDITOR)
        return form

    def _trigger_update(self, test_server: DesktopTestServer) -> None:
        """Open the project again, as the user would: it asks for an update."""
        identifier = next(
            iter(
                load_settings(
                    Path(test_server.get_settings_path())
                ).project_folders
            )
        )
        prefix = f"strictdoc_desktop_session_{test_server.server_port}"
        cookies = "; ".join(
            f"{cookie_['name']}={cookie_['value']}"
            for cookie_ in self.driver.get_cookies()
            if cookie_["name"] == prefix
        )
        assert cookies != "", "The window has no session cookie."
        request = urllib.request.Request(
            f"http://127.0.0.1:{test_server.server_port}/projects/open",
            data=urllib.parse.urlencode({"identifier": identifier}).encode(),
            headers={"Cookie": cookies},
            method="POST",
        )
        opener = urllib.request.build_opener(_NoRedirect())
        try:
            opener.open(request, timeout=30)
        except urllib.error.HTTPError as error:
            assert error.code == 303, error


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_: Any, **__: Any) -> None:
        return None


class _RunningApplication:
    """The application of the user, signed in, with the project cloned."""

    def __init__(
        self,
        case: DesktopCase,
        remote_url: str,
        workspace: str,
        lease_seconds: Optional[float] = None,
    ) -> None:
        self._case = case
        self._remote_url = remote_url
        self._workspace = workspace
        self._lease_seconds = lease_seconds
        self._stack: Any = None

    def __enter__(self) -> DesktopTestServer:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)
        self._stack = ExitStack()
        fake_gitlab, _ = self._stack.enter_context(
            _create_environment(self._remote_url)
        )
        user_path = self._stack.enter_context(tempfile.TemporaryDirectory())
        test_server = self._stack.enter_context(
            DesktopTestServer(
                input_path=test_setup.path_to_sandbox,
                gitlab_url=fake_gitlab.url,
                oauth_client_id=CLIENT_ID,
                gitlab_projects_root=GROUP_PATH,
                user_path=user_path,
                lease_seconds=self._lease_seconds,
            )
        )
        case = self._case
        case.open(test_server.get_start_url())
        case.click(SIGN_IN)
        case.assert_text(DISPLAY_NAME)
        case.click(OPEN_BUTTON)
        case.type(FOLDER_INPUT, self._workspace)
        case.click(FOLDER_SUBMIT)
        case.assert_text(DOCUMENT_TITLE)
        return test_server

    def __exit__(self, *arguments: Any) -> None:
        self._stack.close()
