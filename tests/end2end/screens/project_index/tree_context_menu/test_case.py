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

FOLDER_NODE = (
    "//*[@data-testid='tree-folder-node']"
    "[.//*[@data-testid='tree-folder-title'][normalize-space(.)='specs/']]"
)
DOCUMENT_NODE = "//*[@data-testid='tree-file-link'][@data-tree-node='document']"


class Test(E2ECase):
    def test(self):
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with SDocTestServer(
            input_path=test_setup.path_to_sandbox
        ) as test_server:
            self.open(test_server.get_host_and_port())

            screen_project_index = Screen_ProjectIndex(self)
            screen_project_index.assert_on_screen()
            screen_project_index.assert_contains_folder("specs")
            screen_project_index.assert_contains_document("Alpha")

            menu = TreeContextMenu(self)

            # The menu of a folder fills in the path of the folder.
            menu.do_click_action(
                "tree-add-document-here-action", node_xpath=FOLDER_NODE
            )
            self.assert_element("//sdoc-modal", by=By.XPATH)
            self.assert_equal(
                self.execute_script(
                    "return document.querySelector("
                    "\"[data-testid='form-field-document_path']\").textContent.trim();"
                ),
                "specs/",
            )
            self.click_xpath("//*[@data-testid='form-cancel-action']")
            self.assert_element_not_present("//sdoc-modal", by=By.XPATH)

            # The menu of the project has no "here" actions, the menu of a
            # document has Open and not the actions of the project.
            menu.do_open()
            self.assert_element_not_present(
                "//*[@data-testid='tree-context-menu']"
                "//a[@data-testid='tree-add-document-here-action']",
                by=By.XPATH,
            )
            menu.do_open(DOCUMENT_NODE)
            menu.assert_has_action(
                "tree-open-document-action", node_xpath=DOCUMENT_NODE
            )
            self.assert_element_not_present(
                "//*[@data-testid='tree-context-menu']"
                "//a[@data-testid='tree-add-folder-action']",
                by=By.XPATH,
            )
