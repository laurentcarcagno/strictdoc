import pytest
from docutils.parsers.rst import directives, roles

from strictdoc.backend.rst.rst_to_markdown import RstToMarkdownConverter


def _convert(rst: str, base_dir: str = "") -> str:
    return RstToMarkdownConverter(base_dir=base_dir).convert(rst).markdown


def test_001_inline_markup():
    assert (
        _convert("A *word*, a **strong** one and ``code``.")
        == "A *word*, a **strong** one and `code`.\n"
    )


def test_002_links():
    markdown = _convert(
        "See `the site <https://example.com/a>`_, http://example.org/x and "
        "mail@example.com."
    )

    assert markdown == (
        "See [the site](https://example.com/a), <http://example.org/x> and "
        "<mail@example.com>.\n"
    )


def test_003_the_markers_of_strictdoc_are_kept_as_they_are():
    markdown = _convert(
        "Needs [LINK: REQ-1], see *[LINK: REQ-2]* too.\n\n"
        '[ANCHOR: ANCHOR-1, "Title"]'
    )

    assert "[LINK: REQ-1]" in markdown
    assert "*[LINK: REQ-2]*" in markdown
    assert '[ANCHOR: ANCHOR-1, "Title"]' in markdown
    assert "\\[" not in markdown


@pytest.mark.parametrize(
    ("rst", "expected"),
    [
        ("It costs $5 and 3 * 4 < 5.", "It costs \\$5 and 3 \\* 4 \\< 5."),
        ("A snake_case_name and _lead.", "A snake_case_name and \\_lead."),
        ("A [bracket] text.", "A \\[bracket\\] text."),
        ("1\\) first", "1\\) first"),
        ("Two ~~ tildes.", "Two \\~\\~ tildes."),
    ],
)
def test_004_special_characters_are_escaped(rst, expected):
    assert _convert(rst).strip() == expected


def test_005_bullet_and_numbered_lists_nest():
    markdown = _convert(
        "- one\n- two\n\n  - nested a\n  - nested b\n- three\n\n"
        "1. first\n2. second\n"
    )

    assert markdown == (
        "- one\n- two\n  - nested a\n  - nested b\n- three\n\n"
        "1. first\n2. second\n"
    )


def test_006_alphabetic_lists_keep_their_labels():
    result = RstToMarkdownConverter().convert("a) first\nb) second\n")

    assert result.markdown == "a\\) first\n\nb\\) second\n"
    assert any("loweralpha" in warning_ for warning_ in result.warnings)


@pytest.mark.parametrize(
    ("directive", "kind", "title"),
    [
        ("note", "note", "Note"),
        ("warning", "warning", "Warning"),
        ("tip", "tip", "Tip"),
        ("important", "important", "Important"),
        ("caution", "caution", "Caution"),
        ("danger", "danger", "Danger"),
        ("attention", "attention", "Attention"),
        ("hint", "hint", "Hint"),
        ("error", "error", "Error"),
    ],
)
def test_007_admonitions_are_html_boxes(directive, kind, title):
    markdown = _convert(f".. {directive}::\n\n    Text in *Markdown*.\n")

    assert markdown == (
        f'<div class="sdoc-admonition sdoc-{kind}" role="note">\n'
        f'<p class="sdoc-admonition-title">{title}</p>\n\n'
        "Text in *Markdown*.\n\n</div>\n"
    )


def test_008_a_generic_admonition_keeps_its_title():
    markdown = _convert(".. admonition:: My title\n\n    Body.\n")

    assert markdown == (
        '<div class="sdoc-admonition" role="note">\n'
        '<p class="sdoc-admonition-title">My title</p>\n\nBody.\n\n</div>\n'
    )


def test_009_code_blocks_are_fences_with_their_language():
    markdown = _convert(
        ".. code:: python\n\n    print(1)\n\n"
        ".. code-block:: text\n\n    a ``` b\n\n"
        "Literal::\n\n    plain\n"
    )

    assert "```python\nprint(1)\n```" in markdown
    assert "````text\na ``` b\n````" in markdown
    assert "Literal:\n\n```\nplain\n```" in markdown


def test_010_tables_are_html_with_header_rows_and_spans():
    markdown = _convert(
        ".. list-table::\n   :header-rows: 1\n\n"
        "   * - A\n     - B\n"
        "   * - ``x``\n     - 2 < 3\n"
    )

    assert markdown == (
        "<table>\n<thead>\n<tr><th>A</th><th>B</th></tr>\n</thead>\n"
        "<tbody>\n<tr><td><code>x</code></td><td>2 &lt; 3</td></tr>\n"
        "</tbody>\n</table>\n"
    )


def test_011_grid_tables_keep_column_and_row_spans():
    markdown = _convert(
        "+---+---+\n| A | B |\n+===+===+\n| C     |\n+---+---+\n"
    )

    assert '<td colspan="2">C</td>' in markdown
    assert "<th>A</th><th>B</th>" in markdown


def test_012_csv_tables_are_html_tables():
    markdown = _convert(".. csv-table::\n   :header: a, b\n\n   1, 2\n")

    assert "<th>a</th><th>b</th>" in markdown
    assert "<td>1</td><td>2</td>" in markdown


