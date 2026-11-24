"""
What the user types is never lost to an update of the project, and the change
of another person is never lost to what the user saves.

The project is shared with a colleague: another clone of the same server,
which commits and sends a change while the user has an editor open. The editor
is the WYSIWYG Markdown editor of a node.

@relation(SDOC-SRS-1246, scope=file)
"""

import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional, Tuple

import pytest
from git import Actor, Repo
from selenium.webdriver.common.keys import Keys

from strictdoc.features.desktop.settings import load_settings
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
from tests.end2end.helpers.components.viewtype_selector import (
    ViewType_Selector,
)
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)

DOCUMENT_TITLE = "Document to edit"
SEED_AUTHOR = Actor("Seed", "seed@example.org")
COLLEAGUE = Actor("Colleague", "colleague@example.org")
TYPED_TEXT = " Typed here."

SIGN_IN = '[data-testid="sign-in"]'
OPEN_BUTTON = '[data-testid="catalog-project-open"]'
FOLDER_INPUT = '[data-testid="folder-input"]'
FOLDER_SUBMIT = '[data-testid="folder-submit"]'
EDITOR = "sdoc-markdown-editor[data-ready=true] .ProseMirror"
INDICATOR = '[data-testid="desktop-indicator"]'
NOTICE = '[data-testid="desktop-editing-notice"]'
WAIT_SECONDS = 40.0
COMMENT_EDIT = '[data-testid="comment-edit"]'
BROKEN_DOCUMENT = (
    "[DOCUMENT]\nTITLE: Broken\n\n[REQUIREMENT]\nUID: REQ-9\nNOT SDOC\n"
)

MARKDOWN_DOCUMENT = (
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
    "<<<\n"
)

LIST_DOCUMENT = (
    "[DOCUMENT]\n"
    "MID: 1d6c2b5f8a9e4e1fb7c3a0d4e5f60a11\n"
    f"TITLE: {DOCUMENT_TITLE}\n"
    "OPTIONS:\n"
    "  ENABLE_MID: True\n"
    "\n"
    "[GRAMMAR]\n"
    "ELEMENTS:\n"
    "- TAG: REQUIREMENT\n"
    "  FIELDS:\n"
    "  - TITLE: MID\n"
    "    TYPE: String\n"
    "    REQUIRED: False\n"
    "  - TITLE: UID\n"
    "    TYPE: String\n"
    "    REQUIRED: False\n"
    "  - TITLE: STATUS\n"
    "    TYPE: SingleChoice(Draft, Active, Obsolete)\n"
    "    REQUIRED: False\n"
    "  - TITLE: STATEMENT\n"
    "    TYPE: String\n"
    "    REQUIRED: False\n"
    "\n"
    "[REQUIREMENT]\n"
    "MID: 2e7d3c6a9b0f4f2ac8d4b1e5f6a70b22\n"
    "UID: REQ-1\n"
    "STATEMENT: The system shall brake.\n"
    "\n"
    "[REQUIREMENT]\n"
    "MID: 3f8e4d7bac104a3bd9e5c2f6a7b81c33\n"
    "UID: REQ-2\n"
    "STATEMENT: The system shall steer.\n"
)

COMMENT_DOCUMENT = (
    "[DOCUMENT]\n"
    "MID: 1d6c2b5f8a9e4e1fb7c3a0d4e5f60a11\n"
    f"TITLE: {DOCUMENT_TITLE}\n"
    "OPTIONS:\n"
    "  ENABLE_MID: True\n"
    "\n"
    "[REQUIREMENT]\n"
    "MID: 2e7d3c6a9b0f4f2ac8d4b1e5f6a70b22\n"
    "UID: REQ-1\n"
    "STATEMENT: The system shall brake.\n"
    "COMMENT: A comment that is already there.\n"
    "\n"
    "[REQUIREMENT]\n"
    "MID: 3f8e4d7bac104a3bd9e5c2f6a7b81c33\n"
    "UID: REQ-2\n"
    "STATEMENT: The system shall steer.\n"
)


