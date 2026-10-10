import os
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Dict, List

from strictdoc.backend.docx.docx_profile import (
    DocxProfile,
    DocxRequirementTable,
)
from strictdoc.backend.docx.export.docx_comments import (
    ExportComment,
    comment_fingerprint,
)
from strictdoc.backend.docx.export.docx_template import DocxTemplate
from strictdoc.backend.docx.export.sdoc_to_docx_generator import (
    DocxGenerator,
    ExportRequirement,
    items_from_document,
)
from strictdoc.backend.docx.import_.docx_to_sdoc_converter import (
    DocxToSDocConverter,
)

PROFILE = DocxProfile(
    heading_styles={"Heading1": 1},
    requirement_table=DocxRequirementTable(
        id_style="ReqId",
        title_style="ReqTitle",
        meta_rows={"Version:": "VERSION"},
        text_style="ReqText",
        note_label="Note",
    ),
)
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
W15 = "{http://schemas.microsoft.com/office/word/2012/wordml}"


def _comment(key="R1-a1", body="Not testable.", **overrides) -> ExportComment:
    values = {
        "key": key,
        "author": "anna.durand",
        "date": "2026-10-10T12:00:00Z",
        "body": body,
    }
    values.update(overrides)
    return ExportComment(**values)  # type: ignore[arg-type]


def _requirement(uid: str, *comments: ExportComment) -> ExportRequirement:
    return ExportRequirement(
        uid=uid,
        title="T " + uid,
        statement="The system shall work.",
        fields={"VERSION": "V1"},
        comments=list(comments),
    )


def _package(tmp_path, items) -> Dict[str, bytes]:
    package = DocxGenerator.generate(
        items, PROFILE, DocxTemplate.minimal(PROFILE)
    )
    path = os.path.join(str(tmp_path), "out.docx")
    DocxGenerator.write(package, path)
    with zipfile.ZipFile(path) as package_:
        return {name_: package_.read(name_) for name_ in package_.namelist()}


def test_001_a_comment_becomes_a_native_word_comment(tmp_path):
    parts = _package(tmp_path, [_requirement("R-1", _comment())])
    comments = ET.fromstring(parts["word/comments.xml"])
    (comment,) = comments.findall(f"{W}comment")
    assert comment.get(f"{W}author") == "anna.durand"
    assert comment.get(f"{W}date") == "2026-10-10T12:00:00Z"
    assert comment.get(f"{W}initials") == "AD"
    assert "Not testable." in "".join(comment.itertext())

    relationships = parts["word/_rels/document.xml.rels"].decode()
    assert 'Target="comments.xml"' in relationships
    assert (
        'PartName="/word/comments.xml"' in parts["[Content_Types].xml"].decode()
    )


def test_002_the_range_and_the_reference_use_the_comment_id(tmp_path):
    parts = _package(tmp_path, [_requirement("R-1", _comment())])
    xml = parts["word/document.xml"].decode()
    assert "@@" not in xml
    start = re.search(r'<w:commentRangeStart w:id="(\d+)"/>', xml)
    end = re.search(r'<w:commentRangeEnd w:id="(\d+)"/>', xml)
    reference = re.search(r'<w:commentReference w:id="(\d+)"/>', xml)
    assert start and end and reference
    assert start.group(1) == end.group(1) == reference.group(1) == "0"
    # The range is in the paragraph of the identifier, around its text.
    paragraph = re.search(r"<w:p[ >].*?</w:p>", xml, re.S).group(0)
    assert paragraph.index("commentRangeStart") < paragraph.index("R-1")
    assert paragraph.index("R-1") < paragraph.index("commentRangeEnd")


def test_003_ids_are_unique_across_requirements_and_comments(tmp_path):
    parts = _package(
        tmp_path,
        [
            _requirement(
                "R-1", _comment("R1-a"), _comment("R1-b", body="Second.")
            ),
            _requirement("R-2", _comment("R2-a", author="paul")),
        ],
    )
    comments = ET.fromstring(parts["word/comments.xml"])
    ids = [c.get(f"{W}id") for c in comments.findall(f"{W}comment")]
    assert ids == ["0", "1", "2"]
    xml = parts["word/document.xml"].decode()
    assert sorted(re.findall(r'commentReference w:id="(\d+)"', xml)) == ids


