import os
import re
import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib
from typing import Dict, List

from strictdoc.backend.docx.docx_profile import (
    DocxProfile,
    DocxRequirementTable,
)
from strictdoc.backend.docx.export.docx_images import image_size
from strictdoc.backend.docx.export.docx_template import DocxTemplate
from strictdoc.backend.docx.export.docx_tracked_update import DocxUpdater
from strictdoc.backend.docx.export.sdoc_to_docx_generator import (
    DocxGenerator,
    ExportRequirement,
    ExportSection,
    ExportText,
)
from strictdoc.backend.docx.import_.docx_reader import (
    DocxReader,
    TrackedChangesMode,
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
    markup="Markdown",
)


def _png(width: int, height: int, color=(200, 30, 30)) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return (
            struct.pack(">I", len(data))
            + body
            + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    row = b"\x00" + bytes(color) * width
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(row * height))
        + chunk(b"IEND", b"")
    )


def _jpeg(width: int, height: int) -> bytes:
    sof = b"\x08" + struct.pack(">HH", height, width) + b"\x03\x01\x22\x00"
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof + b"\xff\xd9"
    )


def _requirement(
    statement: str, base_dir: str, uid: str = "R-1"
) -> ExportRequirement:
    return ExportRequirement(
        uid=uid,
        title="Title",
        statement=statement,
        fields={"VERSION": "V1"},
        markup="Markdown",
        base_dir=base_dir,
    )


def _generate(tmp_path, items, name="out.docx") -> str:
    package = DocxGenerator.generate(
        items, PROFILE, DocxTemplate.minimal(PROFILE)
    )
    path = os.path.join(str(tmp_path), name)
    DocxGenerator.write(package, path)
    return path


def _parts(path: str) -> Dict[str, bytes]:
    with zipfile.ZipFile(path) as package_:
        return {name_: package_.read(name_) for name_ in package_.namelist()}


def _document_xml(parts: Dict[str, bytes]) -> str:
    return parts["word/document.xml"].decode("utf8")


def _write_image(tmp_path, name: str, data: bytes) -> None:
    with open(os.path.join(str(tmp_path), name), "wb") as file_:
        file_.write(data)


def test_001_image_sizes_of_png_jpeg_and_gif_and_nothing_for_the_rest():
    assert image_size(_png(30, 20)) == ("png", 30, 20)
    assert image_size(_jpeg(64, 48)) == ("jpeg", 64, 48)
    assert image_size(b"GIF89a" + struct.pack("<HH", 5, 7) + b"\x00" * 8) == (
        "gif",
        5,
        7,
    )
    assert image_size(b"<svg xmlns='http://www.w3.org/2000/svg'/>") is None
    assert image_size(b"RIFF....WEBPVP8 ") is None
    assert image_size(b"") is None


def test_002_a_fresh_export_embeds_the_image(tmp_path):
    _write_image(tmp_path, "pic.png", _png(40, 20))
    path = _generate(
        tmp_path,
        [_requirement("Before\n\n![pic](./pic.png)\n\nAfter", str(tmp_path))],
    )
    parts = _parts(path)
    media = [name_ for name_ in parts if name_.startswith("word/media/")]
    assert len(media) == 1 and media[0].endswith(".png")
    assert parts[media[0]] == _png(40, 20)

    relationships = parts["word/_rels/document.xml.rels"].decode("utf8")
    assert re.search(r'Target="media/sdoc_[0-9a-f]+\.png"', relationships)
    assert 'Extension="png"' in parts["[Content_Types].xml"].decode("utf8")

    xml = _document_xml(parts)
    assert "<w:drawing>" in xml and "@@" not in xml
    embed = re.search(r'r:embed="(rIdSdocImage[0-9a-f]+)"', xml)
    assert embed is not None and f'Id="{embed.group(1)}"' in relationships
    assert 'name="sdoc-image:pic.png"' in xml
    # 40 x 20 pixels at 96 dpi.
    assert 'cx="381000" cy="190500"' in xml


def test_003_a_wide_image_is_scaled_to_the_page(tmp_path):
    _write_image(tmp_path, "wide.png", _png(2000, 1000))
    path = _generate(
        tmp_path, [_requirement("![w](./wide.png)", str(tmp_path))]
    )
    assert 'cx="5040000" cy="2520000"' in _document_xml(_parts(path))


def test_004_the_same_file_is_stored_once_and_pictures_have_unique_ids(
    tmp_path,
):
    _write_image(tmp_path, "pic.png", _png(10, 10))
    path = _generate(
        tmp_path,
        [
            _requirement("![a](./pic.png)\n\n![b](./pic.png)", str(tmp_path)),
            _requirement("![c](./pic.png)", str(tmp_path), uid="R-2"),
        ],
    )
    parts = _parts(path)
    assert len([n for n in parts if n.startswith("word/media/")]) == 1
    xml = _document_xml(parts)
    ids = re.findall(r'<wp:docPr id="(\d+)"', xml)
    assert len(ids) == 3 and len(set(ids)) == 3


