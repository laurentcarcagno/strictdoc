"""
The applicable documents of a project, read from the traceability index, for
the reference resolver.

The project option ``applicable_documents = {"DA1": "inputs/pus-standard"}``
names each input document by its path in the project (with or without the
extension) or by its document UID.
"""

import os
from typing import Any, Dict, List, Optional, Sequence

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.core.document_iterator import SDocDocumentIterator
from strictdoc.features.hierarchy.references import (
    ReferenceResolver,
    ReferenceSource,
    ResolverFunction,
)


class IndexReferenceSource(ReferenceSource):
    def __init__(
        self, traceability_index: Any, applicable_documents: Dict[str, str]
    ) -> None:
        self._index = traceability_index
        self._documents: Dict[str, SDocDocument] = {}
        for key_, location_ in applicable_documents.items():
            document = self._find_document(location_)
            if document is not None:
                self._documents[key_] = document
        self._uids: Dict[str, List[str]] = {}
        self._sections: Dict[str, Dict[str, Optional[str]]] = {}

    def _find_document(self, location: str) -> Optional[SDocDocument]:
        wanted = os.path.splitext(location.replace("\\", "/").strip("/"))[0]
        for document_ in self._index.document_tree.document_list:
            if (
                document_.config is not None
                and document_.config.uid == location
            ):
                return document_
            meta = document_.meta
            if meta is None:
                continue
            relative = meta.input_doc_rel_path.relative_path.replace("\\", "/")
            if os.path.splitext(relative.strip("/"))[0] == wanted:
                return document_
        return None

    def _scan(self, document_key: str) -> None:
        if document_key in self._uids:
            return
        uids: List[str] = []
        sections: Dict[str, Optional[str]] = {}
        document = self._documents[document_key]
        iterator = SDocDocumentIterator(document=document, node_filter=None)
        for node_, context_ in iterator.all_content(print_fragments=False):
            if not isinstance(node_, SDocNode):
                continue
            uid = node_.reserved_uid or None
            if node_.node_type == "SECTION":
                number = context_.get_level_string()
                if number:
                    sections[number] = uid
            if uid:
                uids.append(uid)
        self._uids[document_key] = uids
        self._sections[document_key] = sections

    def has_document(self, document_key: str) -> bool:
        return document_key in self._documents

    def uids_of(self, document_key: str) -> Sequence[str]:
        self._scan(document_key)
        return self._uids[document_key]

    def section_uid(self, document_key: str, number: str) -> Optional[str]:
        self._scan(document_key)
        return self._sections[document_key].get(number)

    def section_exists(self, document_key: str, number: str) -> bool:
        self._scan(document_key)
        return number in self._sections[document_key]


def build_reference_resolver(
    applicable_documents: Dict[str, str], traceability_index: Any
) -> Optional[ResolverFunction]:
    """The resolver of the project, None when it names no applicable document."""
    if len(applicable_documents) == 0:
        return None
    return ReferenceResolver(
        IndexReferenceSource(traceability_index, applicable_documents)
    ).resolve
