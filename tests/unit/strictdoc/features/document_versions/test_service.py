"""
@relation(SDOC-SRS-215, scope=file)
"""

from strictdoc.features.document_versions.service import (
    compare_snapshots,
    read_snapshots,
)

BEFORE = """[DOCUMENT]
TITLE: Versions

[REQUIREMENT]
UID: REQ-1
TITLE: First
STATEMENT: Alpha.

[REQUIREMENT]
UID: REQ-2
TITLE: Second
STATEMENT: Beta.

[REQUIREMENT]
UID: REQ-4
TITLE: Fourth
STATEMENT: Delta.
"""

AFTER = """[DOCUMENT]
TITLE: Versions

[REQUIREMENT]
UID: REQ-1
TITLE: First
STATEMENT: Alpha, reworded.

[REQUIREMENT]
UID: REQ-3
TITLE: Third
STATEMENT: Gamma.

[REQUIREMENT]
UID: REQ-4
TITLE: Fourth
STATEMENT: Delta.
"""


def test_001_snapshots_are_keyed_by_uid_in_document_order() -> None:
    snapshots = read_snapshots(BEFORE)

    assert list(snapshots) == ["REQ-1", "REQ-2", "REQ-4"]
    assert snapshots["REQ-1"].title == "First"
    assert snapshots["REQ-1"].fields["STATEMENT"] == "Alpha."


def test_002_comparison_lists_added_removed_and_changed_items() -> None:
    comparison = compare_snapshots(
        read_snapshots(BEFORE), read_snapshots(AFTER)
    )

    assert [item_.key for item_ in comparison.added] == ["REQ-3"]
    assert [item_.key for item_ in comparison.removed] == ["REQ-2"]
    assert [item_.key for item_ in comparison.changed] == ["REQ-1"]
    assert comparison.unchanged == 1
    change = comparison.changed[0].changes[0]
    assert (change.name, change.before, change.after) == (
        "STATEMENT",
        "Alpha.",
        "Alpha, reworded.",
    )


def test_003_the_same_text_has_no_difference() -> None:
    comparison = compare_snapshots(
        read_snapshots(BEFORE), read_snapshots(BEFORE)
    )

    assert comparison.added == []
    assert comparison.removed == []
    assert comparison.changed == []
    assert comparison.unchanged == 3
