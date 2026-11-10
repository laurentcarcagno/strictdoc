"""
@relation(SDOC-SRS-212, scope=file)
"""

import os

from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)
from tests.end2end.server import SDocTestServer

PATH_TO_THIS_FOLDER = os.path.dirname(os.path.abspath(__file__))

READER = {
    "X-Forwarded-Preferred-Username": "ruth",
    "X-Forwarded-User": "id-ruth",
    "X-Forwarded-Groups": "t-readers",
}

EDIT_ACTION = '[data-testid="node-edit-action"]'


class Test(E2ECase):
    """
    A reader sees the actions that the role does not allow, disabled: each
    says which role it needs, and a click on it does nothing.
    """

    def test(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with SDocTestServer(
            input_path=test_setup.path_to_sandbox,
            config_path=os.path.join(
                PATH_TO_THIS_FOLDER, "config", "strictdoc_config.py"
            ),
        ) as test_server:
            # The browser plays the login proxy: it sends the identity of a
            # reader with every request.
            self.execute_cdp_cmd("Network.enable", {})
            self.execute_cdp_cmd(
                "Network.setExtraHTTPHeaders", {"headers": READER}
            )
            try:
                self.open(test_server.get_host_and_port())
                self.execute_script("sessionStorage.clear()")

                screen_project_index = Screen_ProjectIndex(self)
                screen_project_index.assert_on_screen()
                screen_document = (
                    screen_project_index.do_click_on_first_document()
                )
                screen_document.assert_on_screen_document()

                # The edit action is on the page, disabled, with the reason.
                self.wait_for_element_present(
                    f'{EDIT_ACTION}[aria-disabled="true"]'
                )
                assert (
                    self.get_attribute(EDIT_ACTION, "title", hard_fail=False)
                    == "Needs the author role"
                )
                assert (
                    self.get_attribute(
                        '[data-testid="document-delete-action"]',
                        "title",
                        hard_fail=False,
                    )
                    == "Needs the administrator role"
                )

                # A click on it opens no form.
                self.execute_script(
                    f"document.querySelector('{EDIT_ACTION}').click()"
                )
                self.sleep(1)
                self.assert_element_absent('[data-testid="form-cancel-action"]')
                screen_document.assert_on_screen_document()
            finally:
                self.execute_cdp_cmd(
                    "Network.setExtraHTTPHeaders", {"headers": {}}
                )
                self.execute_script("sessionStorage.clear()")
