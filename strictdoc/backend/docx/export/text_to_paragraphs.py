"""
Picks the converter that matches the markup of the SDoc document.
"""

from typing import List

from strictdoc.backend.docx.docx_profile import MARKUP_MARKDOWN
from strictdoc.backend.docx.export.markdown_to_paragraphs import (
    markdown_to_paragraphs,
)
from strictdoc.backend.docx.export.rst_to_paragraphs import (
    ExportParagraph,
    rst_to_paragraphs,
)


def text_to_paragraphs(
    text: str, markup: str, base_dir: str = ""
) -> List[ExportParagraph]:
    """base_dir is where the relative paths of the images start."""
    if markup == MARKUP_MARKDOWN:
        return markdown_to_paragraphs(text, base_dir)
    return rst_to_paragraphs(text)
