"""
The table bar of the Markdown editor: a table that needs more than a pipe
table (merged cell, coloured cell, header rows) is written as an HTML table,
and is read back as a table of the editor.
"""

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


def bar(name: str) -> str:
    return f"[data-testid='table-{name}']"


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

            # The bar is hidden until the toggle of the toolbar is used.
            toggle = (
                "(//div[contains(@class,'milkdown-top-bar')]"
                "//*[contains(@class,'top-bar-item')])[last()]"
            )
            self.assert_element_not_visible("[data-testid='table-bar']")
            self.click_xpath(toggle)
            self.assert_element_visible("[data-testid='table-bar']")
            # Outside of a table only "insert a table" is on.
            self.assert_true(self.is_element_enabled(bar("insert")))
            self.assert_false(self.is_element_enabled(bar("merge")))
            self.click_xpath(toggle)
            self.assert_element_not_visible("[data-testid='table-bar']")

            # A click in a table cell shows it: a column, then the cells of a
            # row merged and filled.
            self.click("sdoc-markdown-editor td")
            self.assert_element_visible("[data-testid='table-bar']")
            self.click(bar("column-right"))
            self.click(bar("select-row"))
            self.click(bar("merge"))
            self.click(bar("fill"))
            self.click(bar("color-ffd966"))

            # The alignment is the one of the cell.
            self.click("sdoc-markdown-editor th")
            self.click(bar("align-right"))
            self.assert_element("sdoc-markdown-editor th[style*='right']")

            # A new table goes after the table of the cursor.
            self.click(bar("insert"))
            self.click("[data-testid='table-grid-2x2']")

            form_edit_requirement.do_form_submit()

            screen_document.assert_text("The system shall start.")
            self.assert_element("sdoc-node table td[colspan='3']")

        assert test_setup.compare_sandbox_and_expected_output()
