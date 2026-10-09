import os
import re
import zipfile
from typing import List

from strictdoc.backend.docx.docx_profile import (
    DocxProfile,
    DocxRequirementTable,
)
from strictdoc.backend.docx.export.docx_template import (
    DocxTemplate,
    clean_skeleton,
    split_top_level,
)
from strictdoc.backend.docx.export.sdoc_to_docx_generator import (
    DocxGenerator,
    ExportRequirement,
    ExportSection,
    ExportText,
    items_from_document,
)
from strictdoc.backend.docx.import_.docx_reader import (
    DocxParagraph,
    DocxReader,
    DocxTable,
    TrackedChangesMode,
)
from strictdoc.backend.docx.import_.docx_to_sdoc_converter import (
    DocxToSDocConverter,
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
)


def _requirement(uid="R-1", **overrides) -> ExportRequirement:
    values = {
        "uid": uid,
        "title": "A title",
        "statement": "The system shall work.",
        "fields": {"VERSION": "V1", "LINKED_REQ": "-"},
        "note": "",
    }
    values.update(overrides)
    return ExportRequirement(**values)  # type: ignore[arg-type]


def _generate(tmp_path, items, template=None) -> str:
    template = template or DocxTemplate.minimal(PROFILE)
    package = DocxGenerator.generate(items, PROFILE, template)
    path = os.path.join(str(tmp_path), "out.docx")
    DocxGenerator.write(package, path)
    return path


def _read(path: str) -> list:  # type: ignore[type-arg]
    return DocxReader.read(path, TrackedChangesMode.ACCEPT)


def test_001_sections_text_and_requirements_are_written(tmp_path):
    path = _generate(
        tmp_path,
        [
            ExportSection(1, "Intro"),
            ExportText("Hello **bold**."),
            ExportSection(2, "Detail"),
            _requirement(),
        ],
    )
    blocks = _read(path)
    paragraphs = [b_ for b_ in blocks if isinstance(b_, DocxParagraph)]
    assert [(p_.style, p_.text) for p_ in paragraphs[:3]] == [
        ("Heading1", "Intro"),
        ("", "Hello bold."),
        ("Heading2", "Detail"),
    ]
    assert paragraphs[1].rst == "Hello **bold**."
    requirement_table = [b_ for b_ in blocks if isinstance(b_, DocxTable)][0]
    texts = [
        [" ".join(p_.text for p_ in c_.paragraphs) for c_ in r_]
        for r_ in requirement_table.rows
    ]
    assert texts[0] == ["R-1"]
    assert texts[1] == ["A title"]
    assert texts[2] == ["Version:", "V1"]
    assert texts[3] == ["Linked Req:", "-"]
    assert texts[4] == ["The system shall work."]
    assert texts[5] == ["Note :"]


def test_002_a_deeper_section_than_the_profile_uses_the_deepest_style(tmp_path):
    path = _generate(tmp_path, [ExportSection(5, "Deep")])
    assert _read(path)[0].style == "Heading2"


def test_003_the_note_follows_its_label(tmp_path):
    path = _generate(tmp_path, [_requirement(note="See annex.")])
    note_cell = _read(path)[0].rows[5][0]
    assert [p_.text for p_ in note_cell.paragraphs] == ["Note : See annex."]


def test_004_special_characters_are_escaped(tmp_path):
    path = _generate(
        tmp_path,
        [_requirement(title="A & B <c>", statement="x < y & z")],
    )
    table_ = _read(path)[0]
    assert table_.rows[1][0].paragraphs[0].text == "A & B <c>"
    assert table_.rows[4][0].paragraphs[0].text == "x < y & z"


def test_005_a_list_table_becomes_a_word_table(tmp_path):
    rst = ".. list-table::\n\n   * - a\n     - b\n   * - c\n     - d"
    path = _generate(tmp_path, [ExportText(rst)])
    table_ = _read(path)[0]
    assert [[c_.paragraphs[0].text for c_ in r_] for r_ in table_.rows] == [
        ["a", "b"],
        ["c", "d"],
    ]


