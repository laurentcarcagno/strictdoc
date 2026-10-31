"""
Checks the toolbar of the Markdown editor in a real browser: the tooltips of the
buttons, and the alignment of a paragraph (left, centre, right, justified).

Usage (see README.md):

    SDOC_URL=http://host.docker.internal:5111/sample/document.html \
    SDOC_SHOTS=/work/shots python check_toolbar.py

SDOC_URL is the address of the document screen of the sample. SDOC_SHOTS is an
optional folder for screenshots. The exit code is 1 when a check fails.
"""

import os
import sys
from typing import List

from playwright.sync_api import Page, sync_playwright

URL = os.environ["SDOC_URL"]
SHOTS = os.environ.get("SDOC_SHOTS")
FAILED: List[str] = []

EDITOR = "sdoc-markdown-editor[data-ready=true] .ProseMirror"
PARAGRAPH = f"{EDITOR} > p"
BUTTONS = ".milkdown-top-bar .top-bar-item"
ALIGNED = "sdoc-node p[style*='text-align']"


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


def open_form(page: Page) -> None:
    page.goto(URL)
    page.locator("sdoc-node").first.hover()
    page.locator('[data-testid="node-edit-action"]').first.click(force=True)
    page.wait_for_selector(EDITOR)
    page.wait_for_timeout(500)


def tooltip_of(page: Page, selector: str, index: int = 0) -> str:
    """The text of the bubble after hovering a button, '' when none shows."""
    page.mouse.move(5, 5)
    page.wait_for_timeout(80)
    page.locator(selector).nth(index).hover()
    try:
        page.wait_for_selector(".sdoc-tooltip:not([hidden])", timeout=1500)
    except Exception:  # noqa: BLE001
        return ""
    return page.locator(".sdoc-tooltip").inner_text()


def check_tooltips(page: Page) -> None:
    count = page.locator(BUTTONS).count()
    named = page.locator(BUTTONS).evaluate_all(
        "buttons => buttons.every(button => button.getAttribute('aria-label'))"
    )
    check("the buttons are named before any hover", count > 0 and named)
    labels = [tooltip_of(page, BUTTONS, index) for index in range(count)]
    report("  top bar labels", labels)
    check(
        "every button of the top bar has a tooltip",
        count > 0 and all(labels),
        labels,
    )
    check("labels are different", len(set(labels)) == len(labels), labels)
    check(
        "the editor buttons are named",
        {
            "Bold",
            "Italic",
            "Align left",
            "Align centre",
            "Align right",
            "Justify",
            "Diagram",
        }
        <= set(labels),
    )
    check(
        "the heading selector has a tooltip",
        tooltip_of(page, ".top-bar-heading-button") == "Text style",
    )
    shot(page, "tooltip")

    # The bubble goes away with the pointer, and the browser draws no other.
    page.mouse.move(5, 5)
    page.wait_for_timeout(200)
    check(
        "the bubble hides when the pointer leaves",
        page.locator(".sdoc-tooltip:not([hidden])").count() == 0,
    )

    page.locator(BUTTONS).filter(has=page.locator(".sdoc-table-icon")).click()
    page.wait_for_selector("[data-testid=table-bar]")
    bubble = tooltip_of(page, "[data-testid=table-insert]")
    check("the table bar has tooltips", bubble == "Insert a table", bubble)
    check(
        "the table bar keeps no native title",
        page.locator("[data-testid=table-insert]").get_attribute("title")
        is None,
    )
    page.locator(BUTTONS).filter(has=page.locator(".sdoc-table-icon")).click()


def style_of(page: Page, selector: str) -> str:
    return page.eval_on_selector(selector, "element => element.style.textAlign")


