"""
The bar at the top of a document: "/review" is a job that reads the
requirements and proposes comments, shown as cards while they come; only the
ticked ones are saved, as comments of the user. The ids and dates of the
comments change at each run, so the file is read, not compared.
"""

from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)
from tests.end2end.server import SDocTestServer

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

            self.wait_for_element(BAR_INPUT)
            bar = self.find_element(BAR_INPUT)
            bar.click()
            # "/" in the document bar lists the document commands.
            bar.send_keys("/")
            self.wait_for_text("/review", '[data-testid="ai-bar-menu"]')
            self.assert_text("/write", '[data-testid="ai-bar-menu"]')
            assert "/rewrite" not in self.get_text(
                '[data-testid="ai-bar-menu"]'
            )
            bar.send_keys("review")
            bar.send_keys("\n")
            bar.send_keys("\n")

            self.wait_for_text("Start what, and when?", PANEL)
            self.wait_for_text("Done:", PANEL)
            boxes = self.find_elements(f"{PANEL} input[type=checkbox]")
            assert [box.is_selected() for box in boxes] == [True, False]

            self.click('[data-testid="ai-bar-apply"]')
            self.wait_for_text("change(s) saved", PANEL)

        with open(
            test_setup.path_to_sandbox + "/document.sdoc", encoding="utf8"
        ) as file_:
            text = file_.read()
        assert "Start what, and when?" in text
        assert "Name the stopping condition." not in text
