"""
The AI servers of the application: declared in the screen of the settings,
they give the open projects their assistant with no restart, and the
guards of the external servers hold.

The internal server is a small server of the protocol of OpenAI on the
loopback address of the computer: no test reaches a real service. The external
server has an address that does not exist: a call to it would fail with another
message than the refusal that the tests wait for, so a refusal is also a proof
that nothing was sent. The rules of the external servers are in a file that
the launcher of the tests gives to the code of the application.

@relation(SDOC-SRS-1253, scope=file)
@relation(SDOC-SRS-1254, scope=file)
@relation(SDOC-SRS-1255, scope=file)
"""

import json
import os
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

import pytest
from git import Actor, Repo

from tests.end2end.desktop.desktop_case import DesktopCase
from tests.end2end.desktop.desktop_test_server import DesktopTestServer
from tests.end2end.desktop.fake_gitlab import (
    CLIENT_ID,
    DISPLAY_NAME,
    GROUP_PATH,
    MAINTAINER,
    FakeGitLab,
)
from tests.end2end.desktop.fake_openai import (
    MODEL,
    SIMULATED_REMARK,
    FakeOpenAI,
)
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.document.screen_document import (
    Screen_Document,
)
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)

DOCUMENT_TITLE = "Classified document"
SEED_AUTHOR = Actor("Seed", "seed@example.org")

SIGN_IN = '[data-testid="sign-in"]'
OPEN_BUTTON = '[data-testid="catalog-project-open"]'
FOLDER_INPUT = '[data-testid="folder-input"]'
FOLDER_SUBMIT = '[data-testid="folder-submit"]'
EDITOR = "sdoc-markdown-editor[data-ready=true] .ProseMirror"
BAR = "form sdoc-ai-bar"
BAR_INPUT = BAR + ' [data-testid="ai-bar-input"]'
PANEL = BAR + ' [data-testid="ai-bar-panel"]'
PROVIDER = BAR + " select.ai-bar__provider"
DOCUMENT_BAR = 'sdoc-ai-bar[data-scope="document"]'
NODE_BUTTON = '[data-testid="node-edit-action-llm"]'
ADD = '[data-testid="ai-add"]'
COMPANY_KEY = "sk-company-0123456789"
POLICY = {
    "version": 1,
    "cloud_blocked_classifications": ["Secret"],
    "cloud_token_budget_per_month": 0,
}


def _create_remote(root: str) -> str:
    """A project of one document that is classified "Secret"."""
    work_path = os.path.join(root, "remote_work")
    os.makedirs(work_path)
    Path(work_path, "strictdoc.toml").write_text(
        '[project]\ntitle = "Classified"\n', encoding="utf-8"
    )
    Path(work_path, "doc.sdoc").write_text(
        "[DOCUMENT]\n"
        "MID: 1d6c2b5f8a9e4e1fb7c3a0d4e5f60a11\n"
        f"TITLE: {DOCUMENT_TITLE}\n"
        "CLASSIFICATION: Secret\n"
        "OPTIONS:\n"
        "  ENABLE_MID: True\n"
        "  MARKUP: Markdown\n"
        "\n"
        "[REQUIREMENT]\n"
        "MID: 2e7d3c6a9b0f4f2ac8d4b1e5f6a70b22\n"
        "UID: REQ-1\n"
        "STATEMENT: >>>\n"
        "The system shall start quickly.\n"
        "<<<\n",
        encoding="utf-8",
    )
    work_repo = Repo.init(work_path, initial_branch="main")
    work_repo.index.add(["doc.sdoc", "strictdoc.toml"])
    work_repo.index.commit("Seed", author=SEED_AUTHOR, committer=SEED_AUTHOR)
    work_repo.close()
    bare_path = os.path.join(root, "remote.git")
    Repo.clone_from(work_path, bare_path, bare=True).close()
    return f"file://{bare_path}"


