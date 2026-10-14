from selenium.webdriver.common.by import By
from seleniumbase import BaseCase

TREE = "//*[@data-testid='nav-project-tree']"


class AsideProjectTree:  # pylint: disable=invalid-name
    """
    The project tree. It is in the left bar (under the project picker) on every
    screen of the server; its menu is the one of a right click on its nodes.
    """

    def __init__(self, test_case: BaseCase) -> None:
        assert isinstance(test_case, BaseCase)
        self.test_case: BaseCase = test_case

    def assert_is_aside_tree(self) -> None:
        self.test_case.assert_element(TREE, by=By.XPATH)

    def assert_tree_contains(self, string: str) -> None:
        self.test_case.assert_element_present(
            f"{TREE}//*[contains(., '{string}')]",
            by=By.XPATH,
        )

    def assert_tree_contains_not(self, string: str) -> None:
        self.test_case.assert_element_not_present(
            f"{TREE}//*[contains(., '{string}')]",
            by=By.XPATH,
        )

    def assert_tree_contains_document_title(self, title: str) -> None:
        self.test_case.assert_element_present(
            f"{TREE}//a[@data-testid='tree-file-link']"
            f"/span[@class='sdoc-tree__title'][normalize-space(.)='{title}']",
            by=By.XPATH,
        )

    def do_tree_go_to_document(self, title: str) -> None:
        self.test_case.click_xpath(
            f"{TREE}//a[@data-testid='tree-file-link']"
            f"[.//span[@class='sdoc-tree__title'][normalize-space(.)='{title}']]"
        )
