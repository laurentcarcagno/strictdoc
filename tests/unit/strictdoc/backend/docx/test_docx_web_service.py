import io
import os
import zipfile

import pytest

from strictdoc.backend.docx.docx_web_service import (
    MAX_UPLOAD_BYTES,
    attach_meta,
    check_upload,
    export_fresh,
    export_update,
    import_upload,
    safe_stem,
)
from strictdoc.backend.docx.import_.docx_reader import TrackedChangesMode
from strictdoc.core.project_config import ProjectConfig
from strictdoc.helpers.exception import StrictDocException
from tests.unit.strictdoc.backend.docx.docx_builder import (
    cell,
    paragraph,
    row,
    table,
    write_docx,
)

PROFILE_SOURCE = """
from strictdoc.backend.docx.docx_profile import (
    DocxProfile,
    DocxRequirementTable,
)


def create_profile():
    return DocxProfile(
        heading_styles={"Heading1": 1},
        requirement_table=DocxRequirementTable(
            id_style="ReqId",
            title_style="ReqTitle",
            meta_rows={"Version:": "VERSION"},
            text_style="ReqText",
            note_label="Note",
        ),
    )
"""


def _requirement_table(uid: str, text: str) -> str:
    return table(
        row(cell(paragraph(uid, style="ReqId"))),
        row(cell(paragraph("Title " + uid, style="ReqTitle"))),
        row(cell(paragraph("Version:")), cell(paragraph("V1"))),
        row(cell(paragraph(text, style="ReqText"))),
        row(cell(paragraph("Note"))),
    )


@pytest.fixture
def project_config(tmp_path) -> ProjectConfig:
    profile_path = os.path.join(str(tmp_path), "profile.py")
    with open(profile_path, "w", encoding="utf8") as file_:
        file_.write(PROFILE_SOURCE)
    config = ProjectConfig.default_config()
    config.docx_profile = profile_path
    return config


@pytest.fixture
def word_bytes(tmp_path) -> bytes:
    path = os.path.join(str(tmp_path), "spec.docx")
    write_docx(
        path,
        [
            paragraph("Section", style="Heading1"),
            _requirement_table("R-1", "The system shall start."),
            _requirement_table("R-2", "The system shall stop."),
        ],
    )
    with open(path, "rb") as file_:
        return file_.read()


def _import(word_bytes, project_config, tmp_path, name="My spec.docx"):
    return import_upload(
        word_bytes,
        name,
        project_config,
        str(tmp_path),
        TrackedChangesMode.ACCEPT,
        overwrite=False,
    )


def test_001_safe_stem_keeps_only_safe_characters():
    assert safe_stem("My spec (v2).docx") == "My_spec__v2"
    assert safe_stem("../../etc/passwd.docx") == "passwd"
    assert safe_stem("C:\\dir\\file.docx") == "file"
    assert safe_stem("") == "word_document"
    assert safe_stem(None) == "word_document"
    assert safe_stem("???.docx") == "word_document"


def test_002_check_upload_rejects_what_is_not_a_word_file():
    with pytest.raises(StrictDocException, match="empty"):
        check_upload(b"")
    with pytest.raises(StrictDocException, match="not a Word"):
        check_upload(b"plain text")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package_:
        package_.writestr("other.txt", "x")
    with pytest.raises(StrictDocException, match="word/document.xml"):
        check_upload(buffer.getvalue())
    with pytest.raises(StrictDocException, match="larger"):
        check_upload(b"0" * (MAX_UPLOAD_BYTES + 1))


def test_003_import_upload_reports_and_writes_nothing(
    word_bytes, project_config, tmp_path
):
    result = _import(word_bytes, project_config, tmp_path)
    assert result.stem == "My_spec"
    assert result.report.requirement_count == 2
    assert result.report.section_count == 1
    assert [
        name_ for name_ in os.listdir(str(tmp_path)) if "sdoc" in name_
    ] == []


def test_004_attach_meta_gives_the_writer_a_path(
    word_bytes, project_config, tmp_path
):
    result = _import(word_bytes, project_config, tmp_path)
    full_path = attach_meta(result.document, str(tmp_path), result.stem)
    assert full_path == os.path.join(str(tmp_path), "My_spec.sdoc")
    assert result.document.meta.input_doc_full_path == full_path


def test_005_export_fresh_gives_a_word_file_that_imports_back(
    word_bytes, project_config, tmp_path
):
    document = _import(word_bytes, project_config, tmp_path).document
    exported = export_fresh(document, project_config)
    check_upload(exported)
    again = _import(exported, project_config, tmp_path).report
    assert again.requirement_count == 2


def test_006_export_update_reports_the_differences_only(
    word_bytes, project_config, tmp_path
):
    document = _import(word_bytes, project_config, tmp_path).document
    _, unchanged = export_update(document, word_bytes, project_config)
    assert (len(unchanged.added), len(unchanged.changed)) == (0, 0)
    assert unchanged.unchanged == 2

    edited_path = os.path.join(str(tmp_path), "edited.docx")
    write_docx(
        edited_path,
        [
            paragraph("Section", style="Heading1"),
            _requirement_table("R-1", "The system shall start fast."),
            _requirement_table("R-2", "The system shall stop."),
        ],
    )
    with open(edited_path, "rb") as file_:
        edited = _import(file_.read(), project_config, tmp_path).document
    changed_bytes, changed = export_update(edited, word_bytes, project_config)
    assert changed.changed == {"R-1": ["STATEMENT"]}
    assert changed.unchanged == 1
    check_upload(changed_bytes)


def test_007_export_update_rejects_a_base_that_is_not_word(
    word_bytes, project_config, tmp_path
):
    document = _import(word_bytes, project_config, tmp_path).document
    with pytest.raises(StrictDocException):
        export_update(document, b"nope", project_config)
