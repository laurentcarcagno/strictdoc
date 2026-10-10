"""
Images in the Word document: reading the image files, the inline drawing and
the parts of the package that go with it.

An image is written as a drawing whose name starts with IMAGE_NAME_PREFIX, so
that reading the document back finds the images that StrictDoc wrote and
ignores the others.
"""

import hashlib
import os
import re
import struct
from typing import Dict, Iterable, List, Optional, Tuple
from xml.sax.saxutils import quoteattr

from strictdoc.backend.docx.export.rst_to_paragraphs import (
    ExportImage,
    ExportParagraph,
)
from strictdoc.features.svg.rasterizer import (
    rasterize_svg,
    svg_display_size,
)
from strictdoc.features.svg.sanitizer import SvgRejected, sanitize_svg

IMAGE_NAME_PREFIX = "sdoc-image:"

# Word shows pictures at 96 pixels per inch: 9525 EMU per pixel.
_EMU_PER_PIXEL = 9525
# The widest picture: 14 cm of a page (360000 EMU per cm).
_MAX_WIDTH_EMU = 14 * 360000

_TOKEN = "@@SDOC_IMAGE:{}@@"
_TOKEN_PATTERN = re.compile(r"@@SDOC_IMAGE:([0-9a-f]+)@@")
# The SVG part of a picture that has a PNG fallback.
_SVG_TOKEN = "@@SDOC_IMAGE_SVG:{}@@"
_SVG_EXTENSION_URI = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"
_SVG_NAMESPACE = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"
_DOCPR_TOKEN = "@@SDOC_DOCPR@@"

_IMAGE_RELATIONSHIP_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
)
_CONTENT_TYPES = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "svg": "image/svg+xml",
}


def load_image(path: str, alt: str = "") -> Optional[ExportImage]:
    """The image of a file that Word can show, or None."""
    try:
        with open(path, "rb") as file_:
            data = file_.read()
    except OSError:
        return None
    if path.lower().endswith(".svg"):
        return _load_svg(path, alt, data)
    detected = image_size(data)
    if detected is None:
        return None
    extension, width, height = detected
    width_emu = width * _EMU_PER_PIXEL
    height_emu = height * _EMU_PER_PIXEL
    if width_emu > _MAX_WIDTH_EMU:
        height_emu = height_emu * _MAX_WIDTH_EMU // width_emu
        width_emu = _MAX_WIDTH_EMU
    name = os.path.basename(path)
    return ExportImage(
        token=hashlib.sha1(data).hexdigest()[:16],
        name=name,
        alt=alt or name,
        data=data,
        extension=extension,
        content_type=_CONTENT_TYPES[extension],
        width_emu=max(width_emu, 1),
        height_emu=max(height_emu, 1),
    )


def _load_svg(path: str, alt: str, data: bytes) -> Optional[ExportImage]:
    """
    An SVG is cleaned, then drawn twice: the SVG itself for the Word versions
    that show it, and a PNG of twice the display size for all the others.
    """
    try:
        cleaned = sanitize_svg(data)
        width, height = svg_display_size(cleaned)
        width_emu = width * _EMU_PER_PIXEL
        height_emu = height * _EMU_PER_PIXEL
        if width_emu > _MAX_WIDTH_EMU:
            height_emu = height_emu * _MAX_WIDTH_EMU // width_emu
            width_emu = _MAX_WIDTH_EMU
        png = rasterize_svg(cleaned, width_px=2 * max(width, 1))
    except (SvgRejected, ValueError):
        return None
    name = os.path.basename(path)
    return ExportImage(
        token=hashlib.sha1(cleaned).hexdigest()[:16],
        name=name,
        alt=alt or name,
        data=cleaned,
        extension="svg",
        content_type=_CONTENT_TYPES["svg"],
        width_emu=max(width_emu, 1),
        height_emu=max(height_emu, 1),
        fallback_png=png,
    )


