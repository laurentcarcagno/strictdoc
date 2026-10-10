"""
Converts the blocks read from a Word document into an SDoc document.

The converter writes SDoc text and reads it back with the SDoc reader. The
result is a valid document model by construction, and the text is what the
user sees once the document is written to disk.
"""

import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Union

from strictdoc.backend.docx.docx_profile import (
    FREE_TEXT_DROP,
    MARKUP_MARKDOWN,
    MARKUP_RST,
    DocxProfile,
    DocxRequirementTable,
)
from strictdoc.backend.docx.export.docx_comments import (
    comment_fingerprint,
    comment_plain_text,
)
from strictdoc.backend.docx.import_.docx_reader import (
    DocxBlock,
    DocxParagraph,
    DocxTable,
    WordComment,
    _escape_markdown,
    _escape_rst,
)
from strictdoc.backend.docx.import_.sdoc_requirement_blocks import (
    CarryOver,
    owned_field_names,
)
from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.reader import SDReader
from strictdoc.features.comments.model import (
    STATUS_OPEN,
    STATUS_RESOLVED,
    Comment,
    format_comment,
    parse_comment,
)
from strictdoc.features.hierarchy.references import ResolverFunction

REMOVED_SECTION_TITLE = "Not in the Word document"

# Same character set as a UID in the SDoc grammar, without spaces.
_UID_PATTERN = re.compile(r"[\w]+[\w()\-/.:]*")


@dataclass
class DocxImportReport:
    section_count: int = 0
    requirement_count: int = 0
    free_paragraph_count: int = 0
    free_table_count: int = 0
    dropped_paragraph_count: int = 0
    duplicate_uids: List[str] = field(default_factory=list)
    invalid_uids: List[str] = field(default_factory=list)
    # (UID of the requirement, name that looks like a requirement ID but
    # matches no requirement of the document).
    unresolved_links: List[Tuple[str, str]] = field(default_factory=list)
    # Filled when the Word document is merged into an existing SDoc file.
    merged: bool = False
    added_uids: List[str] = field(default_factory=list)
    # UID -> names of the fields whose value changed.
    changed_uids: Dict[str, List[str]] = field(default_factory=dict)
    unchanged_count: int = 0
    # In the SDoc file but no longer in the Word document. They are kept.
    removed_uids: List[str] = field(default_factory=list)
    # Word comments that were not in the SDoc file yet and now are.
    comments_added: int = 0
    # Parent relations written from references to applicable documents.
    references_resolved: int = 0

    def format(self) -> str:
        summary = (
            f"Word import: {self.requirement_count} requirement(s), "
            f"{self.section_count} section(s), "
            f"{self.free_paragraph_count} free paragraph(s), "
            f"{self.free_table_count} other table(s)."
        )
        lines = [summary]
        if self.dropped_paragraph_count > 0:
            lines.append(
                f"  Not imported: {self.dropped_paragraph_count} free "
                f"paragraph(s) (free_text is 'drop')."
            )
        for uid_ in self.duplicate_uids:
            lines.append(f"  Duplicate UID, kept the first only: {uid_}")
        for uid_ in self.invalid_uids:
            lines.append(f"  Invalid UID, requirement imported without: {uid_}")
        for uid_, name_ in self.unresolved_links:
            lines.append(f"  Unresolved link: {uid_} -> {name_}")
        if self.references_resolved > 0:
            lines.append(
                f"  Links to applicable documents: {self.references_resolved}"
            )
        if self.comments_added > 0:
            lines.append(f"  Comments read from Word: {self.comments_added}")
        if self.merged:
            lines.append(
                f"  Merged into the existing file: {len(self.added_uids)} "
                f"added, {len(self.changed_uids)} changed, "
                f"{self.unchanged_count} unchanged, "
                f"{len(self.removed_uids)} not in the Word document."
            )
            for uid_ in self.added_uids:
                lines.append(f"  Added: {uid_}")
            for uid_, names_ in self.changed_uids.items():
                lines.append(f"  Changed: {uid_} ({', '.join(names_)})")
            for uid_ in self.removed_uids:
                lines.append(f"  Kept in '{REMOVED_SECTION_TITLE}': {uid_}")
        return "\n".join(lines)


@dataclass
class _Section:
    level: int
    title: str


