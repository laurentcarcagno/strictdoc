import pytest

from strictdoc.backend.sdoc.residual_rst import find_residual_rst


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (".. note::\n\n    Text.\n", "the directive '.. note::'"),
        ("A ``literal`` here.", "a literal between double backticks"),
        ("+---+---+\n| a | b |\n+---+---+\n", "a table drawn with + and -"),
        ("Title\n~~~~~\n\nText.", "a title underlined with ~"),
    ],
)
def test_001_rst_in_a_markdown_field_is_found(text, reason):
    assert find_residual_rst(text) == reason


@pytest.mark.parametrize(
    "text",
    [
        "Plain **Markdown** with `code` and a [link](x).",
        "Setext heading\n==============\n\nBody.",
        "Another\n-------\n\nBody.",
        "```text\n.. note::\n``literal``\n```\n",
        "``` `` ```: a code span that holds backticks.",
        "A table:\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n",
        "<table>\n<tr><td>a</td></tr>\n</table>",
        "Dots: .. and ... are fine.",
    ],
)
def test_002_markdown_is_left_alone(text):
    assert find_residual_rst(text) is None
