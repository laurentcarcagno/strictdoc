"""
The Word paragraphs of the text of an SDoc node. The text is Markdown (an HTML
document is read the same way: its tags are dropped).
"""

from typing import List

from strictdoc.backend.docx.export.markdown_to_paragraphs import (
    markdown_to_paragraphs,
)
from strictdoc.backend.docx.export.paragraph_model import ExportParagraph


def text_to_paragraphs(text: str, base_dir: str = "") -> List[ExportParagraph]:
    """base_dir is where the relative paths of the images start."""
    return markdown_to_paragraphs(text, base_dir)
