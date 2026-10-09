"""
The mapping profile that tells StrictDoc how a Word document is organized.

Every organization structures its Word requirements differently. A profile
names the paragraph styles that are headings and describes the table layout of
one requirement. A profile is a Python file that defines
``create_profile() -> DocxProfile``, like ``strictdoc_config.py``.
"""

import importlib.util
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from strictdoc.helpers.exception import StrictDocException

FREE_TEXT_TEXT = "text"
FREE_TEXT_DROP = "drop"


@dataclass
class DocxRequirementTable:
    """
    Layout of one requirement, written as a table:

    - The first paragraph of the first row has the style ``id_style`` and
      holds the requirement ID, which becomes the UID.
    - The next row holds the title, in a paragraph of style ``title_style``.
    - A row with two cells whose first cell is a key of ``meta_rows`` holds
      the value of the field that the key maps to.
    - A row with one cell that starts with ``note_label`` holds the note.
    - Any other row with one cell holds the statement.
    """

    id_style: str
    title_style: Optional[str] = None
    # Label in the first cell -> SDoc field name, in output order.
    meta_rows: Dict[str, str] = field(default_factory=dict)
    text_style: Optional[str] = None
    note_label: Optional[str] = None
    note_field: str = "NOTE"
    # Fields whose values may name other requirements. A name that matches a
    # known UID becomes a Parent relation.
    relation_fields: List[str] = field(default_factory=list)


@dataclass
class DocxProfile:
    # Paragraph style -> depth of the section, starting at 1.
    heading_styles: Dict[str, int] = field(
        default_factory=lambda: {
            "Heading1": 1,
            "Heading2": 2,
            "Heading3": 3,
            "Heading4": 4,
        }
    )
    requirement_table: Optional[DocxRequirementTable] = None
    # "text": keep running paragraphs as TEXT nodes. "drop": count only.
    free_text: str = FREE_TEXT_TEXT
    document_title: Optional[str] = None
    # Paragraphs whose style starts with one of these are skipped (tables of
    # contents and tables of figures hold generated text).
    ignored_style_prefixes: Tuple[str, ...] = ("TOC", "TableofFigures")

    @staticmethod
    def generic() -> "DocxProfile":
        return DocxProfile()

    def validate(self) -> None:
        if self.free_text not in (FREE_TEXT_TEXT, FREE_TEXT_DROP):
            raise StrictDocException(
                f"Invalid free_text value in the profile: '{self.free_text}'."
                f" Use '{FREE_TEXT_TEXT}' or '{FREE_TEXT_DROP}'."
            )
        if self.requirement_table is not None:
            for field_name_ in self.requirement_table.meta_rows.values():
                _validate_field_name(field_name_)
            _validate_field_name(self.requirement_table.note_field)


def load_docx_profile(path: str) -> DocxProfile:
    if not os.path.isfile(path):
        raise StrictDocException(f"Profile file not found: {path}.")
    specification = importlib.util.spec_from_file_location(
        "strictdoc_docx_profile", path
    )
    if specification is None or specification.loader is None:
        raise StrictDocException(f"Could not load the profile: {path}.")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    create_profile = getattr(module, "create_profile", None)
    if create_profile is None:
        raise StrictDocException(
            f"The profile {path} must define create_profile()."
        )
    profile = create_profile()
    if not isinstance(profile, DocxProfile):
        raise StrictDocException(
            f"create_profile() in {path} must return a DocxProfile."
        )
    profile.validate()
    return profile


def _validate_field_name(field_name: str) -> None:
    reserved = ("UID", "TITLE", "STATEMENT", "RELATIONS")
    is_valid = (
        len(field_name) > 0
        and field_name == field_name.upper()
        and field_name.replace("_", "").isalnum()
        and not field_name[0].isdigit()
    )
    if not is_valid or field_name in reserved:
        raise StrictDocException(
            f"Invalid field name in the profile: '{field_name}'. Use upper "
            f"case letters, digits and underscores, other than {reserved}."
        )