def test_013_math_blocks_and_references_use_numbers():
    converter = RstToMarkdownConverter()

    result = converter.convert(
        ".. math::\n   :label: first\n\n   E = mc^2\n\n"
        "See :eq:`first` and :math:`a^2`.\n"
    )

    assert result.markdown == (
        "$$\nE = mc^2 \\tag{1}\n$$\n\nSee (1) and $a^2$.\n"
    )


def test_014_a_reference_before_its_label_is_numbered_on_the_second_pass():
    converter = RstToMarkdownConverter()
    texts = [
        "Look at :eq:`later`.",
        ".. math::\n   :label: later\n\n   x = 1\n",
    ]

    for text_ in texts:
        converter.convert(text_)
    markdown = converter.convert(texts[0]).markdown

    assert markdown == "Look at (1).\n"


def test_015_images(tmp_path):
    (tmp_path / "diagram.svg").write_text("<svg/>")
    (tmp_path / "diagram.png").write_bytes(b"")
    (tmp_path / "photo.png").write_bytes(b"")

    markdown = _convert(
        ".. image:: diagram.*\n\n"
        ".. image:: photo.png\n   :alt: A photo\n   :width: 50%\n\n"
        ".. image:: photo.png\n   :align: center\n",
        str(tmp_path),
    )

    assert "![](diagram.svg)" in markdown
    assert '<img src="photo.png" alt="A photo" width="50%" />' in markdown
    assert (
        '<p style="text-align: center"><img src="photo.png" alt="" />'
        in markdown
    )


def test_016_a_wildcard_without_a_file_is_kept_with_a_warning(tmp_path):
    result = RstToMarkdownConverter(str(tmp_path)).convert(
        ".. image:: missing.*\n"
    )

    assert "![](missing.*)" in result.markdown
    assert any("missing.*" in warning_ for warning_ in result.warnings)


def test_017_raw_html_is_kept_and_other_raw_targets_are_dropped():
    result = RstToMarkdownConverter().convert(
        '.. raw:: html\n\n    <pre class="mermaid">\n    A --> B\n    </pre>\n\n'
        ".. raw:: latex\n\n    \\newpage\n"
    )

    assert result.markdown == '<pre class="mermaid">\nA --> B\n</pre>\n'
    assert any("latex" in warning_ for warning_ in result.warnings)


def test_018_roles_for_sub_and_superscripts():
    assert (
        _convert("H\\ :sub:`2`\\ O and mc\\ :sup:`2`.")
        == "H<sub>2</sub>O and mc<sup>2</sup>.\n"
    )


def test_019_definition_lists_are_dl():
    assert _convert("Term\n    The *definition*.\n") == (
        "<dl><dt>Term</dt><dd>The <em>definition</em>.</dd></dl>\n"
    )


def test_020_quotes_transitions_and_line_blocks():
    markdown = _convert(
        "    A quote.\n\n----------\n\n| line one\n| line two\n"
    )

    assert markdown == "> A quote.\n\n---\n\nline one\\\nline two\n"


def test_021_field_lists_are_bullets():
    assert _convert(":Author: Anna\n:Version: 2\n") == (
        "- **Author:** Anna\n- **Version:** 2\n"
    )


def test_022_comments_and_the_header_of_a_review_comment():
    markdown = _convert(
        ".. sdoc-comment: id=c1 author=anna status=open\n\nThe text.\n"
    )

    assert markdown == (
        "<!-- sdoc-comment id=c1 author=anna status=open -->\n\nThe text.\n"
    )
    assert (
        _convert(".. a plain -- comment\n") == "<!-- a plain - - comment -->\n"
    )


def test_023_an_unknown_directive_becomes_a_comment_with_a_warning():
    result = RstToMarkdownConverter().convert(
        ".. unknown-directive:: foo\n\n    body\n"
    )

    assert result.markdown.startswith("<!-- .. unknown-directive:: foo")
    assert any("Unknown directive" in warning_ for warning_ in result.warnings)


def test_024_a_line_that_starts_with_the_terminator_is_indented():
    result = RstToMarkdownConverter().convert(
        ".. code:: text\n\n    STATEMENT: >>>\n    Text\n    <<<\n"
    )

    assert "\n <<<\n" in result.markdown
    assert not any(
        line_.startswith("<<<") for line_ in result.markdown.split("\n")
    )
    assert any("<<<" in warning_ for warning_ in result.warnings)


def test_025_section_titles_become_headings():
    assert _convert("Title\n=====\n\nBody.\n\nSub\n---\n\nMore.\n") == (
        "# Title\n\nBody.\n\n## Sub\n\nMore.\n"
    )


def test_026_the_docutils_registry_is_left_as_it_was():
    directives_before = set(directives._directives)
    roles_before = set(roles._roles)

    _convert(".. math::\n\n   x\n\n:eq:`a`")

    assert set(directives._directives) == directives_before
    assert set(roles._roles) == roles_before


def test_027_the_words_of_the_rst_are_the_words_of_the_markdown():
    converter = RstToMarkdownConverter()
    rst = ".. note::\n\n    A *note* with a list:\n\n    - one\n    - two\n"

    converter.convert(rst)

    assert converter.reference_text(rst).split() == [
        "Note",
        "A",
        "note",
        "with",
        "a",
        "list:",
        "one",
        "two",
    ]
