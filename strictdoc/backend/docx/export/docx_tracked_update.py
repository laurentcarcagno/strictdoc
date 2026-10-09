"""
Updates a Word document from the model and records every change as a tracked
change.

The requirements of the base document are matched with the model by UID:

- a new requirement is inserted as a tracked table, after its predecessor,
- a requirement that changed gets its changed fields replaced: the old text is
  a tracked deletion, the new text a tracked insertion,
- a requirement that is no longer in the model is a tracked deletion,
- everything else, including everything that is not a requirement, is left
  byte for byte as it was.

Rejecting all changes gives back the base document. Accepting them gives the
model.
"""

import datetime as dt
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from strictdoc.backend.docx.docx_profile import (
    DocxProfile,
    DocxRequirementTable,
)
from strictdoc.backend.docx.export.docx_template import (
    clean_skeleton,
    split_top_level,
)
from strictdoc.backend.docx.export.docx_xml import paragraph_xml
from strictdoc.backend.docx.export.rst_to_paragraphs import (
    ExportParagraph,
    ExportRun,
    rst_to_paragraphs,
)
from strictdoc.backend.docx.export.sdoc_to_docx_generator import (
    PARAGRAPH_PATTERN,
    ExportItem,
    ExportRequirement,
    ExportSection,
    effective_profile,
    paragraph_like,
    requirement_xml,
    row_role,
    text_of,
)
from strictdoc.backend.docx.import_.docx_reader import (
    DocxTable,
    TrackedChangesMode,
    read_table_element,
)
from strictdoc.backend.docx.import_.docx_to_sdoc_converter import (
    join_paragraphs,
    read_requirement,
)
from strictdoc.helpers.exception import StrictDocException
from strictdoc.helpers.file_system import file_open_read_bytes

_WORD = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_RUN = re.compile(r"<w:r(?:\s[^>]*)?>.*?</w:r>", re.S)
_DELETED_BLOCK = re.compile(r"<w:del\b[^>/]*>.*?</w:del>", re.S)


@dataclass
class DocxUpdateReport:
    added: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    # UID -> names of the fields that changed.
    changed: Dict[str, List[str]] = field(default_factory=dict)
    unchanged: int = 0

    def format(self) -> str:
        summary = (
            f"Word update: {len(self.added)} added, "
            f"{len(self.changed)} changed, {len(self.deleted)} deleted, "
            f"{self.unchanged} unchanged requirement(s)."
        )
        lines = [summary]
        lines += [f"  Added: {uid_}" for uid_ in self.added]
        lines += [
            f"  Changed: {uid_} ({', '.join(names_)})"
            for uid_, names_ in self.changed.items()
        ]
        lines += [f"  Deleted: {uid_}" for uid_ in self.deleted]
        return "\n".join(lines)


class DocxUpdater:
    @staticmethod
    def update(
        base_path: str, items: List[ExportItem], profile: DocxProfile
    ) -> Tuple[Dict[str, bytes], DocxUpdateReport]:
        profile = effective_profile(profile)
        layout = profile.requirement_table
        assert layout is not None
        parts = _read_package(base_path)
        document_xml = parts["word/document.xml"].decode("utf8")
        body_start = document_xml.index("<w:body>") + len("<w:body>")
        body_end = document_xml.rindex("</w:body>")
        chunks = split_top_level(document_xml[body_start:body_end])
        if "".join(chunks) != document_xml[body_start:body_end]:
            raise StrictDocException(
                f"Could not split the body of {base_path} safely."
            )

        revisions = _Revisions(profile.revision_author, document_xml)
        report = DocxUpdateReport()
        base_requirements = _index_requirements(
            chunks, document_xml[:body_start], layout
        )
        base_headings = _index_headings(chunks, profile)
        skeleton = _skeleton(chunks, layout)

        insertions: Dict[int, List[str]] = {}
        anchor = -1
        model_uids = set()
        for item_ in items:
            if isinstance(item_, ExportSection):
                found = base_headings.get((item_.level, item_.title))
                anchor = found if found is not None else anchor
                continue
            if not isinstance(item_, ExportRequirement):
                continue
            model_uids.add(item_.uid)
            base = base_requirements.get(item_.uid)
            if base is not None:
                changed = _changed_fields(base, item_, layout)
                if len(changed) > 0:
                    chunks[base.chunk_index] = _edit_table(
                        chunks[base.chunk_index],
                        item_,
                        changed,
                        layout,
                        revisions,
                    )
                    report.changed[item_.uid] = changed
                else:
                    report.unchanged += 1
                anchor = base.chunk_index
            else:
                new_table = requirement_xml(item_, layout, skeleton)
                inserted = revisions.inserted_table(new_table) + (
                    revisions.inserted_empty_paragraph()
                )
                insertions.setdefault(anchor, []).append(inserted)
                report.added.append(item_.uid)

        for uid_, base_ in base_requirements.items():
            if uid_ not in model_uids:
                chunks[base_.chunk_index] = revisions.deleted_table(
                    chunks[base_.chunk_index]
                )
                report.deleted.append(uid_)

        body = _assemble(chunks, insertions, base_requirements)
        parts["word/document.xml"] = (
            document_xml[:body_start] + body + document_xml[body_end:]
        ).encode("utf8")
        return parts, report


