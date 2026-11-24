"""
The application says nothing of Git. The screens of the user are walked in
English and in French: the home, the project, a document, the table, the page
of an item, its history, the versions, the menus of the tree, the window of the
merge, the update and the publication of a version. None shows a word of the
tool, and none links to the pages of Git.

@relation(SDOC-SRS-1248, scope=file)
@relation(SDOC-SRS-1249, scope=file)
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
from typing import Any, Callable, Iterator, List, Tuple

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
from tests.end2end.helpers.components.tree_context_menu import TreeContextMenu
from tests.end2end.helpers.components.viewtype_selector import (
    ViewType_Selector,
)
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)

DOCUMENT_TITLE = "Shared document"
DOCUMENT_MID = "1d6c2b5f8a9e4e1fb7c3a0d4e5f60a11"
SEED_AUTHOR = Actor("Seed", "seed@example.org")
COLLEAGUE = Actor("Colleague", "colleague@example.org")
TYPED_TEXT = " Typed here."

SIGN_IN = '[data-testid="sign-in"]'
OPEN_BUTTON = '[data-testid="catalog-project-open"]'
FOLDER_INPUT = '[data-testid="folder-input"]'
FOLDER_SUBMIT = '[data-testid="folder-submit"]'
EDITOR = "sdoc-markdown-editor[data-ready=true] .ProseMirror"
MENU = "[data-testid='tree-context-menu']"
DIALOG = '[data-testid="sync-conflict-dialog"]'
KEEP_LOCAL = '[data-testid="sync-keep-local"]'
CANCEL = '[data-testid="form-cancel-action"]'
SUBMIT = '[data-testid="form-submit-action"]'
WAIT_SECONDS = 40.0

# The words that the user never reads (the tool, and its names for things).
BANNED_WORDS = re.compile(
    r"\b(git|gitlab|commit|commits|committed|push|pushed|pull|pulled|merge|"
    r"merged|branch|origin|repository|rebase|tag|tags|sha)\b",
    re.IGNORECASE,
)

# The short identifier of a commit (the identifiers of the nodes have 32).
HASH = re.compile(r"\b[0-9a-f]{7,12}\b")

TEXTS = {
    "en": {
        "up_to_date": "The project is up to date.",
        "published": "Version A1 is published.",
        "update": "Update the project",
        "publish": "Publish a version",
    },
    "fr": {
        "up_to_date": "Le projet est à jour.",
        "published": "La version A1 est publiée.",
        "update": "Mettre à jour le projet",
        "publish": "Publier une version",
    },
}


def _create_remote(root: str) -> Tuple[str, str]:
    """A bare repository of a Markdown document with two requirements."""
    work_path = os.path.join(root, "remote_work")
    os.makedirs(work_path)
    Path(work_path, "doc.sdoc").write_text(
        "[DOCUMENT]\n"
        f"MID: {DOCUMENT_MID}\n"
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


def _get_server_tags(bare_path: str) -> List[str]:
    repo = Repo(bare_path)
    try:
        return sorted(tag_.name for tag_ in repo.tags)
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
    def test_001_the_screens_say_nothing_of_git_in_english(self) -> None:
        self._walk("en")

    def test_002_the_screens_say_nothing_of_git_in_french(self) -> None:
        self._walk("fr")

    # ---- The walk

    def _walk(self, language: str) -> None:
        texts = TEXTS[language]
        with tempfile.TemporaryDirectory() as root:
            remote_url, bare_path = _create_remote(root)
            workspace = os.path.join(root, "workspace")
            os.makedirs(workspace)
            with ExitStack() as stack:
                fake_gitlab, _ = stack.enter_context(
                    _create_environment(remote_url)
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
                        language=language,
                    )
                )
                self._walk_home(test_server)
                self._open_project(workspace)
                self._walk_project(texts, bare_path)
                self._walk_merge(remote_url, root, test_server)

    def _walk_home(self, test_server: DesktopTestServer) -> None:
        self.open(test_server.get_start_url())
        self.click(SIGN_IN)
        self._check("home before the sign-in")
        self.assert_text(DISPLAY_NAME)
        self._check("home")

    def _open_project(self, workspace: str) -> None:
        self.click(OPEN_BUTTON)
        self.type(FOLDER_INPUT, workspace)
        self.click(FOLDER_SUBMIT)
        self.assert_text(DOCUMENT_TITLE)
        self._check("project")

    def _walk_project(self, texts: Any, bare_path: str) -> None:
        menu = TreeContextMenu(self)
        screen_document = Screen_ProjectIndex(self).do_click_on_first_document()
        screen_document.assert_on_screen_document()
        self._check("document")
        origin = self._get_origin()

        # The menus of the tree: the project, and a document.
        menu.do_open()
        self._check_menu("menu of the project")
        names = self._get_menu_names()
        for name_ in ("tree-update-action", "tree-publish-action"):
            assert name_ in names, (name_, names)
        for name_ in (
            "tree-git-action",
            "tree-sync-action",
            "tree-version-document-action",
        ):
            assert name_ not in names, (name_, names)
        document_node = "//*[@data-testid='tree-file-link']"
        menu.do_open(document_node)
        self._check_menu("menu of a document")
        assert "tree-version-document-action" not in self._get_menu_names()
        self.send_keys("body", Keys.ESCAPE)

        # The table, the page of an item and its history.
        ViewType_Selector(self).do_go_to_table().assert_on_screen_table()
        self._check("table")
        for tab_ in ("content", "links", "comments", "history"):
            self.open(f"{origin}/item/REQ-1?tab={tab_}")
            self.wait_for_element("body")
            if tab_ == "history":
                # There is a history to read: the seed of the project.
                self.assert_element('[data-testid="item-revision"]')
            self._check(f"item, {tab_}")

        # The versions of the document, before there is one.
        self.open(f"{origin}/versions/{DOCUMENT_MID}")
        self.wait_for_element('[data-testid="versions-title"]')
        self._check("versions, none yet")

        # The update.
        self.open(f"{origin}/")
        menu.do_click_action("tree-update-action")
        self._wait_for_text(
            '[data-testid="update-message"]', texts["up_to_date"]
        )
        self._check("update")
        self.click(CANCEL)

        # The publication of a version, then the versions of the document.
        menu.do_click_action("tree-publish-action")
        self.wait_for_element('[data-testid="publish-dialog"]')
        self._check("publication")
        self.click(SUBMIT)
        self._wait_for_text('[data-testid="publish-done"]', texts["published"])
        self._check("published")
        assert _get_server_tags(bare_path) == ["A1"]
        self.click(CANCEL)
        self.open(f"{origin}/versions/{DOCUMENT_MID}")
        self.assert_text("A1")
        self._check("versions")

    def _walk_merge(
        self,
        remote_url: str,
        root: str,
        test_server: DesktopTestServer,
    ) -> None:
        origin = self._get_origin()
        self.open(f"{origin}/")
        screen_document = Screen_ProjectIndex(self).do_click_on_first_document()
        screen_document.assert_on_screen_document()
        form = screen_document.get_node(1).do_open_form_edit_requirement()
        form.assert_on_form()
        self.wait_for_element(EDITOR)
        self.execute_script(
            "document.querySelector(arguments[0]).focus();", EDITOR
        )
        self.find_element(EDITOR).send_keys(Keys.CONTROL, Keys.END)
        self.find_element(EDITOR).send_keys(TYPED_TEXT)
        _push_change_of_colleague(
            remote_url,
            root,
            "The system shall brake.",
            "The system shall brake hard.",
        )
        self._trigger_update(test_server)
        form.do_form_submit()
        _wait_for(
            lambda: self.is_element_visible(DIALOG),
            WAIT_SECONDS,
            "The window of the merge did not open.",
        )
        self._check("window of the merge")
        self.click(KEEP_LOCAL)
        self._check("window of the merge, a choice")

    # ---- What the walk looks at

    def _check(self, where: str) -> None:
        """No word of the tool in the text of the page, no link to Git."""
        text = self.get_text("body")
        words = BANNED_WORDS.findall(_without_field_names(text))
        assert words == [], f"{where}: {words} in:\n{text}"
        hashes = HASH.findall(text)
        assert hashes == [], f"{where}: {hashes} in:\n{text}"
        self._check_links(where)

    def _check_menu(self, where: str) -> None:
        text = self.get_text(MENU)
        words = BANNED_WORDS.findall(text)
        assert words == [], f"{where}: {words} in:\n{text}"

    def _check_links(self, where: str) -> None:
        links: List[str] = self.execute_script(
            "return Array.from(document.querySelectorAll('a[href]'))"
            ".filter(function (link) {"
            "  return /^\\/git(\\/|$|\\?)|\\/actions\\/git\\/overview/"
            "    .test(link.getAttribute('href')) &&"
            "    link.getClientRects().length > 0;"
            "}).map(function (link) { return link.getAttribute('href'); });"
        )
        assert links == [], f"{where}: links to Git {links}"

    def _get_menu_names(self) -> List[str]:
        names: List[str] = self.execute_script(
            "return Array.from(document.querySelectorAll("
            "\"[data-testid='tree-context-menu'] a[data-testid]\"))"
            ".filter(function (item) { return item.offsetParent !== null; })"
            ".map(function (item) { return item.dataset.testid; });"
        )
        return names

    def _get_origin(self) -> str:
        parts = urllib.parse.urlsplit(self.get_current_url())
        return f"{parts.scheme}://{parts.netloc}"

    def _wait_for_text(self, selector: str, expected: str) -> None:
        _wait_for(
            lambda: expected in self.get_text(selector),
            WAIT_SECONDS,
            f"{expected!r} did not appear.",
        )

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


def _without_field_names(text: str) -> str:
    """
    The column "TAGS" of the table is a field of the requirements (their own
    tags), not a tag of the versions: it is not looked at.
    """
    return re.sub(r"\bTAGS\b", " ", text)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_: Any, **__: Any) -> None:
        return None
