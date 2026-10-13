"""
/translate in the bar of a document is a job that prepares a new document with
the UIDs suffixed by the language (REQ-1 becomes REQ-1-FR) and the links that
follow. Only "Apply selected" writes the file, and the browser opens it.
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
            bar.send_keys("/translate fr")
            bar.send_keys("\n")
            self.wait_for_text("Create document_FR.sdoc", PANEL)
            self.assert_text("UIDs get the suffix -FR", PANEL)
            self.click('[data-testid="ai-bar-apply"]')
            self.wait_for_text("change(s) saved", PANEL)

            # The browser opens the new document.
            self.wait_for_text("Le système doit démarrer")
            self.assert_text("Document 1 (FR)")

        with open(
            test_setup.path_to_sandbox + "/document_FR.sdoc", encoding="utf8"
        ) as file_:
            text = file_.read()
        assert "UID: REQ-1-FR" in text and "UID: REQ-2-FR" in text
        assert "[LINK: REQ-2-FR]" in text
        assert "LANGUAGE: fr" in text