def image_size(data: bytes) -> Optional[Tuple[str, int, int]]:
    """(extension, width, height) of a PNG, JPEG or GIF file, else None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return ("png", width, height) if width > 0 and height > 0 else None
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
        return ("gif", width, height) if width > 0 and height > 0 else None
    if data[:2] == b"\xff\xd8":
        return _jpeg_size(data)
    return None


def _jpeg_size(data: bytes) -> Optional[Tuple[str, int, int]]:
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        length = struct.unpack(">H", data[index + 2 : index + 4])[0]
        # SOF0..SOF15, except DHT (C4), JPG (C8) and DAC (CC).
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[index + 5 : index + 9])
            return ("jpeg", width, height) if width > 0 and height > 0 else None
        index += 2 + length
    return None


def drawing_xml(image: ExportImage) -> str:
    """The inline picture; the relationship and the id are filled in later."""
    cx, cy = image.width_emu, image.height_emu
    name = quoteattr(IMAGE_NAME_PREFIX + image.name)
    description = quoteattr(image.alt)
    return (
        "<w:drawing>"
        '<wp:inline distT="0" distB="0" distL="0" distR="0"'
        ' xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"'
        ' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
        ' xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<wp:extent cx="{cx}" cy="{cy}"/>'
        f'<wp:docPr id="{_DOCPR_TOKEN}" name={name} descr={description}/>'
        '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/>'
        "</wp:cNvGraphicFramePr>"
        "<a:graphic>"
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        "<pic:pic>"
        f'<pic:nvPicPr><pic:cNvPr id="0" name={name}/><pic:cNvPicPr/></pic:nvPicPr>'
        f"<pic:blipFill>{_blip_xml(image)}"
        "<a:stretch><a:fillRect/></a:stretch></pic:blipFill>"
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
        "</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing>"
    )


def _blip_xml(image: ExportImage) -> str:
    """The picture reference; an SVG carries the PNG and the SVG extension."""
    embed = _TOKEN.format(image.token)
    if image.fallback_png is None:
        return f'<a:blip r:embed="{embed}"/>'
    return (
        f'<a:blip r:embed="{embed}"><a:extLst>'
        f'<a:ext uri="{_SVG_EXTENSION_URI}">'
        f'<asvg:svgBlip xmlns:asvg="{_SVG_NAMESPACE}"'
        f' r:embed="{_SVG_TOKEN.format(image.token)}"/>'
        "</a:ext></a:extLst></a:blip>"
    )


def images_in(paragraphs: Iterable[ExportParagraph]) -> Dict[str, ExportImage]:
    """The images that the paragraphs use, by token."""
    images: Dict[str, ExportImage] = {}
    for paragraph_ in paragraphs:
        for run_ in paragraph_.runs:
            if run_.image is not None:
                images[run_.image.token] = run_.image
    return images


def embed_images(
    package: Dict[str, bytes], images: Dict[str, ExportImage]
) -> None:
    """
    Adds the media parts, the relationships and the content types that the
    drawings in word/document.xml need, and fills in their placeholders.
    """
    document_xml = package["word/document.xml"].decode("utf8")
    used = {
        token_: images[token_]
        for token_ in _TOKEN_PATTERN.findall(document_xml)
        if token_ in images
    }
    if len(used) == 0:
        return

    relationships = package.get("word/_rels/document.xml.rels")
    if relationships is None:
        raise ValueError("The package has no word/_rels/document.xml.rels.")
    relationships_xml = relationships.decode("utf8")
    content_types_xml = package["[Content_Types].xml"].decode("utf8")

    new_relationships: List[str] = []

    def add_part(
        token_: str, extension: str, content_type: str, data: bytes, kind: str
    ) -> str:
        nonlocal relationships_xml, content_types_xml
        part_name = f"media/sdoc_{token_[:12]}.{extension}"
        relationship_id = f"rIdSdoc{kind}{token_[:12]}"
        package[f"word/{part_name}"] = data
        if f'Id="{relationship_id}"' not in relationships_xml:
            new_relationships.append(
                f'<Relationship Id="{relationship_id}" '
                f'Type="{_IMAGE_RELATIONSHIP_TYPE}" Target="{part_name}"/>'
            )
        if not re.search(
            rf'<Default\b[^>]*Extension="{extension}"',
            content_types_xml,
            re.IGNORECASE,
        ):
            content_types_xml = content_types_xml.replace(
                "</Types>",
                f'<Default Extension="{extension}" '
                f'ContentType="{content_type}"/></Types>',
                1,
            )
        return relationship_id

    for token_, image_ in used.items():
        if image_.fallback_png is not None:
            png_id = add_part(
                token_, "png", "image/png", image_.fallback_png, "Image"
            )
            svg_id = add_part(
                token_, "svg", image_.content_type, image_.data, "Svg"
            )
            document_xml = document_xml.replace(
                _SVG_TOKEN.format(token_), svg_id
            )
        else:
            png_id = add_part(
                token_,
                image_.extension,
                image_.content_type,
                image_.data,
                "Image",
            )
        document_xml = document_xml.replace(_TOKEN.format(token_), png_id)
    relationships_xml = relationships_xml.replace(
        "</Relationships>", "".join(new_relationships) + "</Relationships>", 1
    )

    # Every picture of the document needs its own id.
    taken = [
        int(id_)
        for id_ in re.findall(r'<wp:docPr[^>]*\sid="(\d+)"', document_xml)
    ]
    next_id = max(taken, default=0) + 1
    while _DOCPR_TOKEN in document_xml:
        document_xml = document_xml.replace(_DOCPR_TOKEN, str(next_id), 1)
        next_id += 1

    package["word/document.xml"] = document_xml.encode("utf8")
    package["word/_rels/document.xml.rels"] = relationships_xml.encode("utf8")
    package["[Content_Types].xml"] = content_types_xml.encode("utf8")
