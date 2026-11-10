"""
@relation(SDOC-SRS-214, scope=file)
"""

import os

from tests.end2end.e2e_case import E2ECase
from tests.end2end.helpers.screens.search.search import Screen_Search
from tests.end2end.server import SDocTestServer

path_to_this_test_file_folder = os.path.dirname(os.path.abspath(__file__))


class Test(E2ECase):
    """
    An exact UID opens the page of the item. The facets search without a
    query: the status keeps the items that have it.
    """

    def test(self) -> None:
        with SDocTestServer(
            input_path=path_to_this_test_file_folder
        ) as test_server:
            self.open(test_server.get_host_and_port() + "/search")

            screen_search = Screen_Search(self)
            screen_search.do_search("REQ-2")
            self.assert_text("REQ-2", '[data-testid="item-title"]')

            self.open(test_server.get_host_and_port() + "/search")
            self.select_option_by_value(
                '[data-testid="search-facet-status"]', "Draft"
            )
            self.click('[data-testid="form-submit-action"]')
            self.assert_text("Child requirement")
            self.assert_text_not_visible("Parent requirement")
