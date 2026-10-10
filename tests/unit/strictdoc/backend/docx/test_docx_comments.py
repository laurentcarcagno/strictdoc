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
    ExportText,
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


# ---- update and reading back (step C5) ---------------------------------------

from strictdoc.backend.docx.export.docx_tracked_update import DocxUpdater  # noqa: E402
from strictdoc.backend.docx.import_.docx_reader import (  # noqa: E402
    DocxReader,
    TrackedChangesMode,
    read_word_comments,
)
from strictdoc.backend.docx.import_.sdoc_requirement_blocks import (  # noqa: E402
    build_carry_over,
)
from strictdoc.features.comments.model import parse_comment  # noqa: E402


def _write(package: Dict[str, bytes], path: str) -> str:
    DocxGenerator.write(package, path)
    return path


def _base(tmp_path, items, name="base.docx") -> str:
    package = DocxGenerator.generate(
        items, PROFILE, DocxTemplate.minimal(PROFILE)
    )
    return _write(package, os.path.join(str(tmp_path), name))


def _document_xml(path: str) -> bytes:
    with zipfile.ZipFile(path) as package_:
        return package_.read("word/document.xml")


def test_011_update_adds_a_new_comment_to_an_unchanged_requirement(tmp_path):
    base = _base(tmp_path, [_requirement("R-1")])
    with_comment = [_requirement("R-1", _comment())]
    package, report = DocxUpdater.update(base, with_comment, PROFILE)
    assert report.comments_added == 1
    assert report.changed == {}
    assert "Comments added: 1" in report.format()
    updated = _write(package, os.path.join(str(tmp_path), "updated.docx"))
    assert [c.author for c in read_word_comments(updated).values()] == [
        "anna.durand"
    ]
    assert b"commentReference" in _document_xml(updated)

    # The text of the document did not change.
    def rows(path: str):
        return [
            b_.rows
            for b_ in DocxReader.read(path, TrackedChangesMode.REJECT)
            if hasattr(b_, "rows")
        ]

    assert rows(updated) == rows(base)


def test_012_a_second_update_finds_nothing_to_do(tmp_path):
    items = [_requirement("R-1", _comment(), _comment("b", body="Another."))]
    base = _base(tmp_path, [_requirement("R-1")])
    package, _ = DocxUpdater.update(base, items, PROFILE)
    updated = _write(package, os.path.join(str(tmp_path), "updated.docx"))
    again, report = DocxUpdater.update(updated, items, PROFILE)
    assert report.comments_added == 0 and report.changed == {}
    assert again["word/document.xml"] == _document_xml(updated)
    assert again["word/comments.xml"] == zipfile.ZipFile(updated).read(
        "word/comments.xml"
    )


def test_013_update_keeps_the_comments_that_people_added_in_word(tmp_path):
    items = [_requirement("R-1", _comment())]
    base = _base(tmp_path, items)
    with zipfile.ZipFile(base) as package_:
        parts = {name_: package_.read(name_) for name_ in package_.namelist()}
    # A customer adds a comment in Word: comment 7, anchored in the table.
    parts["word/comments.xml"] = parts["word/comments.xml"].replace(
        b"</w:comments>",
        b'<w:comment w:id="7" w:author="Client" w:date="2026-10-12T09:30:00Z" '
        b'w:initials="C"><w:p><w:r><w:t>Please explain.</w:t></w:r></w:p>'
        b"</w:comment></w:comments>",
    )
    parts["word/document.xml"] = parts["word/document.xml"].replace(
        b"</w:p>",
        b'<w:r><w:commentReference w:id="7"/></w:r></w:p>',
        1,
    )
    customer = _write(parts, os.path.join(str(tmp_path), "customer.docx"))

    package, report = DocxUpdater.update(customer, items, PROFILE)
    assert report.comments_added == 0
    updated = _write(package, os.path.join(str(tmp_path), "updated.docx"))
    comments = read_word_comments(updated)
    assert sorted(c.author for c in comments.values()) == [
        "Client",
        "anna.durand",
    ]


def test_014_a_requirement_added_by_the_update_brings_its_comments(tmp_path):
    base = _base(tmp_path, [_requirement("R-1")])
    items = [
        _requirement("R-1"),
        _requirement("R-2", _comment("R2-a", body="New one.")),
    ]
    package, report = DocxUpdater.update(base, items, PROFILE)
    assert report.added == ["R-2"] and report.comments_added == 1
    updated = _write(package, os.path.join(str(tmp_path), "updated.docx"))
    (comment,) = read_word_comments(updated).values()
    assert comment.text == "New one."
    assert b"@@" not in _document_xml(updated)


def _word_with_comments(tmp_path) -> str:
    return _base(
        tmp_path,
        [
            _requirement(
                "R-1",
                _comment("a", body="Open remark.", resolved=False),
                _comment(
                    "b", body="Done remark.", resolved=True, author="paul"
                ),
            )
        ],
    )


