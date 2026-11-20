from html import escape
from typing import Optional, Sequence, Tuple


def key_value_table(
    rows: Sequence[Tuple[str, object]], caption: Optional[str] = None
) -> str:
    """
    A two-column HTML table for a Markdown field: the key in bold, then the
    value. There is no empty line inside, so Markdown keeps it as one block.
    """
    lines = ["<table>"]
    if caption is not None:
        lines.append(f"<caption>{escape(caption)}</caption>")
    lines.append("<tbody>")
    for key_, value_ in rows:
        lines.append(
            f"<tr><td><strong>{escape(key_)}</strong></td>\n"
            f"<td>{escape(str(value_))}</td></tr>"
        )
    lines.extend(["</tbody>", "</table>"])
    return "\n".join(lines) + "\n"
