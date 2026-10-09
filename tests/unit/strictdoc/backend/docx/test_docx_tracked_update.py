import os
import re
import zipfile
from typing import List, Tuple

from strictdoc.backend.docx.docx_profile import (
    DocxProfile,
    DocxRequirementTable,
)
from strictdoc.backend.docx.export.docx_tracked_update import (
    DocxUpdater,
    DocxUpdateReport,
)
from strictdoc.backend.docx.export.sdoc_to_docx_generator import (
    ExportRequirement,
    ExportSection,
)
from strictdoc.backend.docx.import_.docx_reader import (
    DocxReader,
    DocxTable,
    TrackedChangesMode,
)
from tests.unit.strictdoc.backend.docx.docx_builder import (
    cell,
    paragraph,
    row,
    table,
    write_docx,
)

PROFILE = DocxProfile(
    heading_styles={"Heading1": 1, "Heading2": 2},
    requirement_table=DocxRequirementTable(
        id_style="ReqId",
        title_style="ReqTitle",
        meta_rows={"Version:": "VERSION", "Linked Req:": "LINKED_REQ"},
        text_style="ReqText",
        note_label="Note",
        relation_fields=["LINKED_REQ"],
    ),
    revision_author="Laurent Carcagno",
)


def _table(uid, title="T", version="V0", text="Shall work.", note="Note :"):
    return table(
        row(cell(paragraph(uid, style="ReqId"))),
        row(cell(paragraph(title, style="ReqTitle"))),
        row(cell(paragraph("Version:")), cell(paragraph(version))),
        row(cell(paragraph("Linked Req:")), cell(paragraph("-"))),
        row(cell(paragraph(text, style="ReqText"))),
        row(cell(paragraph(note))),
    )


def _requirement(uid, title="T", version="V0", text="Shall work.", note=""):
    return ExportRequirement(
        uid=uid,
        title=title,
        statement=text,
        fields={"VERSION": version, "LINKED_REQ": "-"},
        note=note,
    )


def _base(tmp_path, blocks: List[str]) -> str:
    path = os.path.join(str(tmp_path), "base.docx")
    write_docx(path, blocks)
    return path


def _update(
    tmp_path, base_blocks: List[str], items
) -> Tuple[str, DocxUpdateReport]:
    base = _base(tmp_path, base_blocks)
    package, report = DocxUpdater.update(base, items, PROFILE)
    out = os.path.join(str(tmp_path), "out.docx")
    with zipfile.ZipFile(out, "w") as output_:
        for name_, data_ in package.items():
            output_.writestr(name_, data_)
    return out, report


def _requirements(path: str, mode: TrackedChangesMode) -> dict:  # type: ignore[type-arg]
    result = {}
    for block_ in DocxReader.read(path, mode):
        if isinstance(block_, DocxTable) and len(block_.rows) > 0:
            cells = [
                " | ".join(p_.text for c_ in r_ for p_ in c_.paragraphs)
                for r_ in block_.rows
            ]
            result[cells[0]] = cells
    return result


def _document_xml(path: str) -> str:
    return zipfile.ZipFile(path).read("word/document.xml").decode()


def test_001_an_unchanged_document_is_not_touched(tmp_path):
    base_blocks = [
        paragraph("Chapter", style="Heading1"),
        _table("R-1"),
        paragraph(""),
    ]
    out, report = _update(
        tmp_path,
        base_blocks,
        [ExportSection(1, "Chapter"), _requirement("R-1")],
    )
    assert _document_xml(out) == _document_xml(_base(tmp_path, base_blocks))
    assert report.unchanged == 1
    assert report.added == [] and report.deleted == [] and report.changed == {}


def test_002_a_changed_title_is_a_tracked_replacement(tmp_path):
    out, report = _update(
        tmp_path,
        [_table("R-1", title="Old")],
        [_requirement("R-1", title="New")],
    )
    assert report.changed == {"R-1": ["TITLE"]}
    assert _requirements(out, TrackedChangesMode.ACCEPT)["R-1"][1] == "New"
    assert _requirements(out, TrackedChangesMode.REJECT)["R-1"][1] == "Old"
    xml = _document_xml(out)
    assert 'w:author="Laurent Carcagno"' in xml
    assert "<w:delText" in xml and "<w:ins " in xml


def test_003_a_changed_statement_replaces_the_paragraphs(tmp_path):
    out, report = _update(
        tmp_path,
        [_table("R-1", text="Old text.")],
        [_requirement("R-1", text="First new.\n\nSecond new.")],
    )
    assert report.changed == {"R-1": ["STATEMENT"]}
    accepted = _requirements(out, TrackedChangesMode.ACCEPT)["R-1"]
    assert "First new." in accepted[4] and "Second new." in accepted[4]
    assert "Old text." not in accepted[4]
    assert (
        "Old text." in _requirements(out, TrackedChangesMode.REJECT)["R-1"][4]
    )


