from strictdoc.features.git_config.commit_message import (
    asset_message,
    changed_uids,
    document_message,
)

CONTENT = """[DOCUMENT]
TITLE: Doc

[REQUIREMENT]
UID: REQ-001
STATEMENT: >>>
First.
<<<

[REQUIREMENT]
UID: REQ-042
STATEMENT: >>>
Second changed.
<<<
"""

DIFF_UPDATE = """diff --git a/d.sdoc b/d.sdoc
--- a/d.sdoc
+++ b/d.sdoc
@@ -14 +14 @@ STATEMENT: >>>
-Second.
+Second changed.
"""


def test_changed_uids_finds_the_block_of_a_changed_line() -> None:
    uids, added, deleted = changed_uids(DIFF_UPDATE, CONTENT)
    assert uids == ["REQ-042"]
    assert added == [] and deleted == []


def test_added_and_deleted_uids() -> None:
    diff = "+UID: REQ-9\n-UID: REQ-8\n@@ -1 +1 @@\n"
    _, added, deleted = changed_uids(diff, "")
    assert added == ["REQ-9"]
    assert deleted == ["REQ-8"]


def test_update_message_with_one_uid() -> None:
    assert (
        document_message("d.sdoc", DIFF_UPDATE, CONTENT)
        == "feat(doc): update requirement [REQ-042]"
    )


def test_message_with_several_uids_is_capped() -> None:
    diff = "".join(f"@@ -{n} +{n} @@\n" for n in (4, 5, 10, 11))
    content = CONTENT
    message = document_message("d.sdoc", diff, content)
    assert message == "feat(doc): update requirements [REQ-001, REQ-042]"
    many = "\n".join(
        f"[REQUIREMENT]\nUID: R-{n}\nSTATEMENT: x\n" for n in range(8)
    )
    diff_many = "".join(f"@@ -{4 * n + 2} +{4 * n + 2} @@\n" for n in range(8))
    message = document_message("d.sdoc", diff_many, many)
    assert message.endswith("and 3 more]")


def test_message_without_uid_uses_the_file_name() -> None:
    assert (
        document_message("sub/d.sdoc", "@@ -2 +2 @@\n", CONTENT)
        == "feat(doc): update d.sdoc"
    )


def test_added_requirement_message() -> None:
    diff = "@@ -0,0 +4,3 @@\n+[REQUIREMENT]\n+UID: REQ-042\n+STATEMENT: x\n"
    assert (
        document_message("d.sdoc", diff, CONTENT)
        == "feat(doc): add requirement [REQ-042]"
    )


def test_deleted_requirement_message() -> None:
    diff = "@@ -4,3 +3,0 @@\n-[REQUIREMENT]\n-UID: REQ-007\n-STATEMENT: x\n"
    assert (
        document_message("d.sdoc", diff, CONTENT)
        == "feat(doc): delete requirement [REQ-007]"
    )


def test_asset_message() -> None:
    assert asset_message(["a.png"]) == "feat(doc): add asset a.png"
    assert (
        asset_message(["a.png", "b.svg"])
        == "feat(doc): add assets a.png, b.svg"
    )