def check_alignment(page: Page) -> None:
    page.locator(PARAGRAPH).first.click()
    page.wait_for_timeout(600)
    check(
        "left is the pressed button at first",
        page.locator('.top-bar-item[aria-label="Align left"]')
        .get_attribute("class")
        .count("active")
        == 1,
    )
    for name, label in (
        ("center", "Align centre"),
        ("right", "Align right"),
        ("justify", "Justify"),
    ):
        page.locator(f'.top-bar-item[aria-label="{label}"]').click()
        page.wait_for_timeout(200)
        check(
            f"{name}: the paragraph is aligned",
            style_of(page, PARAGRAPH + ":first-of-type") == name,
        )
        check(
            f"{name}: its button is the pressed one",
            "active"
            in page.locator(
                f'.top-bar-item[aria-label="{label}"]'
            ).get_attribute("class"),
        )
        shot(page, f"align_{name}")

    # Centre again, with a word in bold and a link marker, then save.
    page.locator('.top-bar-item[aria-label="Align centre"]').click()
    word = page.locator(PARAGRAPH).first.locator("strong").first
    check("the paragraph keeps its bold text", word.count() == 1)
    page.locator('[data-testid="form-submit-action"]').click()
    page.wait_for_selector("sdoc-node")
    shot(page, "document")
    aligned = page.locator(ALIGNED)
    check(
        "the document shows the aligned paragraph",
        aligned.count() == 1,
        aligned.count(),
    )
    check(
        "it is centred",
        "center" in (aligned.first.get_attribute("style") or ""),
    )
    check("its bold text is bold", aligned.first.locator("strong").count() == 1)
    check(
        "its link marker stays a link", aligned.first.locator("a").count() >= 1
    )

    # The saved text is read back as an aligned paragraph.
    open_form(page)
    check(
        "centre comes back in the editor",
        style_of(page, PARAGRAPH + ":first-of-type") == "center",
    )
    page.locator(PARAGRAPH).first.click()
    page.wait_for_timeout(300)
    check(
        "its button is pressed",
        "active"
        in page.locator(
            '.top-bar-item[aria-label="Align centre"]'
        ).get_attribute("class"),
    )
    check(
        "it holds the bold text",
        page.locator(PARAGRAPH).first.locator("strong").count() == 1,
    )

    # Back to the left: a plain Markdown paragraph again.
    page.locator(PARAGRAPH).first.click()
    page.locator('.top-bar-item[aria-label="Align left"]').click()
    page.locator('[data-testid="form-submit-action"]').click()
    page.wait_for_selector("sdoc-node")
    check("left writes no HTML paragraph", page.locator(ALIGNED).count() == 0)


def top_button(page: Page, label: str):
    return page.locator(f'.top-bar-item[aria-label="{label}"]')


def horizontal_position(page: Page, selector: str) -> dict:
    """Where an element is inside its container: the gaps on the two sides."""
    return page.evaluate(
        """(selector) => {
          const element = document.querySelector(selector);
          const container = element.closest('.ProseMirror, sdoc-autogen');
          const box = element.getBoundingClientRect();
          const outer = container.getBoundingClientRect();
          const style = getComputedStyle(container);
          const left = outer.left + parseFloat(style.paddingLeft);
          const right = outer.right - parseFloat(style.paddingRight);
          return { left: box.left - left, right: right - box.right,
                   width: box.width, outer: right - left };
        }""",
        selector,
    )


def submit(page: Page) -> None:
    page.locator('[data-testid="form-submit-action"]').click()
    page.wait_for_selector("sdoc-node")
    page.wait_for_timeout(500)


