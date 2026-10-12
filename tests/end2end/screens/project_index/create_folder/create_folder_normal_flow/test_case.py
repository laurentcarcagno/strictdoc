from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)
from tests.end2end.server import SDocTestServer


class Test(E2ECase):
    def test(self):
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with SDocTestServer(
            input_path=test_setup.path_to_sandbox
        ) as test_server:
            self.open(test_server.get_host_and_port())

            screen_project_index = Screen_ProjectIndex(self)
            screen_project_index.assert_on_screen()
            screen_project_index.assert_empty_tree()

            # Several levels at once; the empty folders are shown.
            form_add_folder = (
                screen_project_index.do_open_modal_form_add_folder()
            )
            form_add_folder.do_fill_in_path("specs/system")
            form_add_folder.do_form_submit()
            screen_project_index.assert_contains_folder("specs")
            screen_project_index.assert_contains_folder("system")

            # A document in the new folder.
            form_add_document = (
                screen_project_index.do_open_modal_form_add_document()
            )
            form_add_document.do_fill_in_title("Interface")
            form_add_document.do_fill_in_path("specs/system/interface.sdoc")
            form_add_document.do_form_submit()
            screen_project_index.assert_contains_document("Interface")

        assert test_setup.compare_sandbox_and_expected_output()
