"""
@relation(SDOC-SRS-215, scope=file)
"""

import subprocess

from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)
from tests.end2end.server import SDocTestServer


def git(cwd: str, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


class Test(E2ECase):
    """
    The version in the header of a document opens the versions of the
    document. A version is read without changing the document, and two
    versions are compared.
    """

    def test(self) -> None:
        test_setup = End2EndTestSetup(path_to_test_file=__file__)
        sandbox = test_setup.path_to_sandbox

        git(sandbox, "init", "-q", "-b", "main")
        git(sandbox, "add", "-A")
        git(sandbox, "commit", "-q", "-m", "first version")
        git(sandbox, "tag", "A1")
        path = f"{sandbox}/spec.sdoc"
        with open(path, encoding="utf8") as file_:
            text = file_.read()
        with open(path, "w", encoding="utf8") as file_:
            file_.write(text.replace("Alpha.", "Alpha, reworded."))
        git(sandbox, "commit", "-q", "-am", "second version")
        git(sandbox, "tag", "A2")

        with SDocTestServer(input_path=sandbox) as test_server:
            self.open(test_server.get_host_and_port())
            screen_project_index = Screen_ProjectIndex(self)
            screen_project_index.assert_on_screen()
            screen_document = screen_project_index.do_click_on_first_document()
            screen_document.assert_on_screen_document()

            self.click('[data-testid="header-document-version"]')
            self.assert_text(
                "Versioned document", '[data-testid="versions-title"]'
            )
            self.assert_element('[data-testid="versions-row"]')

            self.click('a[href$="/A1"]')
            self.click('[data-testid="version-item"] summary')
            self.assert_text("Alpha.", '[data-testid="version-items"]')
            self.assert_text_not_visible("Alpha, reworded.")
            self.click('[data-testid="version-back"]')

            self.select_option_by_value('[data-testid="versions-from"]', "A1")
            self.select_option_by_value('[data-testid="versions-to"]', "A2")
            self.click('[data-testid="versions-compare"]')
            self.assert_text("0 added, 0 removed, 1 changed, 1 unchanged")
            self.assert_text("+ Alpha, reworded.")