# ---- reading the base ------------------------------------------------------------


@dataclass
class _BaseRequirement:
    chunk_index: int
    uid: str
    title: str
    fields: Dict[str, str]
    statement: str
    note: str


def _read_package(path: str) -> Dict[str, bytes]:
    try:
        with file_open_read_bytes(path) as file_:
            with zipfile.ZipFile(file_) as package_:
                parts = {
                    name_: package_.read(name_) for name_ in package_.namelist()
                }
    except (zipfile.BadZipFile, OSError) as exception_:
        raise StrictDocException(
            f"Could not read the Word document {path}: {exception_}."
        ) from exception_
    if "word/document.xml" not in parts:
        raise StrictDocException(f"{path} has no word/document.xml.")
    return parts


def _index_requirements(
    chunks: List[str], document_head: str, layout: DocxRequirementTable
) -> Dict[str, _BaseRequirement]:
    marker = f'<w:pStyle w:val="{layout.id_style}"/>'
    requirements: Dict[str, _BaseRequirement] = {}
    for index_, chunk_ in enumerate(chunks):
        if not chunk_.startswith("<w:tbl"):
            continue
        first_style = re.search(r'<w:pStyle w:val="[^"]*"/>', chunk_)
        if first_style is None or first_style.group(0) != marker:
            continue
        table = _parse_table(document_head, chunk_)
        requirement = read_requirement(table, layout)
        if requirement is None or len(requirement.uid) == 0:
            continue
        if requirement.uid in requirements:
            continue
        requirements[requirement.uid] = _BaseRequirement(
            chunk_index=index_,
            uid=requirement.uid,
            title=requirement.title,
            fields=requirement.fields,
            statement=join_paragraphs(requirement.statement_paragraphs),
            note=join_paragraphs(requirement.note_paragraphs),
        )
    return requirements


def _parse_table(document_head: str, table_xml: str) -> DocxTable:
    root = ET.fromstring(document_head + table_xml + "</w:body></w:document>")
    element = root.find(f"{{{_WORD}}}body/{{{_WORD}}}tbl")
    assert element is not None
    return read_table_element(element, TrackedChangesMode.ACCEPT)


def _index_headings(
    chunks: List[str], profile: DocxProfile
) -> Dict[Tuple[int, str], int]:
    headings: Dict[Tuple[int, str], int] = {}
    for index_, chunk_ in enumerate(chunks):
        if not chunk_.startswith("<w:p"):
            continue
        style = re.search(r'<w:pStyle w:val="([^"]*)"/>', chunk_)
        if style is None or style.group(1) not in profile.heading_styles:
            continue
        level = profile.heading_styles[style.group(1)]
        key = (level, " ".join(text_of(chunk_).split()))
        headings.setdefault(key, index_)
    return headings


