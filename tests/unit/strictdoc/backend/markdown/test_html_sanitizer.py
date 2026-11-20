"""
@relation(SDOC-SRS-24, scope=file)
"""

import pytest

from strictdoc.backend.markdown.html_sanitizer import sanitize_html_fragment
from strictdoc.backend.markdown.markdown_to_html_fragment_writer import (
    MarkdownToHtmlFragmentWriter,
)


@pytest.mark.parametrize(
    "html",
    [
        '<div class="sdoc-admonition sdoc-note" role="note">',
        '<p class="sdoc-admonition-title">Note</p>',
        "<dl><dt>Term</dt><dd>Definition</dd></dl>",
        "H<sub>2</sub>O and mc<sup>2</sup>",
        "<br>",
        '<img src="_assets/a.png" alt="a" width="50">',
        '<a href="https://example.com/a?b=1&amp;c=2">link</a>',
        '<a href="#SECTION-1">anchor</a>',
        '<td colspan="2" rowspan="3" style="text-align: center">cell</td>',
        "<!-- a comment -->",
        "<details><summary>More</summary></details>",
        '<pre class="mermaid">\ngraph TD\nA --> B(Preview)\n</pre>',
        '<pre class="plantuml">\n@startuml\nAlice -> Bob: Hello\n@enduml\n</pre>',
    ],
)
def test_001_allowed_html_is_kept(html):
    assert sanitize_html_fragment(html) == html


def test_002_script_is_shown_as_text():
    assert (
        sanitize_html_fragment("<script>alert(1)</script>")
        == "&lt;script&gt;alert(1)&lt;/script&gt;"
    )


@pytest.mark.parametrize(
    "tag",
    ["iframe", "object", "embed", "form", "input", "link", "meta", "style"],
)
def test_003_active_elements_are_shown_as_text(tag):
    assert sanitize_html_fragment(f"<{tag} x>") == f"&lt;{tag} x&gt;"


def test_004_event_attributes_are_removed():
    assert (
        sanitize_html_fragment('<img src="a.png" onerror="alert(1)">')
        == '<img src="a.png">'
    )
    assert (
        sanitize_html_fragment('<div onclick="x()" class="a">')
        == '<div class="a">'
    )


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        "JaVaScRiPt:alert(1)",
        " javascript:alert(1)",
        "java\tscript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "vbscript:x",
    ],
)
def test_005_dangerous_urls_are_removed(href):
    assert sanitize_html_fragment(f'<a href="{href}">x</a>') == "<a>x</a>"


def test_006_data_image_is_allowed_for_img_src_only():
    image = "data:image/png;base64,iVBORw0KGgo="
    assert (
        sanitize_html_fragment(f'<img src="{image}">') == f'<img src="{image}">'
    )
    assert sanitize_html_fragment(f'<a href="{image}">x</a>') == "<a>x</a>"
    svg = "data:image/svg+xml;base64,PHN2Zz4="
    assert sanitize_html_fragment(f'<img src="{svg}">') == "<img>"


def test_007_style_keeps_the_listed_properties_only():
    assert (
        sanitize_html_fragment(
            '<p style="text-align: center; position: fixed; '
            'background-color: #ff0000">'
        )
        == '<p style="text-align: center; background-color: #ff0000">'
    )
    assert (
        sanitize_html_fragment(
            '<p style="background-color: url(javascript:x)">'
        )
        == "<p>"
    )


def test_008_incomplete_tag_does_not_leave_a_raw_angle_bracket():
    assert "<" not in sanitize_html_fragment('<div class="x"').replace(
        "&lt;", ""
    )


def test_009_markdown_writer_sanitizes_html_blocks_and_inline_html():
    html = MarkdownToHtmlFragmentWriter().write(
        "<script>alert(1)</script>\n\nText <b onclick=x>b</b> and "
        '<span class="ok">ok</span>.\n'
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "onclick" not in html
    assert '<span class="ok">ok</span>' in html


def test_010_markdown_writer_keeps_markdown_inside_an_admonition():
    html = MarkdownToHtmlFragmentWriter().write(
        '<div class="sdoc-admonition sdoc-note" role="note">\n'
        '<p class="sdoc-admonition-title">Note</p>\n\n'
        "Text in **Markdown**.\n\n</div>\n"
    )
    assert '<div class="sdoc-admonition sdoc-note" role="note">' in html
    assert "<strong>Markdown</strong>" in html
    assert "</div>" in html
