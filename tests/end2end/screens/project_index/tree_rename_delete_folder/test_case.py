from selenium.webdriver.common.by import By

from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.components.tree_context_menu import (
    TreeContextMenu,
)
from tests.end2end.helpers.form.form import Form
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)
from tests.end2end.server import SDocTestServer


def folder(name: str) -> str:
    return (
        "//*[@data-testid='tree-folder-node']"
        f"[.//*[@data-testid='tree-folder-title'][normalize-space(.)='{name}/']]"
    )


class Test(E2ECase):
    def test(self):
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with SDocTestServer(
            input_path=test_setup.path_to_sandbox
        ) as test_server:
            self.open(test_server.get_host_and_port())

            screen_project_index = Screen_ProjectIndex(self)
            screen_project_index.assert_on_screen()
            screen_project_index.assert_contains_folder("old")
            menu = TreeContextMenu(self)

            # Rename: a bad name is reported in the form, a good one applies.
            menu.do_click_action(
                "tree-rename-folder-action", node_xpath=folder("old")
            )
            form = Form(self)
            form.do_fill_in("new_name", "a b")
            self.click_xpath("//*[@data-testid='form-submit-action']")
            form.assert_error("Invalid folder name")
            form.do_fill_in("new_name", "")
            form.do_fill_in("new_name", "fresh")
            form.do_form_submit()
            screen_project_index.assert_contains_folder("fresh")
            self.assert_element_not_present(folder("old"), by=By.XPATH)

            # Delete: asks first, then the empty folder is gone.
            menu.do_click_action(
                "tree-delete-folder-action", node_xpath=folder("fresh")
            )
            self.assert_element("//*[@data-testid='confirm-message']")
            self.click_xpath("//*[@data-testid='confirm-action']")
            self.assert_element_not_present(folder("fresh"), by=By.XPATH)
            screen_project_index.assert_contains_document("Keep")

            # A document file is renamed; the title stays.
            document = (
                "//a[@data-testid='tree-file-link'][@data-rel-path='keep.sdoc']"
            )
            menu.do_click_action(
                "tree-rename-document-action", node_xpath=document
            )
            form = Form(self)
            form.do_fill_in("new_name", "a b")
            self.click_xpath("//*[@data-testid='form-submit-action']")
            form.assert_error("Invalid document name")
            form.do_fill_in("new_name", "")
            form.do_fill_in("new_name", "kept")
            form.do_form_submit()
            self.assert_element(
                "//a[@data-testid='tree-file-link']"
                "[@data-rel-path='kept.sdoc']",
                by=By.XPATH,
            )
            self.assert_element_not_present(document, by=By.XPATH)
            screen_project_index.assert_contains_document("Keep")
