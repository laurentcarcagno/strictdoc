"""
The command bar of the assistant above the Markdown editor: "/" lists the
commands, /rewrite shows the difference and applies it to the editor (the form
is saved by the user), /comment adds the ticked remark as a comment. The model
is a fake provider of the project configuration.
"""

from selenium.webdriver.common.keys import Keys

from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.document.form_edit_requirement import (
    Form_EditRequirement,
)
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)
from tests.end2end.server import SDocTestServer

EDITOR = "sdoc-markdown-editor[data-ready=true] .ProseMirror"
BAR = 'sdoc-ai-bar [data-testid="ai-bar-input"]'
MENU_ITEM = '[data-testid="ai-bar-menu"] .ai-bar__menu-item'
PANEL = '[data-testid="ai-bar-panel"]'


class Test(E2ECase):
    def test(self):
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with SDocTestServer(
            input_path=test_setup.path_to_sandbox
        ) as test_server:
            self.open(test_server.get_host_and_port())

            screen_project_index = Screen_ProjectIndex(self)
            screen_project_index.assert_on_screen()
            screen_document = screen_project_index.do_click_on_first_document()
            screen_document.assert_on_screen_document()

            # /rewrite: choose the command in the list, run it, apply it.
            form: Form_EditRequirement = (
                screen_document.get_node().do_open_form_edit_requirement()
            )
            form.assert_on_form()
            self.wait_for_element(EDITOR)
            bar = self.wait_for_element(BAR)
            bar.click()
            bar.send_keys("/rew")
            self.wait_for_element(MENU_ITEM)
            self.assert_text("/rewrite", '[data-testid="ai-bar-menu"]')
            bar.send_keys(Keys.ENTER)
            assert bar.get_attribute("value") == "/rewrite "
            bar.send_keys("concise")
            bar.send_keys(Keys.ENTER)
            self.wait_for_element(f"{PANEL} .ai-bar__diff ins")
            self.assert_text("within 2 s", f"{PANEL} .ai-bar__diff ins")
            self.click('[data-testid="ai-bar-apply"]')
            self.wait_for_text("within 2 s", EDITOR)
            self.assert_text("Ctrl+Z", '[data-testid="ai-bar-done"]')
            form.do_form_submit()
            screen_document.assert_text("The system shall start within 2 s.")

            # /comment: the ticked remark becomes a comment of the user.
            form = screen_document.get_node().do_open_form_edit_requirement()
            form.assert_on_form()
            self.wait_for_element(EDITOR)
            bar = self.wait_for_element(BAR)
            bar.click()
            bar.send_keys("/comment")
            self.wait_for_element(MENU_ITEM)
            bar.send_keys(Keys.ENTER)
            bar.send_keys(Keys.ENTER)
            self.wait_for_element(
                f'{PANEL} [data-testid="ai-bar-action"] input:checked'
            )
            self.assert_text(
                "Which start", f'{PANEL} [data-testid="ai-bar-action"]'
            )
            self.click('[data-testid="ai-bar-apply"]')
            self.wait_for_element('[data-testid="ai-bar-done"]')
            # The page reloads and shows the comment in the margin.
            self.wait_for_text("Which start: power on or after a reset?")
