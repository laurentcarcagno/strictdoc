"""
The diagram editor of the Markdown editor: a diagram is drawn in a modal,
saved as an SVG file that carries its own model, and opened again by a double
click on the image.
"""

import base64
import re
from pathlib import Path
from typing import List

from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys

from tests.end2end.e2e_case import E2ECase
from tests.end2end.end2end_test_setup import End2EndTestSetup
from tests.end2end.helpers.screens.document.form_edit_requirement import (
    Form_EditRequirement,
)
from tests.end2end.helpers.screens.project_index.screen_project_index import (
    Screen_ProjectIndex,
)
from tests.end2end.server import SDocTestServer

EDITOR = "sdoc-markdown-editor[data-ready=true] .ProseMirror"
DIAGRAM_MODAL = "[data-testid='diagram-editor']"
DIAGRAM_IMAGE = "sdoc-markdown-editor img[src*='diagram_']"
DIAGRAM_BUTTON = (
    "//*[contains(@class,'top-bar-item')]"
    "[.//*[contains(@class,'sdoc-diagram-icon')]]"
)


def tool(name: str) -> str:
    return f"[data-testid='diagram-{name}']"


def diagram_files(path_to_sandbox: str) -> List[Path]:
    return sorted(Path(path_to_sandbox).glob("_assets/REQ-1/diagram_*.svg"))


def model_of(svg_file: Path) -> str:
    svg = svg_file.read_text(encoding="utf-8")
    match = re.search(
        r"<desc id=\"sdoc-diagram\">sdoc-diagram:v1:([^<]+)<", svg
    )
    assert match is not None, "The SVG file has no diagram model."
    return base64.b64decode(match.group(1)).decode("utf-8")


class Test(E2ECase):
    def test(self):
        test_setup = End2EndTestSetup(path_to_test_file=__file__)

        with SDocTestServer(
            input_path=test_setup.path_to_sandbox
        ) as test_server:
            self.open(test_server.get_host_and_port())

            screen_project_index = Screen_ProjectIndex(self)
            screen_project_index.assert_on_screen()
            screen_document = screen_project_index.do_click_on_first_document()
            screen_document.assert_on_screen_document()

            requirement = screen_document.get_node()
            form_edit_requirement: Form_EditRequirement = (
                requirement.do_open_form_edit_requirement()
            )
            form_edit_requirement.assert_on_form()
            self.wait_for_element(EDITOR)

            # Cancel after a change asks first, and inserts nothing.
            self.click_xpath(DIAGRAM_BUTTON)
            self.assert_element_visible(DIAGRAM_MODAL)
            self.click(tool("shape-rectangle"))
            self.click(tool("cancel"))
            self.accept_alert()
            self.assert_element_not_visible(DIAGRAM_MODAL)
            self.assert_element_absent(DIAGRAM_IMAGE)

            # Two shapes, a connector between them and its label.
            self.click_xpath(DIAGRAM_BUTTON)
            self.assert_element_visible(DIAGRAM_MODAL)
            self.assert_false(self.is_element_enabled(tool("save")))
            self.click(tool("shape-rectangle"))
            self.click(tool("shape-ellipse"))
            self.assert_true(self.is_element_enabled(tool("save")))
            actions = ActionChains(self.driver)
            actions.key_down(Keys.CONTROL).send_keys("a").key_up(
                Keys.CONTROL
            ).perform()
            self.click(tool("connect"))
            actions = ActionChains(self.driver)
            actions.send_keys(Keys.ENTER).send_keys("go").send_keys(
                Keys.F2
            ).perform()
            self.click(tool("save"))
            self.assert_element_not_visible(DIAGRAM_MODAL)
            self.assert_element(DIAGRAM_IMAGE)

            form_edit_requirement.do_form_submit()
            self.assert_element("sdoc-node img[src*='diagram_']")

            files = diagram_files(test_setup.path_to_sandbox)
            assert len(files) == 1, files
            svg = files[0].read_text(encoding="utf-8")
            assert "foreignObject" not in svg
            assert ">go<" in svg
            model = model_of(files[0])
            assert model.count('vertex="1"') == 2, model
            assert model.count('edge="1"') == 1, model

            # A double click on the image opens the diagram again. Save
            # overwrites the same file.
            requirement = screen_document.get_node()
            form_edit_requirement = requirement.do_open_form_edit_requirement()
            form_edit_requirement.assert_on_form()
            self.wait_for_element(EDITOR)
            self.double_click(DIAGRAM_IMAGE)
            self.assert_element_visible(DIAGRAM_MODAL)
            self.click(tool("shape-diamond"))
            self.click(tool("save"))
            self.assert_element_not_visible(DIAGRAM_MODAL)
            form_edit_requirement.do_form_submit()

            files = diagram_files(test_setup.path_to_sandbox)
            assert len(files) == 1, files
            model = model_of(files[0])
            assert model.count('vertex="1"') == 3, model
            assert model.count('edge="1"') == 1, model
