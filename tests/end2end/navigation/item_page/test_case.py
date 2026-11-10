"""
@relation(SDOC-SRS-213, scope=file)
"""

from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.document.screen_document import (
    Screen_Document,
)
from tests.end2end.server import SDocTestServer


class Test(E2ECase):
    """
    The page of an item shows its content, follows a link to the parent, and
    goes back to the item in its document. The comments tab is disabled and
    says why, because the project does not activate the comments.
    """

    def test(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with SDocTestServer(
            input_path=test_setup.path_to_sandbox
        ) as test_server:
            self.open(test_server.get_host_and_port() + "/item/REQ-2")

            self.assert_text("REQ-2", '[data-testid="item-title"]')
            self.assert_text("Child statement.", '[data-testid="item-content"]')

            tab = self.find_element('[data-testid="item-tab-comments"]')
            assert tab.get_attribute("aria-disabled") == "true"
            assert "not activated" in tab.get_attribute("title")

            self.click('[data-testid="item-tab-links"]')
            self.assert_element('[data-testid="item-link-group"]')
            self.click('[data-testid="item-link"] a')
            self.assert_text("REQ-1", '[data-testid="item-title"]')

            self.click('[data-testid="item-back-to-document"]')
            screen_document = Screen_Document(self)
            screen_document.assert_on_screen_document()
            screen_document.assert_target_by_anchor("REQ-1")
