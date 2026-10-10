import re
import xml.etree.ElementTree as ET
from pathlib import Path

from strictdoc.backend.docx.export.docx_images import load_image
from strictdoc.features.svg.rasterizer import (
    rasterize_svg,
    svg_display_size,
)
from tests.unit.strictdoc.backend.docx.test_docx_images import (
    _document_xml,
    _generate,
    _parts,
    _requirement,
    _write_image,
)

CORPUS = Path(__file__).parents[2] / "features" / "svg" / "corpus" / "normal"
STATE_MACHINE = (CORPUS / "state_machine.svg").read_bytes()


def test_001_display_size_from_units_viewbox_and_default():
    def size(attributes: str) -> tuple:
        return svg_display_size(
            f'<svg xmlns="http://www.w3.org/2000/svg" {attributes}/>'.encode()
        )

    assert size('width="100" height="50"') == (100, 50)
    assert size('width="1in" height="2in"') == (96, 192)
    assert size('width="72pt" height="36pt"') == (96, 48)
    assert size('width="25.4mm" height="2.54cm"') == (96, 96)
    assert size('viewBox="0 0 400 120"') == (400, 120)
    assert size('width="200" viewBox="0 0 400 100"') == (200, 50)
    assert size('width="50%" height="50%"') == (300, 150)
    assert size("") == (300, 150)


def test_002_the_rasterizer_gives_a_png_of_the_asked_width():
    png = rasterize_svg(STATE_MACHINE, width_px=640)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert int.from_bytes(png[16:20], "big") == 640


def test_003_the_rasterizer_does_not_read_files_the_svg_names(tmp_path):
    secret = tmp_path / "secret.png"
    secret.write_bytes(rasterize_svg(STATE_MACHINE, width_px=20))
    hostile = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">'
        b'<image href="' + str(secret).encode() + b'" width="20" height="20"/>'
        b"</svg>"
    )
    blank = rasterize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"/>'
    )
    assert rasterize_svg(hostile) == blank


def test_004_a_fresh_export_embeds_svg_with_a_png_fallback(tmp_path):
    _write_image(tmp_path, "diagram.svg", STATE_MACHINE)
    path = _generate(
        tmp_path,
        [_requirement("Before\n\n![d](./diagram.svg)\n\nAfter", str(tmp_path))],
    )
    parts = _parts(path)
    media = sorted(n for n in parts if n.startswith("word/media/"))
    assert len(media) == 2
    assert sum(n.endswith(".svg") for n in media) == 1
    assert sum(n.endswith(".png") for n in media) == 1
    svg_part = next(n for n in media if n.endswith(".svg"))
    png_part = next(n for n in media if n.endswith(".png"))
    assert parts[png_part][:4] == b"\x89PNG"
    assert b"<script" not in parts[svg_part]

    relationships = parts["word/_rels/document.xml.rels"].decode("utf8")
    for part in (svg_part, png_part):
        assert f'Target="{part[len("word/") :]}"' in relationships
    content_types = parts["[Content_Types].xml"].decode("utf8")
    assert 'Extension="svg" ContentType="image/svg+xml"' in content_types
    assert 'Extension="png"' in content_types

    xml = _document_xml(parts)
    assert "@@" not in xml
    ET.fromstring(xml)
    assert "asvg:svgBlip" in xml
    png_id = re.search(r'<a:blip r:embed="(rId[^"]+)"', xml).group(1)
    svg_id = re.search(r'<asvg:svgBlip[^>]*r:embed="(rId[^"]+)"', xml).group(1)
    assert png_id != svg_id
    assert f'Id="{png_id}"' in relationships
    assert f'Id="{svg_id}"' in relationships
    assert 'name="sdoc-image:diagram.svg"' in xml
    # 320 x 140 pixels at 96 dpi.
    assert 'cx="3048000" cy="1333500"' in xml


def test_005_a_hostile_svg_is_cleaned_before_it_is_embedded(tmp_path):
    hostile = (
        b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"'
        b' onload="alert(1)"><script>alert(2)</script>'
        b'<rect width="10" height="10"/></svg>'
    )
    _write_image(tmp_path, "evil.svg", hostile)
    path = _generate(
        tmp_path, [_requirement("![e](./evil.svg)", str(tmp_path))]
    )
    parts = _parts(path)
    svg_part = next(n for n in parts if n.endswith(".svg"))
    assert b"script" not in parts[svg_part]
    assert b"onload" not in parts[svg_part]


def test_006_an_svg_that_cannot_be_made_safe_stays_text(tmp_path):
    _write_image(
        tmp_path,
        "bomb.svg",
        b'<!DOCTYPE svg [<!ENTITY a "x">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg"><text>&a;</text></svg>',
    )
    assert load_image(str(tmp_path / "bomb.svg")) is None
    path = _generate(
        tmp_path, [_requirement("![b](./bomb.svg)", str(tmp_path))]
    )
    assert not any(n.startswith("word/media/") for n in _parts(path))


def test_007_the_same_svg_is_stored_once(tmp_path):
    _write_image(tmp_path, "d.svg", STATE_MACHINE)
    path = _generate(
        tmp_path,
        [
            _requirement("![a](./d.svg)\n\n![b](./d.svg)", str(tmp_path)),
            _requirement("![c](./d.svg)", str(tmp_path), uid="R-2"),
        ],
    )
    parts = _parts(path)
    assert len([n for n in parts if n.startswith("word/media/")]) == 2
    ids = re.findall(r'<wp:docPr id="(\d+)"', _document_xml(parts))
    assert len(ids) == 3 and len(set(ids)) == 3
