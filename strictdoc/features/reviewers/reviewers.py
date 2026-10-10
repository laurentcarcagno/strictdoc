"""
The reviewers of a document: the people who may comment on it besides the
authors. They are named by the author who creates the document (or later by
any author) and are kept in the document itself, in its custom metadata:

    [DOCUMENT]
    METADATA:
      REVIEWERS: ann, bob

so that they travel with the file. A user name is the one the login proxy
reports, in lower case.

Who may comment on a document: an author or an administrator, a user whose
project role is reviewer (all documents), and the reviewers of the document.
"""

import re
from typing import Callable, List, Optional, Sequence

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.document_config import (
    DocumentCustomMetadata,
    DocumentCustomMetadataKeyValuePair,
)
from strictdoc.features.hierarchy.levels import document_metadata
from strictdoc.features.roles.roles import ROLE_REVIEWER, role_allows

REVIEWERS_KEY = "REVIEWERS"
CREATED_BY_KEY = "CREATED_BY"

_SEPARATOR = re.compile(r"[,;\s]+")


def parse_reviewers(text: str) -> List[str]:
    """The distinct user names of a list typed by a person, in order."""
    names: List[str] = []
    for item_ in _SEPARATOR.split(text.strip().lower()):
        if len(item_) > 0 and item_ not in names:
            names.append(item_)
    return names


def unknown_reviewers(
    names: Sequence[str], is_member: Optional[Callable[[str], bool]]
) -> List[str]:
    """The names that are not members of the project (all, if it has none)."""
    if is_member is None:
        return []
    return [name_ for name_ in names if not is_member(name_)]


def document_reviewers(document: SDocDocument) -> List[str]:
    return parse_reviewers(document_metadata(document).get(REVIEWERS_KEY, ""))


def can_comment(role: Optional[str], user: str, document: SDocDocument) -> bool:
    """True if the user may add a comment to a node of this document."""
    if role_allows(role, ROLE_REVIEWER):
        return True
    return user.strip().lower() in document_reviewers(document)


def set_metadata(document: SDocDocument, key: str, value: str) -> None:
    """Sets (or, with an empty value, removes) a custom metadata entry."""
    config = document.config
    if config.custom_metadata is None:
        if len(value) == 0:
            return
        config.custom_metadata = DocumentCustomMetadata(
            parent=config, entries=[]
        )
    metadata = config.custom_metadata
    metadata.entries = [
        entry_
        for entry_ in metadata.entries
        if entry_.key is None or entry_.key.upper() != key
    ]
    if len(value) > 0:
        metadata.entries.append(
            DocumentCustomMetadataKeyValuePair(
                parent=metadata, key=key, parts=[value]
            )
        )
    if len(metadata.entries) == 0:
        config.custom_metadata = None


def set_document_reviewers(
    document: SDocDocument, names: Sequence[str]
) -> None:
    set_metadata(document, REVIEWERS_KEY, ", ".join(names))
