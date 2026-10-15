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
        Drags a node of the tree onto another one. The browser driver does not
        do HTML5 drag and drop, so the events are sent with a DataTransfer.
        """
        self.test_case.assert_element(source_xpath, by=By.XPATH)
        self.test_case.assert_element(target_xpath, by=By.XPATH)
        self.test_case.execute_script(
            """
            const find = (xpath) => document.evaluate(
              xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null
            ).singleNodeValue;
            const source = find(arguments[0]);
            const target = find(arguments[1]);
            const data = new DataTransfer();
            const fire = (node, type) => node.dispatchEvent(
              new DragEvent(type, {bubbles: true, cancelable: true,
                                   dataTransfer: data})
            );
            fire(source, 'dragstart');
            fire(target, 'dragenter');
            fire(target, 'dragover');
            fire(target, 'drop');
            fire(source, 'dragend');
            """,
            source_xpath,
            target_xpath,
        )
