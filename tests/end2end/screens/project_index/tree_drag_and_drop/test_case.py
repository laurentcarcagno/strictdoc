from selenium.webdriver.common.by import By

from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.components.tree_context_menu import (
    TreeContextMenu,
)
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)
from tests.end2end.server import SDocTestServer


def folder(name: str) -> str:
    return (
        "//*[@data-testid='tree-folder-node']"
        f"[.//*[@data-testid='tree-folder-title'][normalize-space(.)='{name}/']]"
    )


def document(rel_path: str) -> str:
    return f"//a[@data-testid='tree-file-link'][@data-rel-path='{rel_path}']"


ROOT = "//*[@data-testid='tree-root-node']"


class Test(E2ECase):
    def test(self):
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with SDocTestServer(
            input_path=test_setup.path_to_sandbox
        ) as test_server:
            self.open(test_server.get_host_and_port())

            screen_project_index = Screen_ProjectIndex(self)
            screen_project_index.assert_on_screen()
            screen_project_index.assert_contains_folder("x")
            screen_project_index.assert_contains_folder("y")
            menu = TreeContextMenu(self)

            # A document dragged onto a folder goes into it.
            menu.do_drag_and_drop(document("alpha.sdoc"), folder("x"))
            self.assert_element(document("x/alpha.sdoc"), by=By.XPATH)
            self.assert_element_not_present(document("alpha.sdoc"), by=By.XPATH)

            # A folder dragged onto a folder goes into it, with its content.
            menu.do_drag_and_drop(folder("x"), folder("y"))
            self.assert_element(document("y/x/alpha.sdoc"), by=By.XPATH)

            # A folder cannot go into itself: nothing happens.
            menu.do_drag_and_drop(folder("y"), folder("x"))
            self.assert_element(document("y/x/alpha.sdoc"), by=By.XPATH)

            # A move that the server refuses is explained.
            menu.do_drag_and_drop(document("dup.sdoc"), folder("y"))
            self.assert_element("//*[@data-testid='tree-notice']", by=By.XPATH)
            self.assert_element(document("dup.sdoc"), by=By.XPATH)

            # A document dragged onto the project goes back to the top.
            menu.do_drag_and_drop(document("y/x/alpha.sdoc"), ROOT)
            self.assert_element(document("alpha.sdoc"), by=By.XPATH)

            # The page of a document that moves follows it.
            self.click_xpath(document("alpha.sdoc"))
            self.assert_element(
                "//body[@data-viewtype='document']", by=By.XPATH
            )
            menu.do_drag_and_drop(document("alpha.sdoc"), folder("y"))
            self.assert_element(document("y/alpha.sdoc"), by=By.XPATH)
            self.assert_url_contains("/y/alpha.html")
            self.assert_element(
                "//body[@data-viewtype='document']", by=By.XPATH
            )
