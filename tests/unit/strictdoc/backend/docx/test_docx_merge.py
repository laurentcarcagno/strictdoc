import os
from typing import List, Optional, Tuple

from strictdoc.backend.docx.docx_profile import (
    DocxProfile,
    DocxRequirementTable,
)
from strictdoc.backend.docx.import_.docx_reader import (
    DocxReader,
    TrackedChangesMode,
)
from strictdoc.backend.docx.import_.docx_to_sdoc_converter import (
    DocxImportReport,
    DocxToSDocConverter,
)
from strictdoc.backend.docx.import_.sdoc_requirement_blocks import (
    build_carry_over,
)
from tests.unit.strictdoc.backend.docx.docx_builder import (
    cell,
    paragraph,
    row,
    table,
    write_docx,
)

PROFILE = DocxProfile(
    requirement_table=DocxRequirementTable(
        id_style="ReqId",
        title_style="ReqTitle",
        meta_rows={"Version:": "VERSION", "Linked Req:": "LINKED_REQ"},
        text_style="ReqText",
        note_label="Note",
        relation_fields=["LINKED_REQ"],
    ),
)


def _requirement(uid, title="T", version="V0", linked="-", text="Shall work."):
    return table(
        row(cell(paragraph(uid, style="ReqId"))),
        row(cell(paragraph(title, style="ReqTitle"))),
        row(cell(paragraph("Version:")), cell(paragraph(version))),
        row(cell(paragraph("Linked Req:")), cell(paragraph(linked))),
        row(cell(paragraph(text, style="ReqText"))),
        row(cell(paragraph("Note :"))),
    )


def _import(
    tmp_path, blocks: List[str], existing: Optional[str]
) -> Tuple[str, DocxImportReport]:
    path = os.path.join(str(tmp_path), "input.docx")
    write_docx(path, blocks)
    docx_blocks = DocxReader.read(path, TrackedChangesMode.ACCEPT)
    carry = (
        build_carry_over(existing, PROFILE.requirement_table)
        if existing is not None
        else None
    )
    text, report = DocxToSDocConverter.build_sdoc_text(
        docx_blocks, PROFILE, "Doc", carry
    )
    DocxToSDocConverter.parse(text)
    return text, report


def test_001_importing_twice_gives_the_same_text_and_no_change(tmp_path):
    blocks = [paragraph("Ch", style="Heading1"), _requirement("R-1")]
    first, _ = _import(tmp_path, blocks, None)
    second, report = _import(tmp_path, blocks, first)
    assert second == first
    assert report.merged is True
    assert report.added_uids == []
    assert report.changed_uids == {}
    assert report.unchanged_count == 1
    assert report.removed_uids == []


def test_002_a_first_import_does_not_report_a_merge(tmp_path):
    _, report = _import(tmp_path, [_requirement("R-1")], None)
    assert report.merged is False


def test_003_a_changed_field_is_updated_and_named_in_the_report(tmp_path):
    first, _ = _import(tmp_path, [_requirement("R-1", version="V0")], None)
    second, report = _import(
        tmp_path,
        [_requirement("R-1", version="V1", text="Shall do more.")],
        first,
    )
    assert "VERSION: V1" in second and "Shall do more." in second
    assert report.changed_uids == {"R-1": ["VERSION", "STATEMENT"]}


def test_004_a_new_requirement_is_added(tmp_path):
    first, _ = _import(tmp_path, [_requirement("R-1")], None)
    second, report = _import(
        tmp_path, [_requirement("R-1"), _requirement("R-2")], first
    )
    assert "UID: R-2" in second
    assert report.added_uids == ["R-2"]


def test_005_fields_and_file_relations_added_by_hand_are_kept(tmp_path):
    first, _ = _import(tmp_path, [_requirement("R-1")], None)
    edited = first.replace(
        "  RELATIONS:\n  - TYPE: Parent",
        "  - TITLE: OWNER\n    TYPE: String\n    REQUIRED: False\n"
        "  RELATIONS:\n  - TYPE: Parent",
    ).replace(
        "TITLE: T\n",
        "TITLE: T\n",
    )
    edited = edited.replace(
        "STATEMENT: >>>\nShall work.\n<<<\n",
        "STATEMENT: >>>\nShall work.\n<<<\nOWNER: Alice\n"
        "RELATIONS:\n- TYPE: File\n  VALUE: src/a.c\n",
    )
    second, report = _import(
        tmp_path, [_requirement("R-1", text="Shall work better.")], edited
    )
    assert "OWNER: Alice" in second
    assert "- TYPE: File\n  VALUE: src/a.c" in second
    assert "Shall work better." in second
    assert "TITLE: OWNER" in second
    assert report.changed_uids == {"R-1": ["STATEMENT"]}


def test_006_a_requirement_gone_from_word_is_kept_and_reported(tmp_path):
    first, _ = _import(
        tmp_path, [_requirement("R-1"), _requirement("R-2")], None
    )
    second, report = _import(tmp_path, [_requirement("R-1")], first)
    assert report.removed_uids == ["R-2"]
    assert "TITLE: Not in the Word document" in second
    assert "UID: R-2" in second


def test_007_a_requirement_kept_once_stays_kept_and_the_text_is_stable(
    tmp_path,
):
    first, _ = _import(
        tmp_path, [_requirement("R-1"), _requirement("R-2")], None
    )
    second, _ = _import(tmp_path, [_requirement("R-1")], first)
    third, report = _import(tmp_path, [_requirement("R-1")], second)
    assert third == second
    assert report.removed_uids == ["R-2"]


def test_008_a_removed_requirement_that_comes_back_leaves_the_kept_section(
    tmp_path,
):
    first, _ = _import(
        tmp_path, [_requirement("R-1"), _requirement("R-2")], None
    )
    second, _ = _import(tmp_path, [_requirement("R-1")], first)
    third, report = _import(
        tmp_path, [_requirement("R-1"), _requirement("R-2")], second
    )
    assert "Not in the Word document" not in third
    assert report.removed_uids == []


def test_009_parent_relations_follow_word_not_the_old_file(tmp_path):
    first, _ = _import(
        tmp_path, [_requirement("R-1"), _requirement("R-2", linked="R-1")], None
    )
    second, _ = _import(
        tmp_path, [_requirement("R-1"), _requirement("R-2", linked="-")], first
    )
    assert "VALUE: R-1" not in second