def test_004_a_changed_meta_field_is_replaced_in_place(tmp_path):
    out, report = _update(
        tmp_path,
        [_table("R-1", version="V0")],
        [_requirement("R-1", version="V3")],
    )
    assert report.changed == {"R-1": ["VERSION"]}
    assert _requirements(out, TrackedChangesMode.ACCEPT)["R-1"][2].endswith(
        "V3"
    )
    assert _requirements(out, TrackedChangesMode.REJECT)["R-1"][2].endswith(
        "V0"
    )


def test_005_a_new_requirement_is_inserted_after_its_predecessor(tmp_path):
    out, report = _update(
        tmp_path,
        [_table("R-1"), paragraph(""), _table("R-3"), paragraph("")],
        [_requirement("R-1"), _requirement("R-2"), _requirement("R-3")],
    )
    assert report.added == ["R-2"]
    accepted = list(_requirements(out, TrackedChangesMode.ACCEPT))
    assert accepted == ["R-1", "R-2", "R-3"]
    assert list(_requirements(out, TrackedChangesMode.REJECT)) == ["R-1", "R-3"]
    assert 'w:val="ReqId"' in _document_xml(out)


def test_006_a_requirement_missing_from_the_model_is_deleted_with_tracking(
    tmp_path,
):
    out, report = _update(
        tmp_path,
        [_table("R-1"), paragraph(""), _table("R-2")],
        [_requirement("R-1")],
    )
    assert report.deleted == ["R-2"]
    assert list(_requirements(out, TrackedChangesMode.ACCEPT)) == ["R-1"]
    assert list(_requirements(out, TrackedChangesMode.REJECT)) == ["R-1", "R-2"]


def test_007_rejecting_everything_restores_the_base_whatever_the_edits(
    tmp_path,
):
    base_blocks = [
        paragraph("Chapter", style="Heading1"),
        _table("R-1", title="A", text="x"),
        paragraph(""),
        _table("R-2", title="B", version="V1"),
        paragraph(""),
        _table("R-4"),
    ]
    items = [
        ExportSection(1, "Chapter"),
        _requirement("R-1", title="A2", text="y\n\nz"),
        _requirement("R-3"),
        _requirement("R-4", version="V9", note="Mine."),
    ]
    out, _ = _update(tmp_path, base_blocks, items)
    base = _base(tmp_path, base_blocks)
    before = DocxReader.read(base, TrackedChangesMode.REJECT)
    after = DocxReader.read(out, TrackedChangesMode.REJECT)
    assert _flatten(after) == _flatten(before)


def _flatten(blocks) -> List[str]:  # type: ignore[no-untyped-def]
    texts: List[str] = []
    for block_ in blocks:
        if isinstance(block_, DocxTable):
            for row_ in block_.rows:
                for cell_ in row_:
                    texts += [p_.text for p_ in cell_.paragraphs]
        elif len(block_.text.strip()) > 0:
            texts.append(block_.text)
    return [t_ for t_ in texts if len(t_.strip()) > 0]


def test_008_accepting_everything_gives_the_model(tmp_path):
    base_blocks = [_table("R-1", title="A"), paragraph(""), _table("R-2")]
    items = [
        _requirement("R-1", title="A2", text="y", note="N."),
        _requirement("R-3", title="C"),
    ]
    out, _ = _update(tmp_path, base_blocks, items)
    accepted = _requirements(out, TrackedChangesMode.ACCEPT)
    assert list(accepted) == ["R-1", "R-3"]
    assert accepted["R-1"][1] == "A2"
    assert accepted["R-1"][5] == "Note : N."
    assert accepted["R-3"][1] == "C"


def test_009_revision_ids_are_unique_and_do_not_clash_with_the_base(tmp_path):
    foreign_edit = (
        '<w:p><w:ins w:id="40" w:author="x" w:date="2026-01-01T00:00:00Z">'
        "<w:r><w:t>old edit</w:t></w:r></w:ins></w:p>"
    )
    base_blocks = [foreign_edit, _table("R-1", title="A")]
    out, _ = _update(
        tmp_path,
        base_blocks,
        [_requirement("R-1", title="B"), _requirement("R-2")],
    )
    identifiers = re.findall(r'<w:(?:ins|del) w:id="(\d+)"', _document_xml(out))
    assert len(identifiers) == len(set(identifiers))
    new_ids = [int(i_) for i_ in identifiers if int(i_) != 40]
    assert min(new_ids) > 40


def test_010_the_base_package_is_kept_apart_from_the_document(tmp_path):
    base = _base(tmp_path, [_table("R-1")])
    with zipfile.ZipFile(base, "a") as package_:
        package_.writestr("word/footer1.xml", "<w:ftr/>")
    package, _ = DocxUpdater.update(
        base, [_requirement("R-1", title="N")], PROFILE
    )
    assert package["word/footer1.xml"] == b"<w:ftr/>"
