"""
References to applicable documents, as written in a Word column such as
"Linked Req":

    [DA1] §5.14.1 ; [DA2] REQ-106005, REQ-106006, REQ-0280

Groups are separated by ";". A group starts with the short name of the
applicable document ("[DA1]"), followed by section numbers ("§5.14.1") and
UIDs separated by ",". A group without a short name continues the previous
one. A "-" or an empty value is no reference.
"""

import re
from dataclasses import dataclass, field
from typing import Callable, Collection, Dict, List, Optional, Sequence

KIND_SECTION = "section"
KIND_UID = "uid"

_DOCUMENT_TAG = re.compile(r"^\[([^\]]*)\]\s*(.*)$", re.DOTALL)


@dataclass(frozen=True)
class Reference:
    # The short name of the applicable document ("DA1"), None when the value
    # does not say.
    document: Optional[str]
    kind: str
    value: str

    def text(self) -> str:
        tag = f"[{self.document}] " if self.document else ""
        mark = "§" if self.kind == KIND_SECTION else ""
        return f"{tag}{mark}{self.value}"


def parse_references(text: str) -> List[Reference]:
    """The references of a value. Never fails: what is no reference is skipped."""
    references: List[Reference] = []
    document: Optional[str] = None
    for group_ in text.replace("\n", " ").split(";"):
        group = group_.strip()
        tag_match = _DOCUMENT_TAG.match(group)
        if tag_match is not None:
            document = tag_match.group(1).strip() or None
            group = tag_match.group(2).strip()
        for item_ in group.split(","):
            item = item_.strip().rstrip(".").strip()
            if len(item) == 0 or item == "-":
                continue
            if item.startswith("§"):
                value = item[1:].strip()
                if len(value) > 0:
                    references.append(Reference(document, KIND_SECTION, value))
            else:
                references.append(Reference(document, KIND_UID, item))
    return references


@dataclass
class ResolvedReferences:
    # The UIDs of the nodes that the references designate, without doubles.
    uids: List[str] = field(default_factory=list)
    # One message per reference that could not be resolved.
    unresolved: List[str] = field(default_factory=list)


class ReferenceSource:
    """What the resolver needs to know about the applicable documents."""

    def has_document(self, document_key: str) -> bool:
        raise NotImplementedError

    def uids_of(self, document_key: str) -> Sequence[str]:
        raise NotImplementedError

    def section_uid(self, document_key: str, number: str) -> Optional[str]:
        """The UID of the section with this number, None if there is none."""
        raise NotImplementedError

    def section_exists(self, document_key: str, number: str) -> bool:
        raise NotImplementedError


class ReferenceResolver:
    def __init__(self, source: ReferenceSource) -> None:
        self._source = source

    def resolve(
        self, text: str, local_uids: Collection[str] = ()
    ) -> ResolvedReferences:
        """
        `local_uids` are the UIDs of the document that holds the text: a
        reference with no applicable document that names one of them is a link
        inside the document.
        """
        result = ResolvedReferences()
        for reference_ in parse_references(text):
            self._resolve_one(reference_, result, local_uids)
        return result

    def _resolve_one(
        self,
        reference: Reference,
        result: ResolvedReferences,
        local_uids: Collection[str],
    ) -> None:
        document = reference.document
        if document is None:
            names = reference.value.split()
            if len(names) > 0 and all(name_ in local_uids for name_ in names):
                for name_ in names:
                    self._add(result, name_)
                return
            result.unresolved.append(
                f"{reference.text()}: no applicable document named"
            )
            return
        if not self._source.has_document(document):
            result.unresolved.append(
                f"{reference.text()}: '{document}' is not an applicable "
                "document of the project"
            )
            return
        if reference.kind == KIND_SECTION:
            if not self._source.section_exists(document, reference.value):
                result.unresolved.append(
                    f"{reference.text()}: no section {reference.value} in "
                    f"{document}"
                )
                return
            uid = self._source.section_uid(document, reference.value)
            if uid is None:
                result.unresolved.append(
                    f"{reference.text()}: section {reference.value} of "
                    f"{document} has no UID to link to"
                )
                return
            self._add(result, uid)
            return
        uids = self._source.uids_of(document)
        if reference.value in uids:
            self._add(result, reference.value)
            return
        # A long UID such as "ISIS-OBCPB-E70-01-REQ-106001" is often written
        # short ("REQ-106001") in the tables that cite it.
        ends = [uid_ for uid_ in uids if uid_.endswith("-" + reference.value)]
        if len(ends) == 1:
            self._add(result, ends[0])
        elif len(ends) > 1:
            result.unresolved.append(
                f"{reference.text()}: ambiguous in {document} "
                f"({', '.join(sorted(ends))})"
            )
        else:
            result.unresolved.append(
                f"{reference.text()}: no such requirement in {document}"
            )

    @staticmethod
    def _add(result: ResolvedReferences, uid: str) -> None:
        if uid not in result.uids:
            result.uids.append(uid)


ResolverFunction = Callable[[str, Collection[str]], ResolvedReferences]


class DictSource(ReferenceSource):
    """A source made of plain data: for tests and for small tools."""

    def __init__(
        self,
        uids: Dict[str, Sequence[str]],
        sections: Optional[Dict[str, Dict[str, Optional[str]]]] = None,
    ) -> None:
        self._uids = uids
        self._sections = sections or {}

    def has_document(self, document_key: str) -> bool:
        return document_key in self._uids

    def uids_of(self, document_key: str) -> Sequence[str]:
        return self._uids.get(document_key, [])

    def section_uid(self, document_key: str, number: str) -> Optional[str]:
        return self._sections.get(document_key, {}).get(number)

    def section_exists(self, document_key: str, number: str) -> bool:
        return number in self._sections.get(document_key, {})
