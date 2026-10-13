"""
/comment in the bar gives remarks as proposals. Only the ticked ones become
comments, written as comments of the user (no mark of the assistant), and the
page reloads to show them. The ids and the dates of the comments change at each
run, so the file is read, not compared.
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
BAR_INPUT = '[data-testid="ai-bar-input"]'
PANEL = '[data-testid="ai-bar-panel"]'


class Test(E2ECase):
    def test(self):
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with SDocTestServer(
            input_path=test_setup.path_to_sandbox
        ) as test_server:
            self.open(test_server.get_host_and_port())

            screen_project_index = Screen_ProjectIndex(self)
            screen_document = screen_project_index.do_click_on_first_document()
            screen_document.assert_on_screen_document()

            requirement = screen_document.get_node()
            form_edit_requirement: Form_EditRequirement = (
                requirement.do_open_form_edit_requirement()
            )
            form_edit_requirement.assert_on_form()
            self.wait_for_element(EDITOR)

            self.wait_for_element(BAR_INPUT)
            bar = self.find_element(BAR_INPUT)
            bar.click()
            bar.send_keys("/comment ambiguity")
            bar.send_keys("\n")
            self.wait_for_text("Start what, and when?", PANEL)
            # Two remarks: the warning is ticked, the info is not.
            boxes = self.find_elements(f"{PANEL} input[type=checkbox]")
            assert [box.is_selected() for box in boxes] == [True, False]

            self.click('[data-testid="ai-bar-apply"]')
            self.wait_for_text("change(s) saved", PANEL)

        saved = test_setup.path_to_sandbox + "/document.sdoc"
        with open(saved, encoding="utf8") as file_:
            text = file_.read()
        assert "Start what, and when?" in text
        assert "Fine otherwise." not in text
        # No mark of the assistant in the comment.
        assert "source=llm" not in text and "model=" not in text