def _skeleton(chunks: List[str], layout: DocxRequirementTable) -> str:
    from strictdoc.backend.docx.export.docx_template import (  # noqa: PLC0415
        DocxTemplate,
    )

    marker = f'<w:pStyle w:val="{layout.id_style}"/>'
    for chunk_ in chunks:
        if chunk_.startswith("<w:tbl") and chunk_.count("<w:tbl>") == 1:
            first_style = re.search(r'<w:pStyle w:val="[^"]*"/>', chunk_)
            if first_style is not None and first_style.group(0) == marker:
                return clean_skeleton(chunk_)
    return DocxTemplate.minimal(
        DocxProfile(requirement_table=layout)
    ).requirement_skeleton


# ---- comparing -----------------------------------------------------------------------


def _normal(text: str) -> str:
    return " ".join(text.split())


def _changed_fields(
    base: _BaseRequirement,
    model: ExportRequirement,
    layout: DocxRequirementTable,
) -> List[str]:
    changed: List[str] = []
    if _normal(base.title) != _normal(model.title):
        changed.append("TITLE")
    for field_name_ in layout.meta_rows.values():
        if _normal(base.fields.get(field_name_, "")) != _normal(
            model.fields.get(field_name_, "")
        ):
            changed.append(field_name_)
    if _normal(base.statement) != _normal(model.statement):
        changed.append("STATEMENT")
    if layout.note_label is not None and _normal(base.note) != _normal(
        model.note
    ):
        changed.append(layout.note_field)
    return changed


# ---- editing a requirement table ----------------------------------------------------


def _edit_table(
    table_xml: str,
    model: ExportRequirement,
    changed: List[str],
    layout: DocxRequirementTable,
    revisions: "_Revisions",
) -> str:
    rows = re.findall(r"<w:tr\b.*?</w:tr>", table_xml, re.S)
    result = table_xml
    text_row_done = False
    for row_ in rows:
        role = row_role(row_, layout, text_row_done)
        new_row: Optional[str] = None
        if role == "title" and "TITLE" in changed:
            new_row = _edit_single_cell(row_, 0, model.title, revisions)
        elif role.startswith("meta:") and role[5:] in changed:
            value = model.fields.get(role[5:], "")
            new_row = _edit_single_cell(row_, 1, value, revisions)
        elif role == "text":
            text_row_done = True
            if "STATEMENT" in changed:
                new_row = _edit_paragraph_cell(
                    row_, rst_to_paragraphs(model.statement), revisions
                )
        elif role == "note" and layout.note_field in changed:
            new_row = _edit_paragraph_cell(
                row_,
                _note_paragraphs(row_, model.note, layout.note_label or ""),
                revisions,
            )
        if new_row is not None:
            result = result.replace(row_, new_row, 1)
    return result


def _note_paragraphs(
    row_xml: str, note: str, note_label: str
) -> List[ExportParagraph]:
    cell = re.search(r"<w:tc\b.*?</w:tc>", row_xml, re.S)
    prototype = PARAGRAPH_PATTERN.search(cell.group(0)) if cell else None
    label_match = (
        re.match(
            rf"\s*{re.escape(note_label)}\s*:?", text_of(prototype.group(0))
        )
        if prototype is not None
        else None
    )
    label = label_match.group(0).strip() if label_match else f"{note_label} :"
    paragraphs = rst_to_paragraphs(note)
    if len(paragraphs) == 0:
        return [ExportParagraph([ExportRun(label)])]
    first = ExportParagraph([ExportRun(label + " ")] + paragraphs[0].runs)
    return [first, *paragraphs[1:]]


def _edit_single_cell(
    row_xml: str, cell_index: int, text: str, revisions: "_Revisions"
) -> str:
    """Replaces the text of the first paragraph of a cell, in place."""
    cells = re.findall(r"<w:tc\b.*?</w:tc>", row_xml, re.S)
    cell = cells[cell_index]
    match = PARAGRAPH_PATTERN.search(cell)
    if match is None:
        return row_xml
    paragraph = match.group(0)
    deleted = revisions.delete_runs(paragraph)
    if len(text) > 0:
        run_properties = re.search(
            r"<w:r\b[^>]*>(<w:rPr>.*?</w:rPr>)", paragraph, re.S
        )
        inserted_run = paragraph_xml(
            ExportParagraph([ExportRun(text)]),
            run_properties_xml=run_properties.group(1)
            if run_properties is not None
            else "",
        )
        runs = "".join(_RUN.findall(inserted_run))
        insertion = revisions.wrap_inserted(runs)
    else:
        insertion = ""
    if deleted.endswith("</w:p>"):
        deleted = deleted[: -len("</w:p>")] + insertion + "</w:p>"
    else:
        deleted = deleted + insertion
    return row_xml.replace(cell, cell.replace(paragraph, deleted, 1), 1)


