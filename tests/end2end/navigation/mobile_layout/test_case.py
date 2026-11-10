"""
@relation(SDOC-SRS-216, scope=file)
"""

from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.server import SDocTestServer

PHONE_WIDTH = 390
PHONE_HEIGHT = 844
DESKTOP_WIDTH = 1400
DESKTOP_HEIGHT = 900

NO_HORIZONTAL_SCROLL = (
    "return document.documentElement.scrollWidth <= window.innerWidth;"
)


class Test(E2ECase):
    """
    On a phone, the page shows the content, and the button of the menu
    switches to the sidebar and back. No screen scrolls sideways. On a
    desktop, there is no such button.
    """

    def test(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        # The browser session is shared with the next tests: the window
        # goes back to the desktop size whatever happens.
        try:
            with SDocTestServer(
                input_path=test_setup.path_to_sandbox
            ) as test_server:
                host = test_server.get_host_and_port()

                self.set_window_size(DESKTOP_WIDTH, DESKTOP_HEIGHT)
                self.open(host)
                self.assert_element('[data-testid="nav"]')
                self.assert_element_not_visible(
                    '[data-testid="layout-menu-toggle"]'
                )

                self.set_window_size(PHONE_WIDTH, PHONE_HEIGHT)
                self.open(host)
                self.assert_element('[data-testid="layout-menu-toggle"]')
                self.assert_element_not_visible('[data-testid="nav"]')
                assert self.execute_script(NO_HORIZONTAL_SCROLL)

                self.click('[data-testid="layout-menu-toggle"]')
                self.assert_element('[data-testid="nav"]')
                self.assert_element_not_visible(".layout_main")

                self.click('[data-testid="layout-menu-toggle"]')
                self.assert_element_not_visible('[data-testid="nav"]')
                self.assert_element(".layout_main")

                self.open(host + "/item/REQ-1")
                self.assert_text("REQ-1", '[data-testid="item-title"]')
                assert self.execute_script(NO_HORIZONTAL_SCROLL)

                self.open(host + "/item/REQ-1?tab=links")
                assert self.execute_script(NO_HORIZONTAL_SCROLL)
        finally:
            self.set_window_size(DESKTOP_WIDTH, DESKTOP_HEIGHT)
