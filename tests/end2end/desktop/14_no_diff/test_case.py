"""
The application does not offer the comparison of Git revisions, even for a
project that declares the feature DIFF: the pages "/diff" and "/diff_result"
answer "not found", and no link leads to them.

@relation(SDOC-SRS-1248, scope=file)
"""

import sys

import pytest

from tests.end2end.desktop.desktop_case import DesktopCase
from tests.end2end.desktop.desktop_test_server import DesktopTestServer
from tests.end2end.end2end_test_setup import End2EndTestSetup

# A synchronous request of the page, with its cookie: the status of the answer.
GET_STATUS_SCRIPT = (
    "var request = new XMLHttpRequest();"
    "request.open('GET', arguments[0], false);"
    "request.send();"
    "return request.status;"
)


@pytest.mark.skipif(
    sys.platform == "win32", reason="The user folders follow XDG variables."
)
class Test(DesktopCase):
    def test_001_the_comparison_of_revisions_is_not_found(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with DesktopTestServer(
            input_path=test_setup.path_to_sandbox,
            project_path=test_setup.path_to_sandbox,
        ) as test_server:
            self.open(test_server.get_start_url())

            # The project is served, with the feature that it declares.
            self.assert_text("Document of the comparison")
            for path_ in ("/diff", "/diff_result"):
                status = self.execute_script(GET_STATUS_SCRIPT, path_)
                assert status == 404, (path_, status)
            # No link of the pages leads to the comparison.
            assert 'href="/diff' not in self.get_page_source()

            self.open(
                test_server.get_start_url().split("/__desktop")[0] + "/diff"
            )
            self.assert_text("Not Found")