def _create_remote(
    root: str,
    document: Optional[str] = None,
    extra_files: Optional[Dict[str, str]] = None,
) -> Tuple[str, str]:
    """
    A bare repository of a document with two requirements: a Markdown one, or
    the text that is given, with other files.
    """
    work_path = os.path.join(root, "remote_work")
    os.makedirs(work_path)
    for name_, text_ in (extra_files or {}).items():
        Path(work_path, name_).write_text(text_, encoding="utf-8")
    Path(work_path, "doc.sdoc").write_text(
        document if document is not None else MARKDOWN_DOCUMENT,
        encoding="utf-8",
    )
    work_repo = Repo.init(work_path, initial_branch="main")
    work_repo.index.add(["doc.sdoc", *(extra_files or {})])
    work_repo.index.commit("Seed", author=SEED_AUTHOR, committer=SEED_AUTHOR)
    work_repo.close()
    bare_path = os.path.join(root, "remote.git")
    Repo.clone_from(work_path, bare_path, bare=True).close()
    return f"file://{bare_path}", bare_path


def _push_change_of_colleague(
    remote_url: str,
    root: str,
    old_text: str,
    new_text: str,
    extra_files: Optional[Dict[str, str]] = None,
) -> str:
    """
    The colleague changes a sentence, commits and sends it, with other files
    if it adds some. Its commit.
    """
    path = os.path.join(root, f"colleague_{time.monotonic_ns()}")
    repo = Repo.clone_from(remote_url, path)
    document = Path(path, "doc.sdoc")
    text = document.read_text(encoding="utf-8")
    assert old_text in text
    document.write_text(text.replace(old_text, new_text), encoding="utf-8")
    for name_, extra_text_ in (extra_files or {}).items():
        Path(path, name_).write_text(extra_text_, encoding="utf-8")
    repo.index.add(["doc.sdoc", *(extra_files or {})])
    commit = repo.index.commit("Change", author=COLLEAGUE, committer=COLLEAGUE)
    repo.git.push("origin", "main")
    repo.close()
    return str(commit.hexsha)


def _count_commits(path: str) -> int:
    repo = Repo(path)
    try:
        return len(list(repo.iter_commits("main")))
    finally:
        repo.close()