@dataclass
class _FreeText:
    paragraphs: List[DocxParagraph]


@dataclass
class DocxRequirement:
    uid: str
    title: str
    fields: Dict[str, str]
    statement_paragraphs: List[DocxParagraph]
    note_paragraphs: List[DocxParagraph]
    # The Word comments that are anchored in the table of the requirement.
    comments: List[WordComment] = field(default_factory=list)


_Item = Union[_Section, _FreeText, DocxTable, DocxRequirement]


class DocxToSDocConverter:
    @staticmethod
    def convert(
        blocks: List[DocxBlock],
        profile: DocxProfile,
        fallback_title: str,
        carry_over: Optional[CarryOver] = None,
        reference_resolver: Optional[ResolverFunction] = None,
    ) -> Tuple[SDocDocument, DocxImportReport]:
        sdoc_text, report = DocxToSDocConverter.build_sdoc_text(
            blocks, profile, fallback_title, carry_over, reference_resolver
        )
        return DocxToSDocConverter.parse(sdoc_text), report

    @staticmethod
    def parse(sdoc_text: str) -> SDocDocument:
        return SDReader().read(sdoc_text)

    @staticmethod
    def build_sdoc_text(
        blocks: List[DocxBlock],
        profile: DocxProfile,
        fallback_title: str,
        carry_over: Optional[CarryOver] = None,
        reference_resolver: Optional[ResolverFunction] = None,
    ) -> Tuple[str, DocxImportReport]:
        """
        With a carry_over (the existing SDoc file), the Word document is
        merged into it: Word owns the profile's fields, the structure and the
        Parent relations; extra fields and File relations are kept.
        """
        report = DocxImportReport()
        if carry_over is not None:
            report.merged = True
        items = _classify_blocks(blocks, profile, report)
        known_uids = _resolve_uids(items, report)
        title = (
            profile.document_title
            if profile.document_title is not None
            else fallback_title
        )
        markup = profile.markup
        header = f"[DOCUMENT]\nTITLE: {_single_line(title)}\n"
        if markup == MARKUP_MARKDOWN:
            header += "OPTIONS:\n  MARKUP: Markdown\n"
        parts: List[str] = [header]
        extra_fields = (
            carry_over.extra_grammar_fields if carry_over is not None else []
        )
        if profile.requirement_table is not None:
            parts.append(_grammar_text(profile.requirement_table, extra_fields))

        open_sections = 0
        for item_ in items:
            if isinstance(item_, _Section):
                while open_sections >= item_.level:
                    parts.append("[[/SECTION]]\n")
                    open_sections -= 1
                parts.append(
                    f"[[SECTION]]\nTITLE: {_single_line(item_.title)}\n"
                )
                open_sections += 1
            elif isinstance(item_, _FreeText):
                parts.append(
                    _text_node(join_paragraphs(item_.paragraphs, markup))
                )
            elif isinstance(item_, DocxTable):
                parts.append(_text_node(_list_table(item_, markup)))
            else:
                assert profile.requirement_table is not None
                parts.append(
                    _requirement_text(
                        item_,
                        profile.requirement_table,
                        known_uids,
                        report,
                        carry_over,
                        markup,
                        reference_resolver,
                    )
                )
        while open_sections > 0:
            parts.append("[[/SECTION]]\n")
            open_sections -= 1
        if carry_over is not None and profile.requirement_table is not None:
            removed_text = _removed_requirements_text(
                profile.requirement_table, known_uids, report, carry_over
            )
            if len(removed_text) > 0:
                parts.append(removed_text)
        return "\n".join(parts), report


def _classify_blocks(
    blocks: List[DocxBlock], profile: DocxProfile, report: DocxImportReport
) -> List[_Item]:
    items: List[_Item] = []
    pending_free: List[DocxParagraph] = []

    def flush_free_text() -> None:
        if len(pending_free) == 0:
            return
        report.free_paragraph_count += len(pending_free)
        if profile.free_text == FREE_TEXT_DROP:
            report.dropped_paragraph_count += len(pending_free)
        else:
            items.append(_FreeText(list(pending_free)))
        pending_free.clear()

    for block_ in blocks:
        if isinstance(block_, DocxParagraph):
            if block_.style.startswith(profile.ignored_style_prefixes):
                continue
            if len(block_.text.strip()) == 0:
                continue
            level = profile.heading_styles.get(block_.style)
            if level is not None:
                flush_free_text()
                report.section_count += 1
                items.append(_Section(level, block_.text.strip()))
            else:
                pending_free.append(block_)
        else:
            flush_free_text()
            if len(block_.rows) == 0:
                # Every row was a tracked change that this mode drops.
                continue
            requirement = read_requirement(block_, profile.requirement_table)
            if requirement is not None:
                report.requirement_count += 1
                items.append(requirement)
            else:
                report.free_table_count += 1
                items.append(block_)
    flush_free_text()
    return items


