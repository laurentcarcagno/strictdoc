"""
Checks the diagram editor of the Markdown editor in a real browser.

It draws a diagram, aligns and distributes the shapes, resizes the image with
its handles, opens the diagram again (double click, then selection and toolbar
button) and reloads the form. It reads the SVG file that the server stored.

Usage (see README.md): a StrictDoc server runs on the sample project, and

    SDOC_URL=http://host.docker.internal:5111/sample/document.html \
    SDOC_SHOTS=/work/shots python check_diagrams.py

SDOC_URL is the address of the document screen of the sample. SDOC_SHOTS is an
optional folder for screenshots. The exit code is 1 when a check fails.
"""

import base64
import os
import re
import sys
from typing import List

from playwright.sync_api import Page, sync_playwright

URL = os.environ["SDOC_URL"]
SHOTS = os.environ.get("SDOC_SHOTS")
FAILED: List[str] = []

EDITOR = "sdoc-markdown-editor[data-ready=true] .ProseMirror"
DIAGRAMS = "sdoc-markdown-editor img[src*='diagram_']"
DIAGRAM_BUTTON = ".top-bar-item:has(.sdoc-diagram-icon)"


def report(*values: object) -> None:
    print(*values, flush=True)  # noqa: T201


def check(name: str, condition: bool, detail: object = "") -> None:
    report(("PASS " if condition else "FAIL ") + name, detail)
    if not condition:
        FAILED.append(name)


def shot(page: Page, name: str) -> None:
    if SHOTS is not None:
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=f"{SHOTS}/{name}.png")


def tool(name: str) -> str:
    return f"[data-testid=diagram-{name}]"


def model_of(svg: str) -> str:
    match = re.search(r'<desc id="sdoc-diagram">sdoc-diagram:v1:([^<]+)<', svg)
    return base64.b64decode(match.group(1)).decode() if match else ""


def vertices(model: str) -> list:
    """The (x, y, width, height) of the shapes of a diagram model."""
    result = []
    for cell in re.findall(
        r'<Cell [^>]*vertex="1"[^>]*>.*?</Cell>', model, re.S
    ):
        geometry = re.search(
            r'<Geometry _x="([-\d.]+)" _y="([-\d.]+)" '
            r'_width="([\d.]+)" _height="([\d.]+)"',
            cell,
        )
        if geometry:
            result.append(tuple(float(value) for value in geometry.groups()))
    return result


def size_of(svg: str) -> tuple:
    """The width and height of the <svg>, and whether the axes scale alone."""
    root = re.search(r"<svg[^>]*>", svg).group(0)

    def number(attribute: str) -> float:
        return float(re.search(attribute + r'="([\d.]+)"', root).group(1))

    return (
        number("width"),
        number("height"),
        'preserveAspectRatio="none"' in root,
    )


def sources(page: Page) -> List[str]:
    return page.eval_on_selector_all(
        DIAGRAMS, "images => images.map(image => image.getAttribute('src'))"
    )


def stored_svg(page: Page, src: str) -> str:
    return page.evaluate(
        """async (src) => {
          const image = document.querySelector(
            `sdoc-markdown-editor img[src='${src}']`);
          const response = await fetch(image.src, {cache: 'reload'});
          return await response.text();
        }""",
        src,
    )


def open_form(page: Page) -> None:
    page.goto(URL)
    page.locator("sdoc-node").first.hover()
    page.locator('[data-testid="node-edit-action"]').first.click(force=True)
    page.wait_for_selector(EDITOR)


def drag(page: Page, handle: str, delta_x: float, delta_y: float) -> None:
    box = page.locator(f"[data-testid=diagram-resize-{handle}]").bounding_box()
    page.mouse.move(box["x"] + 5, box["y"] + 5)
    page.mouse.down()
    page.mouse.move(box["x"] + 5 + delta_x, box["y"] + 5 + delta_y, steps=8)
    page.mouse.up()
    page.wait_for_timeout(1500)


def draw_diagram(page: Page) -> str:
    """Three shapes, distributed and aligned. Returns the new image address."""
    before = set(sources(page))
    page.locator(DIAGRAM_BUTTON).click()
    page.wait_for_selector(tool("editor"))
    for shape in ("rectangle", "ellipse", "diamond"):
        page.click(tool(f"shape-{shape}"))
    check("save is on with a shape", page.is_enabled(tool("save")))
    check(
        "distribute is off with nothing selected",
        not page.is_enabled(tool("distribute-horizontally")),
    )
    page.locator(tool("canvas")).focus()
    page.keyboard.press("Control+a")
    check(
        "align is on with three shapes",
        page.is_enabled(tool("align-shapes-left")),
    )
    check(
        "distribute is on with three shapes",
        page.is_enabled(tool("distribute-horizontally")),
    )
    page.click(tool("distribute-horizontally"))
    page.click(tool("align-shapes-top"))
    shot(page, "aligned")
    page.click(tool("save"))
    page.wait_for_function(
        "(count) => document.querySelectorAll("
        "\"sdoc-markdown-editor img[src*='diagram_']\").length > count",
        arg=len(before),
    )
    page.wait_for_timeout(800)
    return [src for src in sources(page) if src not in before][0]