def test_005_a_missing_or_unsupported_image_stays_text(tmp_path):
    _write_image(tmp_path, "vector.svg", b"<svg xmlns='http://x'/>")
    path = _generate(
        tmp_path,
        [
            _requirement(
                "![v](./vector.svg)\n\n![m](./missing.png)\n\n"
                "![u](http://example.org/x.png)",
                str(tmp_path),
            )
        ],
    )
    parts = _parts(path)
    xml = _document_xml(parts)
    assert "<w:drawing>" not in xml
    assert not [n for n in parts if n.startswith("word/media/")]
    for text_ in (
        "[image: vector.svg]",
        "[image: missing.png]",
        "[image: x.png]",
    ):
        assert text_ in xml


def test_006_free_text_images_are_embedded_too(tmp_path):
    _write_image(tmp_path, "pic.png", _png(8, 8))
    path = _generate(
        tmp_path,
        [
            ExportSection(1, "Section"),
            ExportText("Intro\n\n![p](./pic.png)", "Markdown", str(tmp_path)),
        ],
    )
    parts = _parts(path)
    assert "<w:drawing>" in _document_xml(parts)
    assert len([n for n in parts if n.startswith("word/media/")]) == 1


def _texts(path: str, mode: TrackedChangesMode) -> List[str]:
    texts: List[str] = []
    for block_ in DocxReader.read(path, mode):
        if hasattr(block_, "rows"):
            for row_ in block_.rows:
                for cell_ in row_:
                    texts.extend(p_.text for p_ in cell_.paragraphs)
        else:
            texts.append(block_.text)
    return texts


def test_007_reading_the_word_file_gives_the_image_as_text(tmp_path):
    _write_image(tmp_path, "pic.png", _png(8, 8))
    path = _generate(
        tmp_path, [_requirement("Text\n\n![p](./pic.png)", str(tmp_path))]
    )
    assert "[image: pic.png]" in _texts(path, TrackedChangesMode.ACCEPT)


def test_008_an_image_that_strictdoc_did_not_write_is_ignored(tmp_path):
    _write_image(tmp_path, "pic.png", _png(8, 8))
    path = _generate(tmp_path, [_requirement("![p](./pic.png)", str(tmp_path))])
    parts = _parts(path)
    parts["word/document.xml"] = (
        _document_xml(parts).replace("sdoc-image:", "Picture ").encode("utf8")
    )
    foreign = os.path.join(str(tmp_path), "foreign.docx")
    with zipfile.ZipFile(foreign, "w") as package_:
        for name_, data_ in parts.items():
            package_.writestr(name_, data_)
    assert not any(
        "[image:" in text_
        for text_ in _texts(foreign, TrackedChangesMode.ACCEPT)
    )


def test_009_update_with_an_unchanged_model_finds_no_difference(tmp_path):
    _write_image(tmp_path, "pic.png", _png(12, 12))
    items = [_requirement("Text\n\n![p](./pic.png)", str(tmp_path))]
    base = _generate(tmp_path, items, "base.docx")
    _, report = DocxUpdater.update(base, items, PROFILE)
    assert report.changed == {} and report.unchanged == 1


def test_010_update_inserts_the_image_as_a_tracked_change(tmp_path):
    _write_image(tmp_path, "pic.png", _png(12, 12))
    plain = [_requirement("Text only.", str(tmp_path))]
    base = _generate(tmp_path, plain, "base.docx")
    with_image = [_requirement("Text only.\n\n![p](./pic.png)", str(tmp_path))]
    package, report = DocxUpdater.update(base, with_image, PROFILE)
    assert report.changed == {"R-1": ["STATEMENT"]}

    xml = package["word/document.xml"].decode("utf8")
    assert re.search(r"<w:ins [^>]*>(?:(?!</w:ins>).)*<w:drawing>", xml, re.S)
    assert "@@" not in xml
    assert any(name_.startswith("word/media/") for name_ in package)

    updated = os.path.join(str(tmp_path), "updated.docx")
    DocxGenerator.write(package, updated)
    assert _texts(updated, TrackedChangesMode.REJECT) == _texts(
        base, TrackedChangesMode.REJECT
    )
    assert "[image: pic.png]" in _texts(updated, TrackedChangesMode.ACCEPT)


def test_011_the_package_with_images_opens_in_a_word_reader(tmp_path):
    # Every part is well-formed XML and the relationships point at real parts.
    _write_image(tmp_path, "pic.jpg", _jpeg(30, 20))
    _write_image(tmp_path, "pic.png", _png(30, 20))
    path = _generate(
        tmp_path,
        [_requirement("![a](./pic.jpg)\n\n![b](./pic.png)", str(tmp_path))],
    )
    parts = _parts(path)
    for name_, data_ in parts.items():
        if name_.endswith((".xml", ".rels")):
            ET.fromstring(data_)
    relationships = parts["word/_rels/document.xml.rels"].decode("utf8")
    for target in re.findall(r'Target="(media/[^"]+)"', relationships):
        assert f"word/{target}" in parts
