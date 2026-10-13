"""
The command bar of the assistant above the Markdown editor: "/" lists the
commands, "@" the requirements, "/rewrite" shows a proposal as a difference and
only "Apply selected" changes the text of the editor; saving the form saves it.
The provider is a fake one that answers from the project configuration.
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
# The bar of the form (the document has its own bar above).
BAR = "form sdoc-ai-bar"
BAR_INPUT = BAR + ' [data-testid="ai-bar-input"]'
MENU = BAR + ' [data-testid="ai-bar-menu"]'
PANEL = BAR + ' [data-testid="ai-bar-panel"]'


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

            requirement = screen_document.get_node()
            form_edit_requirement: Form_EditRequirement = (
                requirement.do_open_form_edit_requirement()
            )
            form_edit_requirement.assert_on_form()
            self.wait_for_element(EDITOR)

            # The bar is above the editor, and "/" lists the commands.
            self.wait_for_element(BAR_INPUT)
            bar = self.find_element(BAR_INPUT)
            bar.click()
            bar.send_keys("/")
            self.wait_for_element(MENU)
            self.assert_text("/rewrite", MENU)
            self.assert_text("/verify", MENU)

            # "@" lists the requirements of the project.
            bar.send_keys(Keys.BACKSPACE)
            bar.send_keys("see @REQ")
            self.wait_for_text("@REQ-2", MENU)
            bar.send_keys(Keys.ESCAPE)
            bar.clear()

            # A command: the proposal is a difference, nothing changed yet.
            bar.send_keys("/rewrite ears")
            bar.send_keys(Keys.ESCAPE)
            bar.send_keys(Keys.ENTER)
            self.wait_for_text("Event-driven pattern.", PANEL)
            self.assert_element(f"{PANEL} ins")
            editor_text = self.get_text(EDITOR)
            assert "When started" not in editor_text, editor_text

            # Applying puts it in the editor; the form saves it.
            self.click(BAR + ' [data-testid="ai-bar-apply"]')
            self.wait_for_text("Text replaced", PANEL)
            self.wait_for_text("When started, the system shall start", EDITOR)
            form_edit_requirement.do_form_submit()
            screen_document.assert_text("When started, the system shall start")

        assert test_setup.compare_sandbox_and_expected_output()