def test_015_the_reader_finds_the_comments_of_each_requirement(tmp_path):
    path = _word_with_comments(tmp_path)
    comments = read_word_comments(path)
    assert sorted((c.author, c.text, c.done) for c in comments.values()) == [
        ("anna.durand", "Open remark.", False),
        ("paul", "Done remark.", True),
    ]
    tables = [
        b
        for b in DocxReader.read(path, TrackedChangesMode.ACCEPT)
        if hasattr(b, "rows")
    ]
    assert [c.text for c in tables[0].comments] == [
        "Open remark.",
        "Done remark.",
    ]


def _import(path: str, markup: str, carry_over=None):
    profile = DocxProfile(
        heading_styles=PROFILE.heading_styles,
        requirement_table=PROFILE.requirement_table,
        markup=markup,
    )
    blocks = DocxReader.read(path, TrackedChangesMode.ACCEPT)
    return DocxToSDocConverter.build_sdoc_text(
        blocks, profile, "Spec", carry_over
    )


def _comment_values(sdoc_text: str):
    document = DocxToSDocConverter.parse(sdoc_text)
    (requirement,) = [
        n_ for n_ in document.section_contents if n_.node_type == "REQUIREMENT"
    ]
    return [
        parse_comment(f_.get_text_value())
        for f_ in requirement.get_comment_fields()
    ]


def test_016_import_writes_the_word_comments_with_their_state(tmp_path):
    path = _word_with_comments(tmp_path)
    for markup in ("RST", "Markdown"):
        sdoc_text, report = _import(path, markup)
        comments = _comment_values(sdoc_text)
        assert report.comments_added == 2
        assert [(c.author, c.body, c.status, c.source) for c in comments] == [
            ("anna.durand", "Open remark.", "open", "word"),
            ("paul", "Done remark.", "resolved", "word"),
        ]
        assert comments[0].date == "2026-10-10T12:00:00Z"
        assert "Comments read from Word: 2" in report.format()


def test_017_a_second_import_does_not_duplicate_the_comments(tmp_path):
    path = _word_with_comments(tmp_path)
    first, _ = _import(path, "Markdown")
    carry_over = build_carry_over(first, PROFILE.requirement_table)  # type: ignore[arg-type]
    second, report = _import(path, "Markdown", carry_over)
    assert report.comments_added == 0
    assert len(_comment_values(second)) == 2
    assert [c.id for c in _comment_values(second)] == [
        c.id for c in _comment_values(first)
    ]


def test_018_a_merge_keeps_the_comments_written_in_the_interface(tmp_path):
    path = _word_with_comments(tmp_path)
    first, _ = _import(path, "RST")
    web = (
        "COMMENT: >>>\n.. sdoc-comment: id=web1 author=rita "
        "date=2026-10-11T08:00:00Z status=open source=web\n\nFrom the web.\n<<<\n"
    )
    first = first.rstrip("\n") + "\n" + web
    carry_over = build_carry_over(first, PROFILE.requirement_table)  # type: ignore[arg-type]
    second, report = _import(path, "RST", carry_over)
    bodies = [c.body for c in _comment_values(second)]
    assert "From the web." in bodies
    assert bodies.count("Open remark.") == 1
    assert report.comments_added == 0


def test_019_sdoc_to_word_to_sdoc_gives_the_same_comments(tmp_path):
    source = (
        "[DOCUMENT]\nTITLE: Spec\nOPTIONS:\n  MARKUP: Markdown\n\n"
        "[REQUIREMENT]\nUID: R-1\nTITLE: T\nSTATEMENT: >>>\nText.\n<<<\n"
        "COMMENT: >>>\n<!-- sdoc-comment id=c1 author=anna "
        "date=2026-10-10T12%3A00%3A00Z status=open source=web -->\n\n"
        "Use **bold** here.\n<<<\n"
    )
    document = DocxToSDocConverter.parse(source)
    items = items_from_document(document, PROFILE.requirement_table, "all")  # type: ignore[arg-type]
    word = _base(tmp_path, items)
    carry_over = build_carry_over(source, PROFILE.requirement_table)  # type: ignore[arg-type]
    again, report = _import(word, "Markdown", carry_over)
    comments = _comment_values(again)
    assert report.comments_added == 0
    assert [(c.id, c.body) for c in comments] == [("c1", "Use **bold** here.")]


def test_a_comment_on_a_paragraph_is_anchored_on_its_first_paragraph(tmp_path):
    text = ExportText(
        "A free paragraph.", comments=[_comment("p1", body="Which text?")]
    )
    parts = _package(tmp_path, [text, _requirement("R-1")])
    xml = parts["word/document.xml"].decode()
    assert "@@" not in xml
    paragraph = re.search(r"<w:p[ >].*?</w:p>", xml, re.S).group(0)
    assert paragraph.index("commentRangeStart") < paragraph.index("A free")
    assert "Which text?" in parts["word/comments.xml"].decode()