def check_image_alignment(page: Page) -> None:
    open_form(page)
    image = "sdoc-markdown-editor img[src*='diagram_']"
    src = page.locator(image).first.get_attribute("src")
    picture = f"sdoc-markdown-editor img[src='{src}']"

    page.locator(picture).click(force=True)
    page.wait_for_timeout(300)
    check(
        "an image is on the left by default",
        horizontal_position(page, picture)["left"] < 40,
        horizontal_position(page, picture),
    )
    top_button(page, "Align centre").click()
    page.wait_for_timeout(300)
    check(
        "centre: the image block carries the alignment",
        page.locator(".milkdown-image-block[data-align=center]").count() >= 1,
    )
    place = horizontal_position(page, picture)
    check(
        "centre: the image is in the middle",
        abs(place["left"] - place["right"]) < 24,
        place,
    )
    check(
        "centre: its button is the pressed one",
        "active" in top_button(page, "Align centre").get_attribute("class"),
    )
    top_button(page, "Justify").click()
    check(
        "justify does not apply to an image",
        page.locator(".milkdown-image-block[data-align=center]").count() >= 1,
    )
    top_button(page, "Align right").click()
    page.wait_for_timeout(300)
    place = horizontal_position(page, picture)
    check("right: the image is on the right", place["right"] < 40, place)
    shot(page, "image_right")
    submit(page)

    rendered = f"sdoc-node p[style*='right'] img[src='{src}']"
    check(
        "the document shows the image aligned",
        page.locator(rendered).count() == 1,
    )
    place = horizontal_position(page, rendered)
    check("it is on the right in the document", place["right"] < 40, place)

    open_form(page)
    check(
        "the alignment comes back in the editor",
        page.locator(
            f".milkdown-image-block[data-align=right] img[src='{src}']"
        ).count()
        == 1,
    )
    page.locator(picture).click(force=True)
    top_button(page, "Align left").click()
    submit(page)
    check(
        "left writes the image as plain Markdown again",
        page.locator(f"sdoc-node p[style] img[src='{src}']").count() == 0,
    )
    check(
        "the image is still there",
        page.locator(f"sdoc-node img[src='{src}']").count() == 1,
    )


def check_table_alignment(page: Page) -> None:
    open_form(page)
    table = "sdoc-markdown-editor .ProseMirror table"
    page.locator(f"{table} td").first.click()
    page.wait_for_timeout(300)
    full = horizontal_position(page, table)
    check(
        "a table has the full width by default",
        full["width"] > full["outer"] - 8,
        full,
    )

    top_button(page, "Align centre").click()
    page.wait_for_timeout(300)
    place = horizontal_position(page, table)
    check(
        "centre: the table is narrower and in the middle",
        place["width"] < full["width"] - 40
        and abs(place["left"] - place["right"]) < 24,
        place,
    )
    check(
        "centre: its button is the pressed one",
        "active" in top_button(page, "Align centre").get_attribute("class"),
    )
    top_button(page, "Align centre").click()
    page.wait_for_timeout(300)
    place = horizontal_position(page, table)
    check(
        "the pressed button puts the table back to the full width",
        place["width"] > full["outer"] - 8
        and page.locator(f"{table}[data-align]").count() == 0,
        place,
    )

    top_button(page, "Align right").click()
    page.wait_for_timeout(300)
    place = horizontal_position(page, table)
    check(
        "right: the table is on the right",
        place["right"] < 40 and place["width"] < full["width"] - 40,
        place,
    )
    shot(page, "table_right")
    submit(page)

    rendered = "sdoc-node table[style*='margin-left: auto']"
    check(
        "the document shows the table aligned",
        page.locator(rendered).count() == 1,
    )
    place = horizontal_position(page, rendered)
    check(
        "it is on the right in the document",
        place["right"] < 40 and place["left"] > 40,
        place,
    )
    check(
        "its cells keep their text", page.locator(f"{rendered} td").count() >= 2
    )

    open_form(page)
    check(
        "the alignment comes back in the editor",
        page.locator(f"{table}[data-align=right]").count() == 1,
    )
    page.locator(f"{table} td").first.click()
    top_button(page, "Align right").click()
    submit(page)
    check(
        "the pressed button writes a pipe table again",
        page.locator("sdoc-node table[style]").count() == 0
        and page.locator("sdoc-node table").count() >= 1,
    )


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

    open_form(page)
    check_tooltips(page)
    check_alignment(page)
    check_image_alignment(page)
    check_table_alignment(page)
    browser.close()

report("FAILED:", FAILED)
sys.exit(1 if FAILED else 0)