def _read_document(folder: str) -> str:
    return Path(folder, "doc.sdoc").read_text(encoding="utf-8")


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
    def test_001_the_update_of_another_node_waits_for_the_end_of_the_typing(
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
                    "The system shall steer.",
                    "The system shall steer left.",
                )
                self._trigger_update(test_server)

                # The update waits: the editor is still there, with the text.
                seen = self._wait_for_update(workspace, "steer left")
                assert seen == "waiting", self._describe_loss()
                assert TYPED_TEXT.strip() in self.get_text(EDITOR)
                assert "steer left" not in _read_document(workspace)

                # The typing ends: the update applies, and the page follows.
                form.do_form_cancel()
                _wait_for(
                    lambda: "steer left" in _read_document(workspace),
                    WAIT_SECONDS,
                    "The update was not applied.",
                )
                self.assert_text("The system shall steer left.")
                assert TYPED_TEXT.strip() not in self.get_page_source()

    def test_002_the_same_node_keeps_the_typing_here_and_the_change_there(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root:
            remote_url, bare_path = _create_remote(root)
            workspace = os.path.join(root, "workspace")
            os.makedirs(workspace)
            with self._open_project(remote_url, workspace) as test_server:
                form = self._open_editor_and_type(1)
                colleague_commit = _push_change_of_colleague(
                    remote_url,
                    root,
                    "The system shall brake.",
                    "The system shall brake hard.",
                )
                self._trigger_update(test_server)
                seen = self._wait_for_update(workspace, "brake hard")
                assert seen == "waiting", self._describe_loss()
                assert TYPED_TEXT.strip() in self.get_text(EDITOR)

                form.do_form_submit()

                # The typing is committed here, the commit of the colleague is
                # intact on the server, and the user is told that a choice
                # waits: both changed the same node (see 10_sync).
                _wait_for(
                    lambda: _count_commits(workspace) == 2,
                    WAIT_SECONDS,
                    "The typing was not committed.",
                )
                assert TYPED_TEXT.strip() in _read_document(workspace)
                _wait_for(
                    lambda: (
                        self.is_element_visible(INDICATOR)
                        and self.get_attribute(INDICATOR, "data-state")
                        == "merge_waiting"
                    ),
                    WAIT_SECONDS,
                    "The indicator does not say that a choice waits.",
                )
                repo = Repo(bare_path)
                assert str(repo.commit("main").hexsha) == colleague_commit
                assert "brake hard" in repo.git.show("main:doc.sdoc")
                repo.close()

    def test_003_a_form_on_an_old_version_does_not_replace_the_new_one(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root:
            remote_url, bare_path = _create_remote(root)
            workspace = os.path.join(root, "workspace")
            os.makedirs(workspace)
            with self._open_project(
                remote_url, workspace, lease_seconds=3
            ) as test_server:
                self._open_editor_and_type(1)
                # The window sleeps: no signal of the editor, and the page
                # does not hear the server any more.
                self._put_window_to_sleep()
                _push_change_of_colleague(
                    remote_url,
                    root,
                    "The system shall brake.",
                    "The system shall brake hard.",
                )
                self._trigger_update(test_server)
                _wait_for(
                    lambda: "brake hard" in _read_document(workspace),
                    WAIT_SECONDS,
                    "The update was not applied.",
                )
                commits_before = _count_commits(workspace)

                # The form is not closed by a save that is refused: only the
                # button is pressed.
                self.click_xpath('//*[@data-testid="form-submit-action"]')

                # The save is refused: the text stays on the screen, copyable,
                # and what the colleague wrote is still the file.
                def look() -> str:
                    if self.is_element_visible(NOTICE):
                        return "refused"
                    if _count_commits(workspace) > commits_before:
                        return "saved"
                    return ""

                outcome = _wait_for(look, WAIT_SECONDS, "Nothing happened.")
                assert outcome == "refused", (
                    "The old text was saved over the change of the colleague "
                    f"(the change is still in the file: "
                    f"{'brake hard' in _read_document(workspace)})."
                )
                assert TYPED_TEXT.strip() in self.get_text(EDITOR)
                assert "brake hard" in _read_document(workspace)
                assert _count_commits(workspace) == commits_before

    def test_004_the_other_editors_take_a_lease_and_give_it_back(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            remote_url, bare_path = _create_remote(root)
            workspace = os.path.join(root, "workspace")
            os.makedirs(workspace)
            with self._open_project(remote_url, workspace):
                screen_document = Screen_ProjectIndex(
                    self
                ).do_click_on_first_document()
                screen_document.assert_on_screen_document()
                # A page with no editor does not hold the update.
                assert self._wait_for_editing(False)

                form_config = (
                    screen_document.get_root_node().do_open_form_edit_config()
                )
                assert self._wait_for_editing(True), "The configuration."
                form_config.do_form_cancel()
                assert self._wait_for_editing(False)

                form_grammar = screen_document.do_open_modal_form_edit_grammar()
                assert self._wait_for_editing(True), "The grammar."
                form_grammar.do_form_cancel()
                assert self._wait_for_editing(False)

    def test_005_the_inline_edit_of_the_table_takes_a_lease(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            remote_url, bare_path = _create_remote(root)
            workspace = os.path.join(root, "workspace")
            os.makedirs(workspace)
            with self._open_project(remote_url, workspace):
                Screen_ProjectIndex(self).do_click_on_first_document()
                screen_table = ViewType_Selector(self).do_go_to_table()
                screen_table.assert_on_screen_table()
                node_mid = screen_table.get_node_mid_from_row(row_order=1)
                assert node_mid is not None

                # The edit mode of the table is not an editor: a cell is.
                screen_table.do_toggle_edit_mode()
                screen_table.assert_edit_mode_on()
                assert self._wait_for_editing(False)
                screen_table.do_open_inline_cell(node_mid, "STATEMENT")
                assert self._wait_for_editing(True), "The cell."
                screen_table.do_save_inline_cell_by_outside_click()
                screen_table.wait_for_cell_not_editing(node_mid, "STATEMENT")
                assert self._wait_for_editing(False)

    def test_006_a_comment_that_exists_is_not_an_open_editor(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            remote_url, bare_path = _create_remote(
                root,
                COMMENT_DOCUMENT,
                {"strictdoc.toml": '[project]\nfeatures = ["COMMENTS"]\n'},
            )
            workspace = os.path.join(root, "workspace")
            os.makedirs(workspace)
            with self._open_project(remote_url, workspace) as test_server:
                screen_document = Screen_ProjectIndex(
                    self
                ).do_click_on_first_document()
                screen_document.assert_on_screen_document()
                self.wait_for_element(COMMENT_EDIT)

                # The edit form of the comment is in the page, closed: the
                # page holds no lease, so the update applies and the page
                # follows it.
                assert self._wait_for_editing(False)
                _push_change_of_colleague(
                    remote_url,
                    root,
                    "The system shall steer.",
                    "The system shall steer left.",
                )
                self._trigger_update(test_server)
                seen = self._wait_for_update(workspace, "steer left")
                assert seen == "applied"
                self.assert_text("The system shall steer left.")

                # The page that follows the update has the comment too, and
                # still no lease: a save from it is not refused.
                self.wait_for_element(COMMENT_EDIT)
                assert self._wait_for_editing(False)

                # Opened, the form is an editor.
                self.click(COMMENT_EDIT)
                assert self._wait_for_editing(True), "The comment is open."
                self.click(COMMENT_EDIT)
                assert self._wait_for_editing(False)

    def test_007_a_cell_with_a_list_that_loses_the_focus_is_not_saved_late(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root:
            remote_url, bare_path = _create_remote(root, LIST_DOCUMENT)
            workspace = os.path.join(root, "workspace")
            os.makedirs(workspace)
            with self._open_project(
                remote_url, workspace, lease_seconds=3
            ) as test_server:
                Screen_ProjectIndex(self).do_click_on_first_document()
                screen_table = ViewType_Selector(self).do_go_to_table()
                screen_table.assert_on_screen_table()
                node_mid = screen_table.get_node_mid_from_row(row_order=1)
                screen_table.do_toggle_edit_mode()
                screen_table.assert_edit_mode_on()
                screen_table.do_cell_autocomplete(node_mid, "STATUS", "act")
                # The window sleeps: no signal, and no reload.
                self._put_window_to_sleep()
                assert self._wait_for_editing(False), "The lease did not end."
                _push_change_of_colleague(
                    remote_url,
                    root,
                    "The system shall steer.",
                    "The system shall steer left.",
                )
                self._trigger_update(test_server)
                _wait_for(
                    lambda: "steer left" in _read_document(workspace),
                    WAIT_SECONDS,
                    "The update was not applied.",
                )
                commits_before = _count_commits(workspace)

                # The cell loses the focus: it saves, with no editor in the
                # page any more. The save is refused.
                screen_table.do_submit_cell_autocomplete()

                def look() -> str:
                    if self.is_element_visible(NOTICE):
                        return "refused"
                    if _count_commits(workspace) > commits_before:
                        return "saved"
                    return ""

                outcome = _wait_for(look, WAIT_SECONDS, "Nothing happened.")
                assert outcome == "refused", (
                    "The cell was saved over the change of the colleague."
                )
                assert "steer left" in _read_document(workspace)
                assert "STATUS: Active" not in _read_document(workspace)
                assert _count_commits(workspace) == commits_before

    def test_008_files_that_do_not_build_refuse_the_saves_and_say_why(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root:
            remote_url, bare_path = _create_remote(root)
            workspace = os.path.join(root, "workspace")
            os.makedirs(workspace)
            with self._open_project(remote_url, workspace) as test_server:
                screen_document = Screen_ProjectIndex(
                    self
                ).do_click_on_first_document()
                screen_document.assert_on_screen_document()
                _push_change_of_colleague(
                    remote_url,
                    root,
                    "The system shall steer.",
                    "The system shall steer left.",
                    {"broken.sdoc": BROKEN_DOCUMENT},
                )
                self._trigger_update(test_server)
                _wait_for(
                    lambda: "steer left" in _read_document(workspace),
                    WAIT_SECONDS,
                    "The update was not applied.",
                )
                # The index is the old one: the indicator says that nothing
                # is saved, and the page is not reloaded on a project that
                # does not build.
                _wait_for(
                    lambda: (
                        self.is_element_visible(INDICATOR)
                        and self.get_attribute(INDICATOR, "data-state")
                        == "unreadable"
                    ),
                    WAIT_SECONDS,
                    "The indicator does not say that saving is paused.",
                )
                commits_before = _count_commits(workspace)

                requirement = screen_document.get_node(1)
                form = requirement.do_open_form_edit_requirement()
                form.assert_on_form()
                self.wait_for_element(EDITOR)
                self.execute_script(
                    "document.querySelector(arguments[0]).focus();", EDITOR
                )
                self.find_element(EDITOR).send_keys(TYPED_TEXT)
                # The form is not closed by a save that is refused: only the
                # button is pressed.
                self.click_xpath('//*[@data-testid="form-submit-action"]')

                _wait_for(
                    lambda: self.is_element_visible(NOTICE),
                    WAIT_SECONDS,
                    "The refusal was not shown.",
                )
                assert TYPED_TEXT.strip() in self.get_text(EDITOR)
                assert "steer left" in _read_document(workspace)
                assert _count_commits(workspace) == commits_before

    # ---- What the tests do with the application

    def _put_window_to_sleep(self) -> None:
        """No signal of the editors, and the page does not hear the server."""
        self.execute_script(
            "if (window.sdocDesktop) {"
            "  window.sdocDesktop.pauseSignals(true);"
            "}"
            "if (typeof ws !== 'undefined') {"
            "  ws.onclose = null; ws.close();"
            "}"
        )

    def _open_project(
        self,
        remote_url: str,
        workspace: str,
        lease_seconds: Optional[float] = None,
    ) -> "_RunningApplication":
        return _RunningApplication(self, remote_url, workspace, lease_seconds)

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
        # Focused by the script, not by a click that a moving element of the
        # page may take.
        self.execute_script(
            "document.querySelector(arguments[0]).focus();", EDITOR
        )
        editor.send_keys(Keys.CONTROL, Keys.END)
        editor.send_keys(TYPED_TEXT)
        assert TYPED_TEXT.strip() in self.get_text(EDITOR)
        return form

    def _trigger_update(self, test_server: DesktopTestServer) -> None:
        """Open the project again, as the user would: it asks for an update."""
        assert test_server.user_path is not None
        identifier = next(
            iter(load_settings(_get_settings_path(test_server)).project_folders)
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

    def _describe_loss(self) -> str:
        """What the user lost, for the message of a test that fails."""
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if not self.is_element_present(EDITOR):
                return (
                    "The update changed the files and the page reloaded: "
                    "the editor is gone with the text that was typed."
                )
            time.sleep(0.25)
        return "The update changed the files while the editor was open."

    def _wait_for_editing(self, expected: bool) -> bool:
        """The application sees (or does not see) an editor in the page."""
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            status = self._get_status()
            if status is not None and status.get("editing") is expected:
                return True
            time.sleep(0.25)
        return False

    def _get_status(self) -> Optional[Dict[str, Any]]:
        try:
            status: Optional[Dict[str, Any]] = self.driver.execute_async_script(
                "const done = arguments[arguments.length - 1];"
                "fetch('/__desktop/status', {cache: 'no-store'})"
                "  .then(r => r.json()).then(done).catch(() => done(null));"
            )
            return status
        except Exception:  # noqa: BLE001
            return None

    def _wait_for_update(self, workspace: str, text: str) -> str:
        """
        "applied" when the update changed the files, "waiting" when the
        application says that an update waits for the end of the typing.
        """

        def look() -> str:
            if text in _read_document(workspace):
                return "applied"
            status = self._get_status()
            if status is not None and status.get("update_waiting") is True:
                return "waiting"
            return ""

        found: str = _wait_for(look, WAIT_SECONDS, "The update was not seen.")
        return found


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_: Any, **__: Any) -> None:
        return None


def _get_settings_path(test_server: DesktopTestServer) -> Path:
    return Path(test_server.get_settings_path())


class _RunningApplication:
    """The application of the user, signed in, with the project cloned."""

    def __init__(
        self,
        case: DesktopCase,
        remote_url: str,
        workspace: str,
        lease_seconds: Optional[float],
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