def test_004_a_resolved_comment_is_marked_done(tmp_path):
    parts = _package(
        tmp_path,
        [
            _requirement(
                "R-1", _comment("R1-a"), _comment("R1-b", resolved=True)
            )
        ],
    )
    extended = ET.fromstring(parts["word/commentsExtended.xml"])
    flags = [e.get(f"{W15}done") for e in extended]
    assert flags == ["0", "1"]
    # Each flag points at the paragraph of its comment.
    comments = ET.fromstring(parts["word/comments.xml"]).findall(f"{W}comment")
    paragraph_ids = [
        c.findall(f"{W}p")[-1].get(
            "{http://schemas.microsoft.com/office/word/2010/wordml}paraId"
        )
        for c in comments
    ]
    assert paragraph_ids == [e.get(f"{W15}paraId") for e in extended]
    assert "commentsExtended" in parts["word/_rels/document.xml.rels"].decode()


def test_005_without_comments_the_package_is_unchanged(tmp_path):
    parts = _package(tmp_path, [_requirement("R-1")])
    assert "word/comments.xml" not in parts
    assert "word/commentsExtended.xml" not in parts
    assert "comments" not in parts["word/_rels/document.xml.rels"].decode()


def test_006_a_markdown_comment_keeps_its_formatting(tmp_path):
    parts = _package(
        tmp_path,
        [
            _requirement(
                "R-1",
                _comment(
                    body="Use **bold** and a list:\n\n- one\n- two",
                    markup="Markdown",
                ),
            )
        ],
    )
    xml = parts["word/comments.xml"].decode()
    assert "<w:b/>" in xml
    comment = ET.fromstring(parts["word/comments.xml"]).find(f"{W}comment")
    paragraphs = ["".join(p_.itertext()) for p_ in comment.findall(f"{W}p")]
    assert paragraphs[-2:] == ["- one", "- two"]


def test_007_every_part_is_well_formed_and_targets_exist(tmp_path):
    parts = _package(
        tmp_path,
        [_requirement("R-1", _comment("a"), _comment("b", resolved=True))],
    )
    for name_, data_ in parts.items():
        if name_.endswith((".xml", ".rels")):
            ET.fromstring(data_)
    relationships = parts["word/_rels/document.xml.rels"].decode()
    for target in re.findall(r'Target="([A-Za-z]+\.xml)"', relationships):
        if target in ("comments.xml", "commentsExtended.xml"):
            assert f"word/{target}" in parts


SOURCE = """[DOCUMENT]
TITLE: Spec
OPTIONS:
  ENABLE_MID: True

[REQUIREMENT]
MID: a5c6b14d5ee443149687fb9be69a7ede
UID: R-1
STATEMENT: >>>
The system shall start.
<<<
COMMENT: >>>
.. sdoc-comment: id=c1 author=anna date=2026-10-10T12%3A00%3A00Z status=open

Open remark.
<<<
COMMENT: >>>
.. sdoc-comment: id=c2 author=paul date=2026-10-10T13%3A00%3A00Z status=resolved resolved_by=anna

Resolved remark.
<<<
COMMENT: >>>
A legacy remark.
<<<
"""


def _items(mode: str) -> List[ExportComment]:
    document = DocxToSDocConverter.parse(SOURCE)
    (requirement,) = [
        item_
        for item_ in items_from_document(
            document,
            PROFILE.requirement_table,
            mode,  # type: ignore[arg-type]
        )
        if isinstance(item_, ExportRequirement)
    ]
    return requirement.comments


def test_008_the_profile_decides_which_comments_go_to_word():
    assert _items("none") == []
    assert [c.body for c in _items("open")] == [
        "Open remark.",
        "A legacy remark.",
    ]
    everything = _items("all")
    assert [c.body for c in everything] == [
        "Open remark.",
        "Resolved remark.",
        "A legacy remark.",
    ]
    assert [c.resolved for c in everything] == [False, True, False]
    assert everything[0].author == "anna"
    assert everything[0].date == "2026-10-10T12:00:00Z"
    # A legacy comment has no author and no date; its key is still unique.
    assert everything[2].author == "" and everything[2].date == ""
    assert len({c.key for c in everything}) == 3


def test_009_the_fingerprint_ignores_spaces_case_and_seconds():
    first = comment_fingerprint("Anna", "2026-10-10T12:00:05Z", "A  B\nC")
    second = comment_fingerprint("anna ", "2026-10-10T12:00:59Z", "A B C")
    assert first == second
    assert first != comment_fingerprint("anna", "2026-10-10T12:01:00Z", "A B C")
    assert first != comment_fingerprint("anna", "2026-10-10T12:00:00Z", "A B D")


def test_010_a_legacy_comment_gets_the_unknown_author_in_word(tmp_path):
    parts = _package(
        tmp_path,
        [_requirement("R-1", _comment("R1-legacy", author="", date=""))],
    )
    comment = ET.fromstring(parts["word/comments.xml"]).find(f"{W}comment")
    assert comment.get(f"{W}author") == "Unknown"
    assert comment.get(f"{W}date") is None