def read_requirement(
    table: DocxTable, layout: Optional[DocxRequirementTable]
) -> Optional[DocxRequirement]:
    if layout is None or len(table.rows) == 0:
        return None
    first_cell = table.rows[0][0]
    if (
        len(first_cell.paragraphs) == 0
        or first_cell.paragraphs[0].style != layout.id_style
    ):
        return None

    uid = _cell_text(first_cell.paragraphs)
    title = ""
    fields: Dict[str, str] = {}
    statement: List[DocxParagraph] = []
    note: List[DocxParagraph] = []
    for row_ in table.rows[1:]:
        first_paragraphs = row_[0].paragraphs
        if len(first_paragraphs) == 0:
            continue
        label = _cell_text(first_paragraphs)
        if (
            layout.title_style is not None
            and first_paragraphs[0].style == layout.title_style
        ):
            title = label
        elif len(row_) >= 2 and label in layout.meta_rows:
            fields[layout.meta_rows[label]] = _cell_text(row_[1].paragraphs)
        elif layout.note_label is not None and label.startswith(
            layout.note_label
        ):
            note = _note_paragraphs(first_paragraphs, layout.note_label)
        else:
            statement.extend(first_paragraphs)
    return DocxRequirement(
        uid, title, fields, statement, note, list(table.comments)
    )


def _note_paragraphs(
    paragraphs: List[DocxParagraph], note_label: str
) -> List[DocxParagraph]:
    """Drops the label ("Note :") and keeps what follows it, if anything."""
    kept: List[DocxParagraph] = []
    for index_, paragraph_ in enumerate(paragraphs):
        text = paragraph_.text
        rst = paragraph_.rst
        markdown = paragraph_.markdown
        if index_ == 0:
            text = re.sub(
                rf"^{re.escape(note_label)}\s*:?\s*", "", text, count=1
            )
            # The label may sit inside the opening markup of a styled run.
            rst = re.sub(
                rf"^((?:\*\*|\*|``)?){re.escape(note_label)}\s*:?\s*",
                r"\1",
                rst,
                count=1,
            )
            markdown = re.sub(
                rf"^((?:\*\*\*|\*\*|\*|`)?){re.escape(note_label)}\s*:?\s*",
                r"\1",
                markdown,
                count=1,
            )
        if len(text.strip()) > 0:
            kept.append(
                DocxParagraph(
                    paragraph_.style,
                    text,
                    rst,
                    paragraph_.is_list_item,
                    markdown,
                )
            )
    return kept


def _cell_text(paragraphs: List[DocxParagraph]) -> str:
    return " ".join(
        paragraph_.text.strip()
        for paragraph_ in paragraphs
        if len(paragraph_.text.strip()) > 0
    )


def _resolve_uids(items: List[_Item], report: DocxImportReport) -> Set[str]:
    known: Set[str] = set()
    for item_ in items:
        if not isinstance(item_, DocxRequirement):
            continue
        if _UID_PATTERN.fullmatch(item_.uid) is None:
            report.invalid_uids.append(item_.uid)
            item_.uid = ""
        elif item_.uid in known:
            report.duplicate_uids.append(item_.uid)
            item_.uid = ""
        else:
            known.add(item_.uid)
    return known


