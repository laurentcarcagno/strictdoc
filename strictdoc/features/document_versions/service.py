"""
The items of a document as they were at a version tag, and the difference
between two versions: the items that were added, removed or changed.

@relation(SDOC-SRS-215, scope=file)
"""

from dataclasses import dataclass, field
from typing import Dict, List

from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.backend.sdoc.reader import SDReader
from strictdoc.core.document_iterator import SDocDocumentIterator


@dataclass(frozen=True)
class ItemSnapshot:
    key: str
    title: str
    fields: Dict[str, str]


@dataclass
class FieldChange:
    name: str
    before: str
    after: str


@dataclass
class ItemChange:
    key: str
    title: str
    changes: List[FieldChange] = field(default_factory=list)


@dataclass
class VersionComparison:
    added: List[ItemSnapshot]
    removed: List[ItemSnapshot]
    changed: List[ItemChange]
    unchanged: int


def read_snapshots(text: str) -> Dict[str, ItemSnapshot]:
    """
    The items of a document text by key (the UID, else the MID), in the order
    of the document. An item with neither is not followed. The text is
    parsed on its own, so a document that includes another one shows the
    included items as they are in the working tree of the includer only if
    the parser can read them: the caller shows the error when it cannot.
    """
    document = SDReader.read(text)
    snapshots: Dict[str, ItemSnapshot] = {}
    iterator = SDocDocumentIterator(document)
    for node_, _ in iterator.all_content(print_fragments=False):
        if not isinstance(node_, SDocNode):
            continue
        key = node_.reserved_uid
        if key is None and node_.reserved_mid is not None:
            key = node_.reserved_mid.get_string_value()
        if key is None or len(key) == 0:
            continue
        fields: Dict[str, str] = {}
        for field_ in node_.enumerate_fields():
            previous = fields.get(field_.field_name)
            value = field_.get_text_value()
            fields[field_.field_name] = (
                value if previous is None else previous + "\n" + value
            )
        snapshots[key] = ItemSnapshot(
            key=key, title=node_.reserved_title or "", fields=fields
        )
    return snapshots


def compare_snapshots(
    before: Dict[str, ItemSnapshot], after: Dict[str, ItemSnapshot]
) -> VersionComparison:
    added = [item_ for key_, item_ in after.items() if key_ not in before]
    removed = [item_ for key_, item_ in before.items() if key_ not in after]
    changed: List[ItemChange] = []
    unchanged = 0
    for key_, old_ in before.items():
        new_ = after.get(key_)
        if new_ is None:
            continue
        change = ItemChange(key=key_, title=new_.title)
        for name_ in list(old_.fields) + [
            name_ for name_ in new_.fields if name_ not in old_.fields
        ]:
            old_value = old_.fields.get(name_, "")
            new_value = new_.fields.get(name_, "")
            if old_value != new_value:
                change.changes.append(FieldChange(name_, old_value, new_value))
        if len(change.changes) > 0:
            changed.append(change)
        else:
            unchanged += 1
    return VersionComparison(
        added=added, removed=removed, changed=changed, unchanged=unchanged
    )