def _edit_paragraph_cell(
    row_xml: str, paragraphs: List[ExportParagraph], revisions: "_Revisions"
) -> str:
    """Deletes every paragraph of the first cell, then inserts the new ones."""
    cells = re.findall(r"<w:tc\b.*?</w:tc>", row_xml, re.S)
    cell = cells[0]
    old_paragraphs = PARAGRAPH_PATTERN.findall(cell)
    if len(old_paragraphs) == 0:
        return row_xml
    prototype = old_paragraphs[0]
    deleted = "".join(revisions.delete_paragraph(p_) for p_ in old_paragraphs)
    inserted = "".join(
        revisions.inserted_paragraph(paragraph_like(prototype, p_))
        for p_ in paragraphs
    )
    first = PARAGRAPH_PATTERN.search(cell)
    assert first is not None
    last_end = list(PARAGRAPH_PATTERN.finditer(cell))[-1].end()
    new_cell = cell[: first.start()] + deleted + inserted + cell[last_end:]
    return row_xml.replace(cell, new_cell, 1)


def _assemble(
    chunks: List[str],
    insertions: Dict[int, List[str]],
    base_requirements: Dict[str, _BaseRequirement],
) -> str:
    """The new body: chunks in order, each insertion after its anchor chunk."""
    end_of_content = len(chunks)
    if end_of_content > 0 and chunks[-1].startswith("<w:sectPr"):
        end_of_content -= 1
    first_requirement = min(
        (b_.chunk_index for b_ in base_requirements.values()),
        default=end_of_content,
    )
    # No anchor: before the first requirement, or at the end of the content.
    pending = insertions.pop(-1, [])
    parts: List[str] = []
    for index_, chunk_ in enumerate(chunks):
        if len(pending) > 0 and index_ in (first_requirement, end_of_content):
            parts.extend(pending)
            pending = []
        parts.append(chunk_)
        parts.extend(_after_anchor(chunks, index_, insertions))
    parts.extend(pending)
    return "".join(parts)


def _after_anchor(
    chunks: List[str], index: int, insertions: Dict[int, List[str]]
) -> List[str]:
    """
    New content goes after the anchor chunk and after the empty paragraph that
    usually follows a requirement table, so that two tables never touch.
    """
    anchored = insertions.get(index)
    if anchored is None:
        return []
    next_chunk = chunks[index + 1] if index + 1 < len(chunks) else ""
    is_table = chunks[index].startswith("<w:tbl")
    if is_table and _is_empty_paragraph(next_chunk):
        # Emit them after the empty paragraph: hand them to that chunk.
        insertions.setdefault(index + 1, [])
        insertions[index + 1] = anchored + insertions[index + 1]
        del insertions[index]
        return []
    return insertions.pop(index)


def _is_empty_paragraph(chunk: str) -> bool:
    return (
        chunk.startswith("<w:p")
        and "<w:t" not in chunk
        and "<w:tbl" not in chunk
    )


# ---- tracked-change markup -----------------------------------------------------------