def _grammar_text(
    layout: DocxRequirementTable,
    extra_fields: List[Tuple[str, List[str]]],
) -> str:
    field_lines = ["UID"] + list(layout.meta_rows.values())
    field_lines += ["TITLE", "STATEMENT"]
    if layout.note_label is not None:
        field_lines.append(layout.note_field)
    lines = [
        "[GRAMMAR]",
        "ELEMENTS:",
        "- TAG: SECTION",
        "  PROPERTIES:",
        "    IS_COMPOSITE: True",
        "  FIELDS:",
        "  - TITLE: UID",
        "    TYPE: String",
        "    REQUIRED: False",
        "  - TITLE: LEVEL",
        "    TYPE: String",
        "    REQUIRED: False",
        "  - TITLE: PREFIX",
        "    TYPE: String",
        "    REQUIRED: False",
        "  - TITLE: TITLE",
        "    TYPE: String",
        "    REQUIRED: True",
        "- TAG: TEXT",
        "  FIELDS:",
        "  - TITLE: STATEMENT",
        "    TYPE: String",
        "    REQUIRED: True",
        "- TAG: REQUIREMENT",
        "  FIELDS:",
    ]
    for name_ in field_lines:
        required = "True" if name_ in ("TITLE", "STATEMENT") else "False"
        lines += [
            f"  - TITLE: {name_}",
            "    TYPE: String",
            f"    REQUIRED: {required}",
        ]
    # Review comments (plan: comments). Every imported requirement can have
    # some, whether the Word file holds comments or not.
    lines += [
        "  - TITLE: COMMENT",
        "    TYPE: String",
        "    REQUIRED: False",
    ]
    for _, extra_lines_ in extra_fields:
        lines += extra_lines_
    lines += ["  RELATIONS:", "  - TYPE: Parent", "  - TYPE: File", ""]
    return "\n".join(lines)


def _requirement_text(
    requirement: DocxRequirement,
    layout: DocxRequirementTable,
    known_uids: Set[str],
    report: DocxImportReport,
    carry_over: Optional[CarryOver],
    markup: str = MARKUP_RST,
    reference_resolver: Optional[ResolverFunction] = None,
) -> str:
    fields: List[Tuple[str, str]] = []
    if len(requirement.uid) > 0:
        fields.append(("UID", requirement.uid))
    for field_name_ in layout.meta_rows.values():
        value = _single_line(requirement.fields.get(field_name_, ""))
        if len(value) > 0:
            fields.append((field_name_, value))
    title = _single_line(requirement.title)
    fields.append(("TITLE", title if len(title) > 0 else requirement.uid))
    statement = join_paragraphs(requirement.statement_paragraphs, markup)
    fields.append(("STATEMENT", _multiline(statement or "(no text)")))
    note = join_paragraphs(requirement.note_paragraphs, markup)
    if len(note) > 0:
        fields.append((layout.note_field, _multiline(note)))

    parent_uids = _parent_uids(
        requirement, layout, known_uids, report, reference_resolver
    )
    file_relations: List[List[str]] = []
    old_comments: List[str] = []
    if carry_over is not None and len(requirement.uid) > 0:
        old_block = carry_over.blocks.get(requirement.uid)
        if old_block is None:
            report.added_uids.append(requirement.uid)
        else:
            _note_changes(
                requirement.uid, fields, old_block.fields, layout, report
            )
            extra_names = [
                name_ for name_, _ in carry_over.extra_grammar_fields
            ]
            # Every value of an extra field, in file order (a field such as
            # COMMENT can be written several times).
            fields += [
                (name_, value_)
                for name_, value_ in old_block.fields
                if name_ in extra_names and name_ != "COMMENT"
            ]
            old_comments = [
                value_
                for name_, value_ in old_block.fields
                if name_ == "COMMENT"
            ]
            file_relations = old_block.file_relations
    fields += _comment_fields(requirement, old_comments, markup, report)
    return _render_requirement(fields, parent_uids, file_relations)


def _comment_fields(
    requirement: DocxRequirement,
    old_values: List[str],
    markup: str,
    report: DocxImportReport,
) -> List[Tuple[str, str]]:
    """
    The COMMENT fields of a requirement: the ones of the existing SDoc file,
    unchanged, then the comments of the Word document that the file does not
    hold yet (same author, date to the minute and text).
    """
    known = set()
    for value_ in old_values:
        comment_ = parse_comment(_field_text(value_))
        known.add(
            comment_fingerprint(
                comment_.author,
                comment_.date,
                comment_plain_text(comment_.body, markup),
            )
        )
    values = list(old_values)
    for word_comment_ in requirement.comments:
        fingerprint = comment_fingerprint(
            word_comment_.author, word_comment_.date, word_comment_.text
        )
        if fingerprint in known:
            continue
        known.add(fingerprint)
        date = word_comment_.date
        if date and not date.endswith("Z") and "+" not in date[10:]:
            date += "Z"
        comment = Comment(
            body=_escape_for_markup(word_comment_.text, markup),
            id="w"
            + hashlib.sha1("|".join(fingerprint).encode()).hexdigest()[:7],
            author=word_comment_.author,
            date=date,
            status=STATUS_RESOLVED if word_comment_.done else STATUS_OPEN,
            source="word",
        )
        values.append(_multiline(format_comment(comment, markup)))
        report.comments_added += 1
    return [("COMMENT", value_) for value_ in values]


