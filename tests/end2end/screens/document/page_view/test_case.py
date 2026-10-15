from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.server import SDocTestServer

SHEETS = ".sdoc-page-sheet"


def button(mode: str) -> str:
    return f"[data-testid='page-view-{mode}']"


class Test(E2ECase):
    def test(self):
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with SDocTestServer(
            input_path=test_setup.path_to_sandbox
        ) as test_server:
            self.open(test_server.get_host_and_port())
            self.click_xpath("//a[@data-testid='tree-file-link']")
            self.assert_element(button("normal"))

            # The normal view has no sheet.
            self.assert_element_not_present(SHEETS)

            # One page: the sheets are stacked in one column.
            self.click(button("one"))
            self.assert_element(SHEETS)
            lefts = self.execute_script(
                "return [...document.querySelectorAll('.sdoc-page-sheet')]"
                ".map(e => e.style.left)"
            )
            assert len(lefts) >= 2, lefts
            assert len(set(lefts)) == 1, lefts

            # Two pages: two columns of sheets.
            self.click(button("two"))
            self.assert_element(f"{SHEETS}:not([style*='left: 0px'])")
            lefts = self.execute_script(
                "return [...document.querySelectorAll('.sdoc-page-sheet')]"
                ".map(e => e.style.left)"
            )
            assert len(set(lefts)) == 2, lefts

            # The choice is kept when the page is loaded again.
            self.refresh()
            self.assert_element(SHEETS)
            self.assert_attribute(button("two"), "aria-pressed", "true")

            # Back to the normal view.
            self.click(button("normal"))
            self.assert_element_not_present(SHEETS)
            self.assert_attribute(button("normal"), "aria-pressed", "true")