class _Revisions:
    def __init__(self, author: str, document_xml: str) -> None:
        self.author = author
        self.date = dt.datetime.now(dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:00Z"
        )
        identifiers = [
            int(i_) for i_ in re.findall(r'w:id="(\d+)"', document_xml)
        ]
        self._next_id = max(identifiers, default=0) + 1

    def attributes(self) -> str:
        self._next_id += 1
        return (
            f'w:id="{self._next_id - 1}" w:author="{self.author}" '
            f'w:date="{self.date}"'
        )

    def wrap_inserted(self, runs_xml: str) -> str:
        return "".join(
            f"<w:ins {self.attributes()}>{run_}</w:ins>"
            for run_ in _RUN.findall(runs_xml)
        )

    def inserted_empty_paragraph(self) -> str:
        return self.inserted_paragraph("<w:p/>")

    def inserted_paragraph(self, paragraph: str) -> str:
        """A paragraph whose mark and runs are tracked insertions."""
        paragraph = self._mark_paragraph(paragraph, "ins")
        return _RUN.sub(
            lambda m_: f"<w:ins {self.attributes()}>{m_.group(0)}</w:ins>",
            paragraph,
        )

    def inserted_table(self, table_xml: str) -> str:
        def mark_row(match: "re.Match[str]") -> str:
            row_ = self._mark_row(match.group(0), "ins")
            return PARAGRAPH_PATTERN.sub(
                lambda p_: self.inserted_paragraph(p_.group(0)), row_
            )

        return re.sub(r"<w:tr\b.*?</w:tr>", mark_row, table_xml, flags=re.S)

    def deleted_table(self, table_xml: str) -> str:
        def mark_row(match: "re.Match[str]") -> str:
            row_ = self._mark_row(match.group(0), "del")
            return PARAGRAPH_PATTERN.sub(
                lambda p_: self.delete_paragraph(p_.group(0)), row_
            )

        return re.sub(r"<w:tr\b.*?</w:tr>", mark_row, table_xml, flags=re.S)

    def delete_paragraph(self, paragraph: str) -> str:
        return self._mark_paragraph(self.delete_runs(paragraph), "del")

    def delete_runs(self, paragraph: str) -> str:
        """Wraps every run that is not already deleted in a tracked deletion."""
        pieces: List[str] = []
        last = 0
        for deleted_ in _DELETED_BLOCK.finditer(paragraph):
            pieces.append(self._delete_in(paragraph[last : deleted_.start()]))
            pieces.append(deleted_.group(0))
            last = deleted_.end()
        pieces.append(self._delete_in(paragraph[last:]))
        return "".join(pieces)

    def _delete_in(self, xml: str) -> str:
        def delete_run(match: "re.Match[str]") -> str:
            run_ = match.group(0)
            run_ = re.sub(r"<w:t(\s[^>]*)?>", r"<w:delText\1>", run_)
            run_ = run_.replace("</w:t>", "</w:delText>")
            return f"<w:del {self.attributes()}>{run_}</w:del>"

        return _RUN.sub(delete_run, xml)

    def _mark_paragraph(self, paragraph: str, kind: str) -> str:
        mark = f"<w:{kind} {self.attributes()}/>"
        if paragraph == "<w:p/>":
            return f"<w:p><w:pPr><w:rPr>{mark}</w:rPr></w:pPr></w:p>"
        properties = re.search(r"<w:pPr>.*?</w:pPr>", paragraph, re.S)
        if properties is None:
            open_tag = re.match(r"<w:p(?:\s[^>]*)?>", paragraph)
            assert open_tag is not None
            return (
                open_tag.group(0)
                + f"<w:pPr><w:rPr>{mark}</w:rPr></w:pPr>"
                + paragraph[open_tag.end() :]
            )
        existing = properties.group(0)
        if "<w:rPr>" in existing:
            updated = existing.replace("<w:rPr>", f"<w:rPr>{mark}", 1)
        else:
            updated = existing.replace(
                "</w:pPr>", f"<w:rPr>{mark}</w:rPr></w:pPr>", 1
            )
        return paragraph.replace(existing, updated, 1)

    def _mark_row(self, row_xml: str, kind: str) -> str:
        mark = f"<w:{kind} {self.attributes()}/>"
        if "<w:trPr>" in row_xml:
            return row_xml.replace("</w:trPr>", f"{mark}</w:trPr>", 1)
        open_tag = re.match(r"<w:tr(?:\s[^>]*)?>", row_xml)
        assert open_tag is not None
        return (
            open_tag.group(0)
            + f"<w:trPr>{mark}</w:trPr>"
            + row_xml[open_tag.end() :]
        )