def _escape_for_markup(text: str, markup: str) -> str:
    return (
        _escape_markdown(text)
        if markup == MARKUP_MARKDOWN
        else _escape_rst(text)
    )


def _parent_uids(
    requirement: DocxRequirement,
    layout: DocxRequirementTable,
    known_uids: Set[str],
    report: DocxImportReport,
    reference_resolver: Optional[ResolverFunction] = None,
) -> List[str]:
    parent_uids: List[str] = []
    for field_name_ in layout.relation_fields:
        value = requirement.fields.get(field_name_, "")
        if reference_resolver is not None:
            # Links inside the document and links to applicable documents.
            resolved = reference_resolver(value, known_uids)
            for uid_ in resolved.uids:
                if uid_ not in parent_uids and uid_ != requirement.uid:
                    parent_uids.append(uid_)
                    if uid_ not in known_uids:
                        report.references_resolved += 1
            for message_ in resolved.unresolved:
                report.unresolved_links.append((requirement.uid, message_))
            continue
        for token_ in re.split(r"[\s,;]+", value):
            name = token_.strip().rstrip(".")
            if len(name) == 0 or name == requirement.uid:
                continue
            if name in known_uids:
                if name not in parent_uids:
                    parent_uids.append(name)
            elif _looks_like_known_uid(name, known_uids):
                report.unresolved_links.append((requirement.uid, name))
    return parent_uids


def _render_requirement(
    fields: List[Tuple[str, str]],
    parent_uids: List[str],
    file_relations: List[List[str]],
) -> str:
    lines = ["[REQUIREMENT]"]
    lines += [f"{name_}: {value_}" for name_, value_ in fields]
    if len(parent_uids) > 0 or len(file_relations) > 0:
        lines.append("RELATIONS:")
        for parent_uid_ in parent_uids:
            lines += ["- TYPE: Parent", f"  VALUE: {parent_uid_}"]
        for relation_lines_ in file_relations:
            lines += relation_lines_
    return "\n".join(lines) + "\n"


def _field_text(raw_value: str) -> str:
    if raw_value.startswith(">>>\n") and raw_value.endswith("\n<<<"):
        raw_value = raw_value[len(">>>\n") : -len("\n<<<")]
    return raw_value.strip()


def _note_changes(
    uid: str,
    new_fields: List[Tuple[str, str]],
    old_fields: List[Tuple[str, str]],
    layout: DocxRequirementTable,
    report: DocxImportReport,
) -> None:
    new_values = {name_: _field_text(value_) for name_, value_ in new_fields}
    old_values = {name_: _field_text(value_) for name_, value_ in old_fields}
    changed = [
        name_
        for name_ in owned_field_names(layout)
        if name_ != "UID"
        and new_values.get(name_, "") != old_values.get(name_, "")
    ]
    if len(changed) > 0:
        report.changed_uids[uid] = changed
    else:
        report.unchanged_count += 1


def _removed_requirements_text(
    layout: DocxRequirementTable,
    known_uids: Set[str],
    report: DocxImportReport,
    carry_over: CarryOver,
) -> str:
    """
    Requirements that are in the existing file but no longer in the Word
    document are kept, in a section of their own. Nothing is deleted silently.
    """
    removed = [uid_ for uid_ in carry_over.blocks if uid_ not in known_uids]
    if len(removed) == 0:
        return ""
    report.removed_uids = removed
    names = owned_field_names(layout) + [
        name_ for name_, _ in carry_over.extra_grammar_fields
    ]
    parts = [f"[[SECTION]]\nTITLE: {REMOVED_SECTION_TITLE}\n"]
    for uid_ in removed:
        block = carry_over.blocks[uid_]
        values = dict(block.fields)
        fields = [(n_, values[n_]) for n_ in names if n_ in values]
        parts.append(_render_requirement(fields, [], block.file_relations))
    parts.append("[[/SECTION]]\n")
    return "\n".join(parts)


