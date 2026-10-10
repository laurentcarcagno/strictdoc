import os
from pathlib import Path
from typing import List
from xml.etree import ElementTree as ET

import pytest

from strictdoc.features.svg.sanitizer import (
    MAX_SVG_DEPTH,
    SvgRejected,
    sanitize_svg,
)

CORPUS = Path(__file__).parent / "corpus"
HOSTILE = sorted(p for p in (CORPUS / "hostile").glob("*.svg"))
NORMAL = sorted(p for p in (CORPUS / "normal").glob("*.svg"))

FORBIDDEN: List[str] = [
    "script",
    "onload",
    "onclick",
    "onmouseover",
    "javascript",
    "foreignobject",
    "iframe",
    "<object",
    "<embed",
    "http://evil",
    "file:",
    "/etc/passwd",
    "../",
    "@import",
    "expression",
    "behavior",
    "<animate",
    "<set",
    "text/html",
    "svg+xml;base64",
    "<!doctype",
    "<!entity",
]


@pytest.mark.parametrize("path", HOSTILE, ids=lambda p: p.name)
def test_001_hostile_file_is_neutralised_or_rejected(path: Path) -> None:
    try:
        cleaned = sanitize_svg(path.read_bytes())
    except SvgRejected:
        return
    lowered = cleaned.decode("utf-8").lower()
    for word in FORBIDDEN:
        assert word not in lowered, f"{path.name}: {word}"


def test_002_a_doctype_is_always_rejected() -> None:
    with pytest.raises(SvgRejected):
        sanitize_svg((CORPUS / "hostile" / "entity.svg").read_bytes())


def test_003_entity_bomb_is_rejected_without_expanding() -> None:
    bomb = (
        b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaaaaaaaa">'
        b'<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">'
        b'<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg"><text>&c;</text></svg>'
    )
    with pytest.raises(SvgRejected):
        sanitize_svg(bomb)


def test_004_huge_file_is_rejected() -> None:
    filler = b"<rect/>" * 2_000_000
    data = b'<svg xmlns="http://www.w3.org/2000/svg">' + filler + b"</svg>"
    with pytest.raises(SvgRejected):
        sanitize_svg(data)


def test_005_deep_nesting_is_rejected() -> None:
    depth = MAX_SVG_DEPTH + 5
    data = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        + b"<g>" * depth
        + b"</g>" * depth
        + b"</svg>"
    )
    with pytest.raises(SvgRejected):
        sanitize_svg(data)


def test_006_too_many_elements_are_rejected() -> None:
    data = (
        b'<svg xmlns="http://www.w3.org/2000/svg">'
        + b"<rect/>" * 60_000
        + b"</svg>"
    )
    with pytest.raises(SvgRejected):
        sanitize_svg(data)


@pytest.mark.parametrize(
    "data",
    [b"", b"not xml", b"<html/>", b"<svg>", b"\xff\xfe<svg/>"],
)
def test_007_not_an_svg_is_rejected(data: bytes) -> None:
    with pytest.raises(SvgRejected):
        sanitize_svg(data)


def test_008_local_references_are_kept() -> None:
    cleaned = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" '
        b'xmlns:xlink="http://www.w3.org/1999/xlink">'
        b'<defs><linearGradient id="g"/><rect id="r" width="1" height="1"/>'
        b"</defs>"
        b'<use xlink:href="#r"/><rect fill="url(#g)" width="1" height="1"/>'
        b"</svg>"
    ).decode()
    assert 'href="#r"' in cleaned
    assert "url(#g)" in cleaned


def test_009_small_embedded_png_is_kept() -> None:
    cleaned = sanitize_svg(
        b'<svg xmlns="http://www.w3.org/2000/svg" '
        b'xmlns:xlink="http://www.w3.org/1999/xlink">'
        b'<image xlink:href="data:image/png;base64,iVBORw0KGgo=" '
        b'width="1" height="1"/></svg>'
    ).decode()
    assert "data:image/png;base64" in cleaned


@pytest.mark.parametrize("path", NORMAL, ids=lambda p: p.name)
def test_010_normal_diagram_keeps_its_drawing(path: Path) -> None:
    original = path.read_bytes()
    cleaned = sanitize_svg(original)

    def shape_count(data: bytes) -> int:
        return sum(
            1
            for element in ET.fromstring(data).iter()
            if element.tag.rsplit("}", 1)[-1]
            in ("rect", "path", "circle", "polyline", "text", "line")
        )

    assert shape_count(cleaned) == shape_count(original)
    assert len(cleaned) >= len(original) * 0.8


def test_011_clean_output_is_stable() -> None:
    for path in NORMAL:
        once = sanitize_svg(path.read_bytes())
        assert sanitize_svg(once) == once


def test_012_corpus_is_present() -> None:
    assert len(HOSTILE) >= 10 and len(NORMAL) >= 5
    assert os.path.isdir(CORPUS)