def test_006_round_trip_import_export_import_is_stable(tmp_path):
    source = os.path.join(str(tmp_path), "source.docx")
    write_docx(
        source,
        [
            paragraph("Chapter", style="Heading1"),
            paragraph("Intro text."),
            paragraph("one", list_item=True),
            paragraph("two", list_item=True),
            table(row(cell(paragraph("h")), cell(paragraph("i")))),
            paragraph("Sub", style="Heading2"),
            table(
                row(cell(paragraph("R-1", style="ReqId"))),
                row(cell(paragraph("First", style="ReqTitle"))),
                row(cell(paragraph("Version:")), cell(paragraph("V1"))),
                row(cell(paragraph("Linked Req:")), cell(paragraph("-"))),
                row(
                    cell(
                        paragraph("Shall A.", style="ReqText"),
                        paragraph("- part", style="ReqText"),
                    )
                ),
                row(cell(paragraph("Note : n1"))),
            ),
            table(
                row(cell(paragraph("R-2", style="ReqId"))),
                row(cell(paragraph("Second", style="ReqTitle"))),
                row(cell(paragraph("Version:")), cell(paragraph("V0"))),
                row(cell(paragraph("Linked Req:")), cell(paragraph("R-1"))),
                row(cell(paragraph("Shall B.", style="ReqText"))),
                row(cell(paragraph("Note :"))),
            ),
        ],
    )
    first_text, _ = DocxToSDocConverter.build_sdoc_text(
        _read(source), PROFILE, "Doc"
    )
    document = DocxToSDocConverter.parse(first_text)
    layout = PROFILE.requirement_table
    assert layout is not None
    generated = _generate(tmp_path, items_from_document(document, layout))
    second_text, _ = DocxToSDocConverter.build_sdoc_text(
        _read(generated), PROFILE, "Doc"
    )
    assert second_text == first_text


# ---- templates ---------------------------------------------------------------

TEMPLATE_BODY = (
    '<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>Cover</w:t></w:r></w:p>'
    "<w:sdt><w:sdtContent><w:p><w:r>"
    '<w:fldChar w:fldCharType="begin"/></w:r><w:r>'
    '<w:instrText xml:space="preserve"> TOC \\o "1-3" </w:instrText></w:r><w:r>'
    '<w:fldChar w:fldCharType="end"/></w:r></w:p></w:sdtContent></w:sdt>'
    '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Old chapter</w:t></w:r></w:p>'
    "<w:tbl><w:tblPr/><w:tblGrid/>"
    '<w:tr><w:trPr><w:ins w:id="1" w:author="x" w:date="d"/></w:trPr><w:tc>'
    '<w:p w14:paraId="AAAAAAAA"><w:pPr><w:pStyle w:val="ReqId"/>'
    '<w:shd w:val="clear" w:fill="FF0000"/></w:pPr>'
    '<w:ins w:id="2" w:author="x" w:date="d"><w:r><w:rPr><w:color w:val="00FF00"/>'
    "</w:rPr><w:t>OLD-ID</w:t></w:r></w:ins></w:p></w:tc></w:tr>"
    '<w:tr><w:tc><w:p><w:pPr><w:pStyle w:val="ReqTitle"/></w:pPr><w:r><w:t>old</w:t></w:r></w:p></w:tc></w:tr>'
    "<w:tr><w:tc><w:p><w:r><w:t>Version:</w:t></w:r></w:p></w:tc>"
    "<w:tc><w:p><w:r><w:t>old</w:t></w:r></w:p></w:tc></w:tr>"
    "<w:tr><w:tc><w:p><w:r><w:t>Linked Req:</w:t></w:r></w:p></w:tc>"
    "<w:tc><w:p/></w:tc></w:tr>"
    '<w:tr><w:tc><w:p><w:pPr><w:pStyle w:val="ReqText"/></w:pPr><w:r><w:t>old text</w:t></w:r></w:p></w:tc></w:tr>'
    "<w:tr><w:tc><w:p><w:r><w:t>Note :</w:t></w:r></w:p></w:tc></w:tr>"
    "</w:tbl>"
    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>'
)


def _write_template(path: str) -> None:
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main" xmlns:w14="http://schemas.microsoft.com/'
        f'office/word/2010/wordml"><w:body>{TEMPLATE_BODY}</w:body></w:document>'
    )
    settings = (
        '<w:settings xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:zoom w:percent="100"/>'
        "<w:compat/></w:settings>"
    )
    with zipfile.ZipFile(path, "w") as package_:
        package_.writestr("word/document.xml", document)
        package_.writestr("word/settings.xml", settings)
        package_.writestr("word/footer1.xml", "<w:ftr/>")


def test_007_front_matter_and_table_of_contents_are_kept(tmp_path):
    template_path = os.path.join(str(tmp_path), "template.docx")
    _write_template(template_path)
    template = DocxTemplate.load(template_path, PROFILE)
    assert template.has_table_of_contents is True
    out = _generate(tmp_path, [ExportSection(1, "New")], template)
    xml = zipfile.ZipFile(out).read("word/document.xml").decode()
    assert "Cover" in xml and "TOC" in xml
    assert "Old chapter" not in xml and "OLD-ID" not in xml
    assert "New" in xml
    assert 'w:fldCharType="begin" w:dirty="true"' in xml
    assert "<w:pgSz" in xml


def test_008_the_output_requests_a_field_update_and_keeps_other_parts(tmp_path):
    template_path = os.path.join(str(tmp_path), "template.docx")
    _write_template(template_path)
    template = DocxTemplate.load(template_path, PROFILE)
    out = _generate(tmp_path, [], template)
    package = zipfile.ZipFile(out)
    settings = package.read("word/settings.xml").decode()
    assert settings.index("updateFields") < settings.index("<w:compat/>")
    assert package.read("word/footer1.xml") == b"<w:ftr/>"