def check_shapes(page: Page, src: str) -> None:
    shapes = vertices(model_of(stored_svg(page, src)))
    check("three shapes are stored", len(shapes) == 3, shapes)
    check("shapes have the same top", len({shape[1] for shape in shapes}) == 1)
    ordered = sorted(shapes)
    gaps = [
        ordered[index + 1][0] - (ordered[index][0] + ordered[index][2])
        for index in range(2)
    ]
    check("gaps are equal", abs(gaps[0] - gaps[1]) < 0.6, gaps)


def check_resize(page: Page, src: str) -> None:
    image = page.locator(f"sdoc-markdown-editor img[src='{src}']")
    svg = stored_svg(page, src)
    width, height, _ = size_of(svg)

    image.click(force=True)
    page.wait_for_selector("[data-testid=diagram-resize]:not([hidden])")
    check("handles show on the selected diagram", True)
    shot(page, "selected")
    drag(page, "se", 80, 40)
    corner_width, corner_height, _ = size_of(stored_svg(page, src))
    check("corner enlarges", corner_width > width and corner_height > height)
    check(
        "corner keeps the proportions",
        abs(corner_width / corner_height - width / height) < 0.05,
    )
    check(
        "model stays after a resize",
        len(vertices(model_of(stored_svg(page, src)))) == 3,
    )

    image.click(force=True)
    drag(page, "e", -60, 0)
    east_width, east_height, free = size_of(stored_svg(page, src))
    check(
        "east changes the width only",
        east_width < corner_width and abs(east_height - corner_height) < 1.5,
    )
    check("free stretch sets preserveAspectRatio none", free)

    image.click(force=True)
    drag(page, "s", 0, 50)
    south_width, south_height, _ = size_of(stored_svg(page, src))
    check(
        "south changes the height only",
        south_height > east_height and abs(south_width - east_width) < 1.5,
    )
    shot(page, "resized")


def check_reopen(page: Page, src: str) -> tuple:
    image = page.locator(f"sdoc-markdown-editor img[src='{src}']")
    width, height, _ = size_of(stored_svg(page, src))

    image.dblclick(force=True)
    page.wait_for_selector(tool("editor"), timeout=8000)
    check("double click opens the diagram", True)
    page.click(tool("shape-triangle"))
    page.click(tool("save"))
    page.wait_for_selector(tool("editor"), state="detached")
    page.wait_for_timeout(1500)
    svg = stored_svg(page, src)
    new_width, new_height, _ = size_of(svg)
    check("the edit adds a shape", len(vertices(model_of(svg))) == 4)
    check(
        "the size the user gave stays",
        new_width >= width - 1 and new_height >= height - 1,
    )

    image.click(force=True)
    page.locator(DIAGRAM_BUTTON).click()
    page.wait_for_selector(tool("editor"), timeout=8000)
    check("selection and button open the diagram", True)
    page.click(tool("cancel"))
    page.wait_for_selector(tool("editor"), state="detached")
    return new_width, new_height


def check_saved(page: Page, src: str, size: tuple) -> None:
    page.locator('[data-testid="form-submit-action"]').click()
    page.wait_for_selector("sdoc-node img[src*='diagram_']")
    shot(page, "document")
    rendered = page.evaluate(
        "(() => { const image = document.querySelector("
        "\"sdoc-node img[src*='diagram_']\"); "
        "return [image.naturalWidth, image.naturalHeight]; })()"
    )
    check(
        "the document shows the size of the file",
        abs(rendered[0] - size[0]) < 2 and abs(rendered[1] - size[1]) < 2,
        rendered,
    )

    open_form(page)
    page.wait_for_timeout(1000)
    check(
        "the saved diagram is in the editor",
        page.locator(f"sdoc-markdown-editor img[src='{src}']").count() == 1,
        src,
    )
    page.locator(f"sdoc-markdown-editor img[src='{src}']").first.dblclick(
        force=True
    )
    page.wait_for_selector(tool("editor"), timeout=8000)
    check("a saved diagram opens by double click", True)
    page.click(tool("cancel"))


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1500, "height": 1000})
    page.on(
        "console",
        lambda message: (
            report("  console", message.type, message.text[:300])
            if message.type == "error"
            else None
        ),
    )
    page.on("pageerror", lambda error: check("no script error", False, error))
    page.on("dialog", lambda dialog: dialog.accept())

    open_form(page)
    source = draw_diagram(page)
    check_shapes(page, source)
    check_resize(page, source)
    final_size = check_reopen(page, source)
    check_saved(page, source, final_size)
    browser.close()

report("FAILED:", FAILED)
sys.exit(1 if FAILED else 0)
