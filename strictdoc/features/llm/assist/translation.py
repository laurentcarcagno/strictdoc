"""
Translating a whole document into a new one.

The new document is a copy of the source (written by the SDoc writer and read
again, so that it shares nothing with the project): the texts of its nodes are
replaced by the translation, every UID gets a suffix with the language
(REQ-12 becomes REQ-12-FR), so does every link and anchor that points inside the
document, and the references to other documents stay as they are. The new MIDs
and the language are written in it. Nothing of this touches the project until a
person applies the result (service.py).
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.backend.sdoc.models.reference import (
    ChildReqReference,
    ParentReqReference,
)
from strictdoc.backend.sdoc.reader import SDReader
from strictdoc.backend.sdoc.writer import SDWriter
from strictdoc.core.document_iterator import SDocDocumentIterator
from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.reviewers.reviewers import set_metadata
from strictdoc.helpers.exception import StrictDocException
from strictdoc.helpers.mid import MID

LANGUAGE_NAMES: Dict[str, str] = {
    "en": "English",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    "fi": "Finnish",
    "pl": "Polish",
    "cs": "Czech",
    "ro": "Romanian",
    "el": "Greek",
    "tr": "Turkish",
    "ru": "Russian",
    "uk": "Ukrainian",
    "ja": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
    "ar": "Arabic",
    "hu": "Hungarian",
}
# Names in other languages that people type.
_ALIASES = {
    "français": "fr",
    "francais": "fr",
    "anglais": "en",
    "allemand": "de",
    "espagnol": "es",
    "italien": "it",
    "portugais": "pt",
    "néerlandais": "nl",
}
_NAME_TO_CODE = {
    **{name_.lower(): code_ for code_, name_ in LANGUAGE_NAMES.items()},
    **_ALIASES,
}
_CODE = re.compile(r"^[a-z]{2,3}$")
_FIELDS_ALWAYS = ("TITLE", "STATEMENT", "CONTENT", "DESCRIPTION", "RATIONALE")
_NOT_TRANSLATED = ("COMMENT", "UID", "MID")
_LINK = re.compile(r"(\[LINK:\s*)([^\]\s,]+)")
_ANCHOR_DEF = re.compile(r"\[ANCHOR:\s*([^,\]\s]+)")
_ANCHOR = re.compile(r"(\[ANCHOR:\s*)([^,\]\s]+)")


class TranslationError(StrictDocException):
    """The document cannot be translated."""


def resolve_language(token: str) -> Tuple[str, str]:
    """The code and the name of a language typed as a code or a name."""
    word = token.strip().lower()
    if word in _NAME_TO_CODE:
        code = _NAME_TO_CODE[word]
        return code, LANGUAGE_NAMES[code]
    if word in LANGUAGE_NAMES:
        return word, LANGUAGE_NAMES[word]
    if _CODE.match(word):
        return word, word.upper()
    raise TranslationError(
        f"'{token}' is not a language: use a code (fr, en, de, es, it...) "
        "or a name (French, English...)."
    )


def parse_arguments(arguments: str) -> Tuple[str, str, str]:
    """The language code, its name and the optional path of the new document."""
    words = arguments.split()
    if not words:
        raise TranslationError("Say the language: /translate fr")
    code, name = resolve_language(words[0])
    return code, name, (words[1] if len(words) > 1 else "")


def default_path(source_relative_path: str, code: str) -> str:
    """spec/req.sdoc -> spec/req_FR.sdoc"""
    base, dot, extension = source_relative_path.rpartition(".")
    if not dot:
        return f"{source_relative_path}_{code.upper()}"
    return f"{base}_{code.upper()}.{extension}"


@dataclass
class WorkItem:
    ref: str
    node_type: str
    uid: str
    fields: Dict[str, str]


@dataclass
class Translation:
    """A copy of a document and the texts to translate."""

    copy: SDocDocument
    suffix: str
    items: List[WorkItem] = field(default_factory=list)
    id_map: Dict[str, str] = field(default_factory=dict)
    nodes_by_ref: Dict[str, Optional[SDocNode]] = field(default_factory=dict)


def _translatable(node: SDocNode) -> Dict[str, str]:
    texts: Dict[str, str] = {}
    for name_, fields_ in node.ordered_fields_lookup.items():
        if name_ in _NOT_TRANSLATED or not fields_:
            continue
        first = fields_[0]
        if name_ in _FIELDS_ALWAYS or first.is_multiline():
            value = first.get_text_value().strip()
            if value:
                texts[name_] = value
    return texts


def start(
    document: SDocDocument, project_config: ProjectConfig, code: str
) -> Translation:
    """The copy of the document, with the work to do listed. Raises."""
    if document.fragments_from_files or any(
        getattr(node_, "is_root_included_document", False)
        for node_, _ in SDocDocumentIterator(document).all_content(
            print_fragments=False
        )
    ):
        raise TranslationError(
            "A document that includes other documents cannot be translated yet."
        )
    source_text = SDWriter(project_config).write(document)
    copy = SDReader.read(source_text)
    suffix = "-" + code.upper()
    translation = Translation(copy=copy, suffix=suffix)
    for anchor_ in _ANCHOR_DEF.findall(source_text):
        translation.id_map[anchor_] = anchor_ + suffix
    translation.items.append(
        WorkItem(
            "doc", "DOCUMENT", copy.config.uid or "", {"TITLE": copy.title}
        )
    )
    translation.nodes_by_ref["doc"] = None
    number = 0
    for node_, _ in SDocDocumentIterator(copy).all_content(
        print_fragments=False
    ):
        if not isinstance(node_, SDocNode):
            continue
        uid = node_.reserved_uid or ""
        if uid:
            translation.id_map[uid] = uid + suffix
        texts = _translatable(node_)
        if not texts:
            continue
        number += 1
        ref = f"n{number}"
        translation.items.append(WorkItem(ref, node_.node_type, uid, texts))
        translation.nodes_by_ref[ref] = node_
    return translation


def batches(
    items: List[WorkItem], budget: int, size: int = 12
) -> List[List[WorkItem]]:
    result: List[List[WorkItem]] = []
    current: List[WorkItem] = []
    used = 0
    for item_ in items:
        length = sum(len(text_) for text_ in item_.fields.values()) + 40
        if current and (used + length > budget or len(current) >= size):
            result.append(current)
            current, used = [], 0
        current.append(item_)
        used += length
    if current:
        result.append(current)
    return result


def rewrite_ids(text: str, id_map: Dict[str, str]) -> str:
    """Links and anchors that point inside the document get the suffix."""

    def link(match: "re.Match[str]") -> str:
        target = match.group(2)
        return match.group(1) + id_map.get(target, target)

    return _ANCHOR.sub(link, _LINK.sub(link, text))


def finish(
    translation: Translation,
    mapping: Dict[str, Dict[str, str]],
    *,
    project_config: ProjectConfig,
    source: SDocDocument,
    code: str,
) -> Tuple[str, int, int]:
    """
    Puts the translations and the suffixed UIDs in the copy and writes it.
    Returns the text of the new document, the number of nodes translated and
    the number that were left in the source language.
    """
    copy = translation.copy
    id_map = translation.id_map
    translated = skipped = 0
    for item_ in translation.items:
        node = translation.nodes_by_ref[item_.ref]
        done = mapping.get(item_.ref)
        if done is None:
            if item_.ref != "doc":
                skipped += 1
            continue
        if item_.ref == "doc":
            copy.title = done.get("TITLE", copy.title).strip() or copy.title
            continue
        assert node is not None
        for name_, text_ in done.items():
            fields_ = node.ordered_fields_lookup.get(name_)
            if fields_ and text_.strip():
                fields_[0].parts = [rewrite_ids(text_.strip(), id_map)]
        translated += 1

    for node_, _ in SDocDocumentIterator(copy).all_content(
        print_fragments=False
    ):
        if not isinstance(node_, SDocNode):
            continue
        uid = node_.reserved_uid
        if uid:
            node_.reserved_uid = id_map[uid]
        node_.ordered_fields_lookup.pop("COMMENT", None)
        node_.reserved_mid = MID.create()
        if "MID" in node_.ordered_fields_lookup:
            node_.set_field_value(
                field_name="MID",
                form_field_index=0,
                value=node_.reserved_mid.get_string_value(),
            )
        for relation_ in node_.relations:
            if isinstance(relation_, (ParentReqReference, ChildReqReference)):
                relation_.ref_uid = id_map.get(
                    relation_.ref_uid, relation_.ref_uid
                )
    source_uid = source.config.uid or source.title
    if copy.config.uid:
        copy.config.uid = copy.config.uid + translation.suffix
    copy.reserved_mid = MID.create()
    set_metadata(copy, "LANGUAGE", code.lower())
    set_metadata(copy, "TRANSLATION_OF", source_uid)
    return SDWriter(project_config).write(copy), translated, skipped


def check_text(text: str) -> List[str]:
    """The UIDs of a document written by finish(); raises when it does not parse."""
    reread = SDReader.read(text)
    uids = []
    for node_, _ in SDocDocumentIterator(reread).all_content(
        print_fragments=False
    ):
        if isinstance(node_, SDocNode) and node_.reserved_uid:
            uids.append(node_.reserved_uid)
    return uids
