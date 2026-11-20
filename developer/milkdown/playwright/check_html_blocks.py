"""
Checks in a real browser that the Markdown editor keeps the HTML of a field.

Each sample is put in the hidden textarea of a <sdoc-markdown-editor>, as the
form does. The check reads the Markdown that the editor writes when the field
is opened (the text that a saved form would send after any edit), then after an
edit elsewhere in the field. No StrictDoc server is needed: the page loads the
committed bundle, strictdoc/features/milkdown/assets/milkdown/.

Usage (see README.md):

    python check_html_blocks.py

CHROMIUM is an optional path to the browser, when the Playwright default is not
installed. The exit code is 1 when a check fails.
"""

import http.server
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Dict, List

from playwright.sync_api import Page, sync_playwright

HERE = Path(__file__).resolve().parent
BUNDLE = HERE.parents[2] / "strictdoc/features/milkdown/assets/milkdown"
FAILED: List[str] = []

# The Markdown of a sample, and what the editor writes when it differs. The
# editor always ends the text with a new line, which the check ignores.
SAMPLES: Dict[str, str] = {
    "div_class_with_markdown": (
        'Before.\n\n<div class="sdoc-admonition sdoc-note" role="note">\n'
        '<p class="sdoc-admonition-title">Note</p>\n\n'
        "Text in **Markdown**.\n\n</div>\n\nAfter."
    ),
    "div_class_one_line": (
        'Before.\n\n<div class="sdoc-note">A plain text note.</div>\n\nAfter.'
    ),
    "div_nested_html_only": (
        'Before.\n\n<div class="x"><p class="t">Title</p><p>Body</p></div>'
        "\n\nAfter."
    ),
    "dl": (
        "Before.\n\n<dl><dt>Term</dt><dd>Definition</dd>"
        "<dt>Other</dt><dd>Text</dd></dl>\n\nAfter."
    ),
    "dl_multiline": (
        "Before.\n\n<dl>\n<dt>Term</dt>\n<dd>Definition</dd>\n</dl>\n\nAfter."
    ),
    "sup_sub_inline": "Water is H<sub>2</sub>O and E = mc<sup>2</sup>.",
    "aside": (
        'Before.\n\n<aside class="sdoc-sidebar">\nSide text.\n</aside>'
        "\n\nAfter."
    ),
    "html_comment_block": "Before.\n\n<!-- a comment -->\n\nAfter.",
    "html_comment_sdoc": "Before.\n\n<!-- sdoc-comment: author=x -->\n\nAfter.",
    "html_comment_inline": "Text <!-- inline comment --> more text.",
    "details": (
        "<details>\n<summary>More</summary>\n\nHidden **text**.\n\n</details>"
    ),
    "span_class_inline": 'A <span class="sdoc-x">marked</span> word.',
    "kbd_mark_inline": "Press <kbd>Ctrl</kbd> and <mark>highlight</mark>.",
    "br_inline": "Line one<br>line two<br/>line three.",
    "figure": (
        '<figure><img src="a.png" alt="a"><figcaption>Caption</figcaption>'
        "</figure>"
    ),
    "unknown_table": (
        '<table class="x"><tr><td><ul><li>a</li></ul></td></tr></table>'
    ),
    "sdoc_link_in_div": (
        '<div class="sdoc-admonition sdoc-warning">\n'
        '<p class="sdoc-admonition-title">Warning</p>\n\n'
        "See [LINK: REQ-1].\n\n</div>"
    ),
    "equation_tag": "$$\nE = mc^2 \\tag{1}\n$$",
    "anchor_and_link": 'Text [LINK: fn-1].\n\n[ANCHOR: fn-1, "1"]',
}

# What the editor changes outside the HTML: the Markdown that it parses and
# writes again. The HTML itself is never changed.
EXPECTED_DIFFERENT: Dict[str, str] = {
    "raw_block_with_blank_lines_inside": (
        '<div class="box">\nfirst\n\n* item a\n* item b\n\n'
        "```python\nprint(1)\n```\n\n</div>"
    ),
    "sup_with_brackets": "A note<sup>\\[1]</sup>.",
}
SAMPLES_DIFFERENT: Dict[str, str] = {
    "raw_block_with_blank_lines_inside": (
        '<div class="box">\nfirst\n\n- item a\n- item b\n\n'
        "```python\nprint(1)\n```\n\n</div>"
    ),
    "sup_with_brackets": "A note<sup>[1]</sup>.",
}

PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<link rel="stylesheet" href="milkdown.css"></head>
<body><div id="stage"></div>
<script src="milkdown.js"></script></body></html>
"""

SCRIPT = """
async (samples) => {
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const results = {};
  for (const [name, markdown] of Object.entries(samples)) {
    const wrapper = document.createElement('div');
    const editor = document.createElement('sdoc-markdown-editor');
    const textarea = document.createElement('textarea');
    textarea.hidden = true;
    textarea.value = markdown;
    wrapper.append(editor, textarea);
    document.getElementById('stage').append(wrapper);
    for (let i = 0; i < 100 && editor.dataset.ready !== 'true'; i++) {
      await wait(50);
    }
    const result = { ready: editor.dataset.ready === 'true' };
    if (result.ready) {
      result.opened = editor.getMarkdown();
      editor.replaceRange(null, null, result.opened + '\\n\\nEdited.');
      // Milkdown reports a change about 200 ms after it.
      await wait(500);
      result.edited = editor.getMarkdown();
      result.sent = textarea.value;
      result.html_nodes = wrapper.querySelectorAll(
        '.ProseMirror [data-type="html"]'
      ).length;
      const count = (part) => wrapper.querySelectorAll('.sdoc-adm-' + part).length;
      result.boxes = { open: count('open'), body: count('body'), close: count('close') };
      result.title = wrapper.querySelector('.sdoc-adm-open')?.dataset.sdocTitle ?? null;
    }
    results[name] = result;
  }
  return results;
}
"""


def report(*values: object) -> None:
    print(*values, flush=True)  # noqa: T201


def check(name: str, condition: bool, detail: object = "") -> None:
    report(("PASS " if condition else "FAIL ") + name, detail)
    if not condition:
        FAILED.append(name)


def serve(folder: str) -> http.server.ThreadingHTTPServer:
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=folder, **kwargs)  # type: ignore[arg-type]

        def log_message(self, format_: str, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def insert_with_slash_menu(page: Page, port: int) -> Dict[str, object]:
    """Types "/" in an empty field and chooses "Note box" in the menu."""
    page.goto(f"http://127.0.0.1:{port}/index.html")
    page.evaluate(
        """() => {
          const wrapper = document.createElement('div');
          const editor = document.createElement('sdoc-markdown-editor');
          const textarea = document.createElement('textarea');
          textarea.hidden = true;
          wrapper.append(editor, textarea);
          document.getElementById('stage').append(wrapper);
        }"""
    )
    page.wait_for_selector("sdoc-markdown-editor[data-ready=true] .ProseMirror")
    page.click("sdoc-markdown-editor .ProseMirror")
    page.keyboard.type("/")
    page.wait_for_selector(".milkdown-slash-menu")
    page.locator(".milkdown-slash-menu li", has_text="Note box").click()
    page.wait_for_selector(".sdoc-adm-open")
    shot = os.environ.get("SDOC_SHOT")
    if shot:
        page.screenshot(path=shot)
    return {
        "markdown": page.evaluate(
            "document.querySelector('sdoc-markdown-editor').getMarkdown()"
        ),
        "boxes": page.evaluate(
            "[...document.querySelectorAll('.sdoc-adm')].map(e => e.className)"
        ),
    }


def main() -> int:
    samples = dict(SAMPLES)
    samples.update(SAMPLES_DIFFERENT)
    with tempfile.TemporaryDirectory() as folder:
        for file_ in BUNDLE.iterdir():
            shutil.copy(file_, folder)
        (Path(folder) / "index.html").write_text(PAGE, encoding="utf8")
        server = serve(folder)
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=os.environ.get("CHROMIUM") or None
                )
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{server.server_port}/index.html")
                results = page.evaluate(SCRIPT, samples)
                inserted = insert_with_slash_menu(page, server.server_port)
                browser.close()
        finally:
            server.shutdown()

    for name, markdown in samples.items():
        result = results[name]
        expected = EXPECTED_DIFFERENT.get(name, markdown)
        check(f"{name}: the editor is ready", result["ready"])
        if not result["ready"]:
            continue
        opened = result["opened"].rstrip("\n")
        check(f"{name}: opened as written", opened == expected, opened)
        check(
            f"{name}: kept after an edit",
            result["edited"].rstrip("\n") == opened + "\n\nEdited.",
        )
        check(
            f"{name}: the form sends the edited text",
            result["sent"] == result["edited"],
        )
    for name in ("div_class_with_markdown", "sdoc_link_in_div"):
        boxes = results[name]["boxes"]
        check(
            f"{name}: drawn as one box",
            boxes["open"] == 1 and boxes["close"] == 1 and boxes["body"] >= 1,
            boxes,
        )
    check(
        "the title of the box comes from the HTML",
        results["div_class_with_markdown"]["title"] == "Note"
        and results["sdoc_link_in_div"]["title"] == "Warning",
        results["div_class_with_markdown"]["title"],
    )
    check(
        "a div without the admonition class is not a box",
        results["div_class_one_line"]["boxes"]["open"] == 0,
    )
    check(
        "the slash menu inserts a note box, written as HTML",
        inserted["markdown"]
        == (
            '<div class="sdoc-admonition sdoc-note" role="note">\n'
            '<p class="sdoc-admonition-title">Note</p>\n\nText.\n\n</div>\n'
        ),
        inserted["markdown"],
    )
    check("the inserted box is drawn", len(inserted["boxes"]) >= 3, inserted)
    report(json.dumps({"failed": FAILED}))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
