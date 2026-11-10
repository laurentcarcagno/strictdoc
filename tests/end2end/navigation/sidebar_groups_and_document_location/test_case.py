"""
@relation(SDOC-SRS-208, SDOC-SRS-209, scope=file)
"""

from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)
from tests.end2end.server import SDocTestServer


class Test(E2ECase):
    """
    The sidebar shows its items in groups, and the page header of a document
    says where the document is: the project, then its folders.
    """

    def test(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with SDocTestServer(
            input_path=test_setup.path_to_sandbox
        ) as test_server:
            self.open(test_server.get_host_and_port())

            screen_project_index = Screen_ProjectIndex(self)
            screen_project_index.assert_on_screen()

            # The default features of a server: the search is in Analysis;
            # no diff, so there is no Versions group.
            self.assert_element(
                '//*[@data-testid="nav-group-analysis"]'
                '//*[@data-testid="project-tree-link-search"]',
                by="xpath",
            )
            self.assert_element_absent('[data-testid="nav-group-versions"]')

            screen_document = screen_project_index.do_click_on_first_document()
            screen_document.assert_on_screen_document()
            screen_document.assert_header_document_title("System specification")

            self.assert_element('[data-testid="header-context"]')
            folders = [
                element_.text.strip().lower()
                for element_ in self.find_elements(
                    '[data-testid="header-breadcrumb-folder"]'
                )
            ]
            assert folders == ["specs", "system"], folders

            # Without the GIT feature, the header shows no version.
            self.assert_element_absent(
                '[data-testid="header-document-version"]'
            )

            # The project name stays the element that the other tests
            # click to click outside an editor: it is no link.
            self.click("#header-project-name")
            screen_document.assert_on_screen_document()
