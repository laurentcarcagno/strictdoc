"""
Reads the requirements of an existing SDoc file as text blocks.

A re-import of a Word document must keep what people added to the SDoc file by
hand: extra fields and File relations. This module extracts them from the text
of the existing file. SDoc text is line-based and regular, so a small scanner
is enough, and the blocks keep the exact text of each value.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from strictdoc.backend.docx.docx_profile import DocxRequirementTable

_FIELD_PATTERN = re.compile(r"^([A-Z][A-Z0-9_]*):(?: (.*))?$")
_BLOCK_STARTS = (
    "[REQUIREMENT]",
    "[TEXT]",
    "[COMPOSITE_REQUIREMENT]",
    "[/COMPOSITE_REQUIREMENT]",
    "[[SECTION]]",
    "[[/SECTION]]",
    "[DOCUMENT]",
    "[GRAMMAR]",
)


@dataclass
class SDocRequirementBlock:
    # (field name, value as written in the file), in file order. A multiline
    # value keeps its ">>>" and "<<<" lines.
    fields: List[Tuple[str, str]] = field(default_factory=list)
    # Each relation is its lines, for example ["- TYPE: File", "  VALUE: a.c"].
    file_relations: List[List[str]] = field(default_factory=list)


@dataclass
class CarryOver:
    """What a re-import takes over from the existing SDoc file."""

    blocks: Dict[str, SDocRequirementBlock] = field(default_factory=dict)
    # (field name, grammar lines) of the String fields that the profile does
    # not own.
    extra_grammar_fields: List[Tuple[str, List[str]]] = field(
        default_factory=list
    )


def owned_field_names(layout: DocxRequirementTable) -> List[str]:
    names = ["UID"] + list(layout.meta_rows.values()) + ["TITLE", "STATEMENT"]
    if layout.note_label is not None:
        names.append(layout.note_field)
    return names


def build_carry_over(sdoc_text: str, layout: DocxRequirementTable) -> CarryOver:
    return CarryOver(
        blocks=parse_requirement_blocks(sdoc_text),
        extra_grammar_fields=parse_grammar_extra_fields(
            sdoc_text, owned_field_names(layout)
        ),
    )


def parse_requirement_blocks(sdoc_text: str) -> Dict[str, SDocRequirementBlock]:
    blocks: Dict[str, SDocRequirementBlock] = {}
    lines = sdoc_text.split("\n")
    index = 0
    while index < len(lines):
        if lines[index] != "[REQUIREMENT]":
            index += 1
            continue
        block, index = _read_block(lines, index + 1)
        uid = dict(block.fields).get("UID")
        if uid is not None:
            blocks[uid] = block
    return blocks


def _read_block(
    lines: List[str], index: int
) -> Tuple[SDocRequirementBlock, int]:
    block = SDocRequirementBlock()
    while index < len(lines) and lines[index] not in _BLOCK_STARTS:
        line = lines[index]
        match = _FIELD_PATTERN.match(line)
        if match is None:
            index += 1
            continue
        name, value = match.group(1), match.group(2) or ""
        if name == "RELATIONS":
            index = _read_relations(lines, index + 1, block)
        elif value == ">>>":
            index += 1
            value_lines = [">>>"]
            while index < len(lines) and lines[index] != "<<<":
                value_lines.append(lines[index])
                index += 1
            value_lines.append("<<<")
            index += 1
            block.fields.append((name, "\n".join(value_lines)))
        else:
            block.fields.append((name, value))
            index += 1
    return block, index


def _read_relations(
    lines: List[str], index: int, block: SDocRequirementBlock
) -> int:
    relations: List[List[str]] = []
    while index < len(lines):
        line = lines[index]
        if line.startswith("- "):
            relations.append([line])
        elif line.startswith("  ") and len(relations) > 0:
            relations[-1].append(line)
        else:
            break
        index += 1
    block.file_relations = [
        relation_ for relation_ in relations if relation_[0] == "- TYPE: File"
    ]
    return index


def parse_grammar_extra_fields(
    sdoc_text: str, owned_names: List[str]
) -> List[Tuple[str, List[str]]]:
    lines = sdoc_text.split("\n")
    try:
        element_index = lines.index("- TAG: REQUIREMENT")
    except ValueError:
        return []

    items: List[List[str]] = []
    for line_ in lines[element_index + 1 :]:
        if line_.startswith("- TAG:") or line_ == "  RELATIONS:":
            break
        if line_.startswith("  - TITLE: "):
            items.append([line_])
        elif line_.startswith("    ") and len(items) > 0:
            items[-1].append(line_)

    extras: List[Tuple[str, List[str]]] = []
    for item_ in items:
        name = item_[0][len("  - TITLE: ") :].strip()
        is_string = "    TYPE: String" in item_
        # COMMENT is part of every generated grammar, so it is not an extra.
        if (
            is_string
            and name not in owned_names
            and name not in ("RELATIONS", "COMMENT")
        ):
            extras.append((name, item_))
    return extras
