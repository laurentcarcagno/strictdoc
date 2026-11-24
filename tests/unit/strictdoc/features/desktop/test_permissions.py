"""
@relation(SDOC-SRS-1242, scope=file)
@relation(SDOC-SRS-1243, scope=file)
"""

from typing import Optional

import pytest

from strictdoc.features.desktop.permissions import can_commit, can_send


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("administrator", True),
        ("author", True),
        # The role of a reviewer is below the one of an author.
        ("reviewer", False),
        ("reader", False),
        # A project that is not open in this session: the server decides.
        (None, True),
    ],
)
def test_001_who_sends(role: Optional[str], expected: bool) -> None:
    assert can_send(role) is expected


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("administrator", True),
        ("author", True),
        # A commit that its author cannot send nor move forward is not made.
        ("reviewer", False),
        ("reader", False),
        # The simulated catalog has no role: the commits are made.
        (None, True),
    ],
)
def test_002_who_commits_the_changes_of_a_request(
    role: Optional[str], expected: bool
) -> None:
    assert can_commit(role) is expected
