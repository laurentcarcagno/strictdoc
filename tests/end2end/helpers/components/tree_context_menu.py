from selenium.webdriver import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from seleniumbase import BaseCase


class TreeContextMenu:
    """
    The menu of the project tree: it opens with a right click on a node of the
    tree in the left bar (the project at the top, a folder, a document).
    """

    ROOT = "//*[@data-testid='tree-root-node']"

    def __init__(self, test_case: BaseCase) -> None:
        assert isinstance(test_case, BaseCase)
        self.test_case: BaseCase = test_case

    def do_open(self, node_xpath: str = ROOT) -> None:
        # A menu that is still open covers the rows below it.
        ActionChains(self.test_case.driver).send_keys(Keys.ESCAPE).perform()
        self.test_case.context_click(node_xpath, by=By.XPATH)
        self.test_case.assert_element(
            "//*[@data-testid='tree-context-menu']"
            "[not(@hidden)]//a[@role='menuitem']",
            by=By.XPATH,
        )

    def do_click_action(self, testid: str, node_xpath: str = ROOT) -> None:
        assert isinstance(testid, str)
        self.do_open(node_xpath)
        self.test_case.click_xpath(
            f"//*[@data-testid='tree-context-menu']//a[@data-testid='{testid}']"
        )

    def assert_has_action(self, testid: str, node_xpath: str = ROOT) -> None:
        self.do_open(node_xpath)
        self.test_case.assert_element(
            f"//*[@data-testid='tree-context-menu']//a[@data-testid='{testid}']",
            by=By.XPATH,
        )

    def do_drag_and_drop(self, source_xpath: str, target_xpath: str) -> None:
        """
        Drags a node of the tree onto another one with the mouse: the tree
        follows the pointer, it does not use the drag and drop of the browser.
        """
        self.test_case.assert_element(source_xpath, by=By.XPATH)
        self.test_case.assert_element(target_xpath, by=By.XPATH)
        source = self.test_case.find_element(source_xpath, by=By.XPATH)
        target = self.test_case.find_element(target_xpath, by=By.XPATH)
        (
            ActionChains(self.test_case.driver)
            .move_to_element(source)
            .click_and_hold()
            .move_by_offset(8, 8)
            .move_by_offset(8, 8)
            .move_to_element(target)
            .move_by_offset(2, 0)
            .release()
            .perform()
        )