def _looks_like_known_uid(name: str, known_uids: Set[str]) -> bool:
    """
    True if the name has the shape of this document's UIDs: it starts with the
    same prefix (the part before the first dash) as a known one.
    """
    if _UID_PATTERN.fullmatch(name) is None or "-" not in name:
        return False
    prefix = name.split("-", 1)[0]
    return any(uid_.split("-", 1)[0] == prefix for uid_ in known_uids)


def join_paragraphs(
    paragraphs: List[DocxParagraph], markup: str = MARKUP_RST
) -> str:
    """
    One paragraph of the given markup per Word paragraph. List items that
    follow each other stay together, so that the markup sees one list.
    """
    result: List[str] = []
    previous_was_item = False
    for paragraph_ in paragraphs:
        text = paragraph_.marked_up(markup).strip()
        if len(text) == 0:
            continue
        marker = _list_marker(paragraph_, markup)
        is_item = marker is not None
        if marker is not None:
            text = _ITEM_MARKER_PATTERN.sub("", text, count=1)
            text = marker + text.replace("\n", "\n  ")
        separator = "\n" if is_item and previous_was_item else "\n\n"
        if len(result) > 0:
            result.append(separator)
        result.append(text)
        previous_was_item = is_item
    return "".join(result)


# The marker of a list item, as written by the Markdown or the RST escaping.
_ITEM_MARKER_PATTERN = re.compile(r"^\\?(?:-|\u2022|\d+\\?[.)])\s+")
_PLAIN_ITEM_PATTERN = re.compile(r"^\s*(?:(-|\u2022)|(\d+)[.)])\s+")


def _list_marker(paragraph: DocxParagraph, markup: str) -> Optional[str]:
    """The marker to write for a list item, or None for a normal paragraph."""
    match = _PLAIN_ITEM_PATTERN.match(paragraph.text)
    if match is not None:
        if match.group(2) is None:
            return "- "
        if markup == MARKUP_MARKDOWN:
            return f"{match.group(2)}. "
        # In RST, a paragraph that starts with a number is a normal paragraph.
    if paragraph.is_list_item:
        return "- "
    return None


def _list_table(table: DocxTable, markup: str = MARKUP_RST) -> str:
    column_count = max((len(row_) for row_ in table.rows), default=0)
    if column_count == 0:
        return ""
    if markup == MARKUP_MARKDOWN:
        return _pipe_table(table, column_count)
    lines = [".. list-table::", ""]
    for row_ in table.rows:
        cells = [
            _single_line(" ".join(p_.rst for p_ in cell_.paragraphs))
            for cell_ in row_
        ]
        cells += [""] * (column_count - len(cells))
        for index_, cell_text_ in enumerate(cells):
            prefix = "   * - " if index_ == 0 else "     - "
            lines.append((prefix + cell_text_).rstrip())
    return "\n".join(lines)


def _pipe_table(table: DocxTable, column_count: int) -> str:
    """A Markdown pipe table; the first row of the Word table is the header."""
    rows: List[List[str]] = []
    for row_ in table.rows:
        cells = [
            _single_line(
                " ".join(
                    p_.marked_up(MARKUP_MARKDOWN) for p_ in cell_.paragraphs
                )
            ).replace("|", "\\|")
            for cell_ in row_
        ]
        rows.append(cells + [""] * (column_count - len(cells)))
    lines = ["| " + " | ".join(rows[0]) + " |"]
    lines.append("| " + " | ".join(["---"] * column_count) + " |")
    for cells in rows[1:]:
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _text_node(statement: str) -> str:
    if len(statement.strip()) == 0:
        return ""
    return "[TEXT]\nSTATEMENT: " + _multiline(statement) + "\n"


def _multiline(text: str) -> str:
    text = text.replace("<<<", "\\<\\<\\<")
    return ">>>\n" + text.strip("\n") + "\n<<<"


def _single_line(text: str) -> str:
    return " ".join(text.split())