def _wait_for(condition: Callable[[], Any], seconds: float, why: str) -> Any:
    deadline = time.monotonic() + seconds
    while True:
        found = condition()
        if found:
            return found
        assert time.monotonic() < deadline, why
        time.sleep(0.25)


@pytest.mark.skipif(
    sys.platform == "win32", reason="The user folders follow XDG variables."
)
class Test(DesktopCase):
    def test_001_no_button_without_a_server_then_the_bar_with_no_restart(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root, FakeOpenAI() as openai:
            with ExitStack() as stack:
                home, document_url = self._open_project(
                    stack, root, with_policy=True
                )
                # No server: no AI button in the page.
                self.assert_element_not_present(DOCUMENT_BAR)
                self.assert_element_not_present(NODE_BUTTON)

                # The user declares a server of the company, in the settings,
                # while the project is open.
                self.open(home + "settings")
                self.assert_element('[data-testid="ai-none"]')
                self._add_server(
                    name="Company",
                    url=openai.url,
                    is_internal=True,
                    key=COMPANY_KEY,
                )
                self.assert_text("Company", '[data-testid="ai-server-name"]')
                # The key is kept, and never shown again.
                assert COMPANY_KEY not in self.get_page_source()
                self.click('[data-testid="ai-server"] summary')
                self.assert_element('[data-testid="ai-clear-key"]')
                assert self.get_attribute(
                    '[data-testid="ai-server"] [data-testid="ai-key"]', "value"
                ) in ("", None)

                # The page that the project made before is made again, and the
                # bar is there: nothing was restarted.
                self.open(document_url)
                self.assert_element(DOCUMENT_BAR)
                self.assert_element_present(NODE_BUTTON)
                self._ask_in_the_form("/comment ambiguity")
                _wait_for(
                    lambda: SIMULATED_REMARK in self.get_text(PANEL),
                    40,
                    "The simulated answer did not come.",
                )
                assert openai.get_chat_count() == 1
                # The answer came from the server of the user, with its model.
                chat = next(
                    request_
                    for request_ in openai.requests
                    if request_["method"] == "POST"
                )
                assert chat["body"]["model"] == MODEL
                # The key of the user reached the server, from the keyring.
                assert chat["headers"]["authorization"] == (
                    f"Bearer {COMPANY_KEY}"
                )

                # The server is deleted: the buttons go, with no restart.
                self.open(home + "settings")
                self.click('[data-testid="ai-server"] summary')
                self.click('[data-testid="ai-delete"]')
                self.assert_element('[data-testid="ai-none"]')
                self.open(document_url)
                self.assert_element_not_present(DOCUMENT_BAR)
                self.assert_element_not_present(NODE_BUTTON)

    def test_002_a_classified_document_is_refused_to_an_external_server(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root, FakeOpenAI() as openai:
            with ExitStack() as stack:
                home, document_url = self._open_project(
                    stack, root, with_policy=True
                )
                self.open(home + "settings")
                self._add_server(
                    name="Company", url=openai.url, is_internal=True
                )
                self._add_server(
                    name="Abroad",
                    url="https://external.invalid/v1",
                    is_internal=False,
                    key="sk-not-a-real-key",
                    model="abroad-model",
                )
                # The key is never shown again, and the external server is
                # declared as such.
                assert "sk-not-a-real-key" not in self.get_page_source()
                self.assert_text(
                    "external", "(//*[@data-testid='ai-server'])[2]"
                )

                self.open(document_url)
                self.assert_element(DOCUMENT_BAR)
                self._ask_in_the_form("/comment ambiguity", provider="abroad")
                _wait_for(
                    lambda: "classification" in self.get_text(PANEL),
                    40,
                    "The refusal did not come.",
                )
                # Nothing was sent to a server: the one of the company was not
                # asked, and the external address could not be reached anyway.
                assert openai.get_chat_count() == 0
                assert "cannot be reached" not in self.get_text(PANEL)

    def test_003_without_the_rules_no_external_server_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with ExitStack() as stack:
                home, document_url = self._open_project(
                    stack, root, with_policy=False
                )
                self.open(home + "settings")
                self.assert_element('[data-testid="ai-policy-message"]')
                self.assert_text("not installed")
                self._add_server(
                    name="Abroad",
                    url="https://external.invalid/v1",
                    is_internal=False,
                    key="sk-not-a-real-key",
                    model="abroad-model",
                )
                self.click('[data-testid="ai-server"] summary')
                self.assert_text("rules for external servers are missing")

                # The only server is external and the rules are missing: no
                # button.
                self.open(document_url)
                self.assert_element_not_present(DOCUMENT_BAR)
                self.assert_element_not_present(NODE_BUTTON)

    # ---- What the tests do with the application

    def _open_project(
        self, stack: ExitStack, root: str, *, with_policy: bool
    ) -> Tuple[str, str]:
        """Start the application, open the project and its document."""
        remote_url = _create_remote(root)
        workspace = os.path.join(root, "workspace")
        os.makedirs(workspace)
        policy_path: Optional[str] = None
        if with_policy:
            policy_path = os.path.join(root, "ai_policy.json")
            Path(policy_path).write_text(json.dumps(POLICY), encoding="utf-8")
        fake_gitlab = stack.enter_context(FakeGitLab())
        fake_gitlab.add_project(
            1, "ISIS", remote_url, MAINTAINER, subgroup="satellites"
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
                ai_policy_path=policy_path,
            )
        )
        self.open(test_server.get_start_url())
        self.click(SIGN_IN)
        self.assert_text(DISPLAY_NAME)
        self.click(OPEN_BUTTON)
        self.type(FOLDER_INPUT, workspace)
        self.click(FOLDER_SUBMIT)
        self.assert_text(DOCUMENT_TITLE)
        Screen_ProjectIndex(self).do_click_on_first_document()
        self.assert_text("The system shall start quickly.")
        return (
            f"http://127.0.0.1:{test_server.server_port}/",
            self.get_current_url(),
        )

    def _add_server(
        self,
        *,
        name: str,
        url: str,
        is_internal: bool,
        key: str = "",
        model: str = MODEL,
    ) -> None:
        """Fill the form that adds a server, with the list of its models."""
        self.click(f"{ADD} summary")
        self.type(f'{ADD} [data-testid="ai-name"]', name)
        self.type(f'{ADD} [data-testid="ai-url"]', url)
        if is_internal:
            self.click(f'{ADD} [data-testid="ai-internal"]')
        if key != "":
            self.type(f'{ADD} [data-testid="ai-key"]', key)
        if is_internal:
            # The model is chosen in the list that the server gives.
            self.click(f'{ADD} [data-testid="ai-load-models"]')
            _wait_for(
                lambda: (
                    self.execute_script(
                        "return document.querySelectorAll("
                        "'[data-testid=\"ai-add\"] datalist option').length"
                    )
                    > 0
                ),
                20,
                "The server did not list its models.",
            )
        self.type(f'{ADD} [data-testid="ai-model"]', model)
        self.click(f'{ADD} [data-testid="ai-save"]')
        self.assert_element('[data-testid="ai-server"]')

    def _ask_in_the_form(
        self, command: str, provider: Optional[str] = None
    ) -> None:
        form = Screen_Document(self).get_node(1).do_open_form_edit_requirement()
        form.assert_on_form()
        self.wait_for_element(EDITOR)
        self.wait_for_element(BAR_INPUT)
        if provider is not None:
            self.wait_for_element(PROVIDER)
            self.select_option_by_value(PROVIDER, provider)
        # In the middle of the window, and focused by the script, not by a
        # click: the bar is at the foot of a long form, where the indicator of
        # the application (fixed at the bottom of the window) may cover it.
        self.execute_script(
            "const bar = document.querySelector(arguments[0]);"
            "bar.scrollIntoView({block: 'center'}); bar.focus();",
            BAR_INPUT,
        )
        bar = self.find_element(BAR_INPUT)
        bar.send_keys(command)
        bar.send_keys("\n")
