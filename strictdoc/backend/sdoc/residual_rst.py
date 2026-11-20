import re
from typing import List, Optional

# What a field written in RST has and Markdown has not. The code blocks are
# skipped, and so are the underlines that Markdown reads as headings (= and -).
_DIRECTIVE = re.compile(r"^\s*\.\. [A-Za-z0-9_-]+::")
_DOUBLE_BACKTICK_LITERAL = re.compile(
    r"(?<!`)``(?![\s`])[^`\n]+(?<![\s`])``(?!`)"
)
_GRID_TABLE_BORDER = re.compile(r"^\s*\+[-=]+(\+[-=]+)+\+\s*$")
_RST_UNDERLINE = re.compile(r"^([~^\"'+#*])\1{2,}\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def find_residual_rst(text: str) -> Optional[str]:
    """
    The first thing in a Markdown field that looks like RST, or None. It is a
    hint for the author: the check is not a parser.
    """
    lines: List[str] = text.split("\n")
    in_fence = False
    for index_, line_ in enumerate(lines):
        # An underline of tildes is also a fence: the text above decides.
        if (
            not in_fence
            and index_ > 0
            and lines[index_ - 1].strip() != ""
            and not _FENCE.match(lines[index_ - 1])
            and _RST_UNDERLINE.match(line_) is not None
            and len(line_.strip()) >= len(lines[index_ - 1].strip()) - 1
        ):
            return "a title underlined with " + line_.strip()[0]
        if _FENCE.match(line_) is not None:
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _DIRECTIVE.match(line_) is not None:
            return f"the directive '{line_.strip()}'"
        if _GRID_TABLE_BORDER.match(line_) is not None:
            return "a table drawn with + and -"
        if _DOUBLE_BACKTICK_LITERAL.search(line_) is not None:
            return "a literal between double backticks"
    return None
