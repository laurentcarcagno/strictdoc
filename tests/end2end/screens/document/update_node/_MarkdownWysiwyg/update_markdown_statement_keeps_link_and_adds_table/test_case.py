"""
The WYSIWYG Markdown editor edits the statement of a node of a Markdown
document: the text is saved as Markdown, [LINK: UID] is not escaped and a
table pasted into the editor is written as a pipe table.
"""

from selenium.webdriver.common.by import By
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

            # The Markdown editor replaces the plain editor for the statement.
            self.wait_for_element(EDITOR)
            self.assert_element_not_present(
                '//sdoc-contenteditable[@data-testid="form-field-STATEMENT"]',
                by=By.XPATH,
            )
            self.assert_element(
                'sdoc-markdown-editor [class*="top-bar"]',
            )

            editor = self.find_element(EDITOR)
            editor.click()
            editor.send_keys(Keys.CONTROL, Keys.END)
            editor.send_keys(" Edited.")
            self.execute_script(
                "const editor = document.querySelector(arguments[0]);"
                "editor.focus();"
                "const data = new DataTransfer();"
                "data.setData('text/plain', "
                "  '| a | b |\\n| --- | --- |\\n| 1 | 2 |\\n');"
                "editor.dispatchEvent(new ClipboardEvent('paste', "
                "  {clipboardData: data, bubbles: true, cancelable: true}));",
                EDITOR,
            )
            self.wait_for_element("sdoc-markdown-editor tr")

            form_edit_requirement.do_form_submit()

            screen_document.assert_text("Edited.")
            self.assert_element("table")

        assert test_setup.compare_sandbox_and_expected_output()