def test_009_the_requirement_keeps_the_look_of_the_template_table(tmp_path):
    template_path = os.path.join(str(tmp_path), "template.docx")
    _write_template(template_path)
    template = DocxTemplate.load(template_path, PROFILE)
    out = _generate(tmp_path, [_requirement("NEW-1")], template)
    xml = zipfile.ZipFile(out).read("word/document.xml").decode()
    assert 'w:fill="FF0000"' in xml  # paragraph shading of the id cell
    assert 'w:color w:val="00FF00"' in xml  # run color of the id
    assert "NEW-1" in xml
    assert "<w:ins " not in xml  # the tracked wrappers of the template are gone
    assert "w14:paraId" not in xml


def test_010_two_requirements_do_not_share_text(tmp_path):
    template_path = os.path.join(str(tmp_path), "template.docx")
    _write_template(template_path)
    template = DocxTemplate.load(template_path, PROFILE)
    out = _generate(
        tmp_path,
        [_requirement("A-1", title="TA"), _requirement("B-2", title="TB")],
        template,
    )
    tables = [b_ for b_ in _read(out) if isinstance(b_, DocxTable)]
    assert [t_.rows[0][0].paragraphs[0].text for t_ in tables] == ["A-1", "B-2"]
    assert [t_.rows[1][0].paragraphs[0].text for t_ in tables] == ["TA", "TB"]


def test_011_split_top_level_keeps_nested_structures_together():
    chunks: List[str] = split_top_level(
        "<w:p><w:r/></w:p><w:sdt><w:sdtContent><w:p/><w:tbl><w:tr><w:tc>"
        "<w:p/></w:tc></w:tr></w:tbl></w:sdtContent></w:sdt><w:p/>"
        '<w:bookmarkEnd w:id="1"/><w:sectPr><w:pgSz/></w:sectPr>'
    )
    assert [c_[:6] for c_ in chunks] == [
        "<w:p><",
        "<w:sdt",
        "<w:p/>",
        "<w:boo",
        "<w:sec",
    ]


def test_012_clean_skeleton_unwraps_insertions_and_drops_ids():
    cleaned = clean_skeleton(
        '<w:tbl><w:tr w:rsidR="00AA"><w:trPr><w:ins w:id="1" w:author="a" '
        'w:date="d"/></w:trPr><w:tc><w:p w14:paraId="BB" w14:textId="CC">'
        '<w:ins w:id="2" w:author="a" w:date="d"><w:r><w:t>x</w:t></w:r></w:ins>'
        '<w:del w:id="3" w:author="a" w:date="d"><w:r><w:delText>y</w:delText>'
        "</w:r></w:del></w:p></w:tc></w:tr></w:tbl>"
    )
    assert "w:ins" not in cleaned and "w:del" not in cleaned
    assert "paraId" not in cleaned and "rsid" not in cleaned
    assert re.search(r"<w:t>x</w:t>", cleaned) is not None


def test_013_an_empty_self_closing_value_cell_gets_exactly_one_paragraph(
    tmp_path,
):
    template_path = os.path.join(str(tmp_path), "template.docx")
    _write_template(template_path)
    template = DocxTemplate.load(template_path, PROFILE)
    out = _generate(
        tmp_path, [_requirement(fields={"LINKED_REQ": "R-9"})], template
    )
    table_ = [b_ for b_ in _read(out) if isinstance(b_, DocxTable)][0]
    linked_cell = table_.rows[3][1]
    assert [p_.text for p_ in linked_cell.paragraphs] == ["R-9"]


def test_014_the_sample_note_of_the_template_never_leaks_into_a_requirement(
    tmp_path,
):
    template_path = os.path.join(str(tmp_path), "template.docx")
    _write_template(template_path)
    with zipfile.ZipFile(template_path) as package_:
        parts = {name_: package_.read(name_) for name_ in package_.namelist()}
    document = parts["word/document.xml"].decode()
    document = document.replace(
        "<w:tc><w:p><w:r><w:t>Note :</w:t></w:r></w:p></w:tc>",
        "<w:tc><w:p><w:r><w:t>Note :</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>SAMPLE NOTE</w:t></w:r></w:p></w:tc>",
    )
    parts["word/document.xml"] = document.encode()
    with zipfile.ZipFile(template_path, "w") as package_:
        for name_, data_ in parts.items():
            package_.writestr(name_, data_)
    template = DocxTemplate.load(template_path, PROFILE)
    out = _generate(
        tmp_path,
        [_requirement(note=""), _requirement("R-2", note="Mine.")],
        template,
    )
    tables = [b_ for b_ in _read(out) if isinstance(b_, DocxTable)]
    notes = [[p_.text for p_ in t_.rows[5][0].paragraphs] for t_ in tables]
    assert notes == [["Note :"], ["Note : Mine."]]
