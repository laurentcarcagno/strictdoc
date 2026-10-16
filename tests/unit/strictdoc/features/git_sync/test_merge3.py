from strictdoc.features.git_sync.blocks import split_blocks
from strictdoc.features.git_sync.merge3 import (
    CONFLICT,
    LOCAL,
    SAME,
    SERVER,
    assemble,
    conflict_indexes,
    merge3,
)

HEADER = "[DOCUMENT]\nTITLE: Spec\n\n"


def _req(uid, statement, title="T"):
    return (
        f"[REQUIREMENT]\nUID: {uid}\nTITLE: {title}\n"
        f"STATEMENT: >>>\n{statement}\n<<<\n\n"
    )


def _doc(*parts):
    return HEADER + "".join(parts)


SECTION_OPEN = "[[SECTION]]\nUID: S-1\nTITLE: Section one\n\n"
SECTION_CLOSE = "[[/SECTION]]\n"


def test_001_blocks_keep_the_text_and_have_keys():
    text = _doc(SECTION_OPEN, _req("R-1", "one"), SECTION_CLOSE)
    blocks = split_blocks(text)
    assert "".join(b.text for b in blocks) == text
    assert [b.key for b in blocks] == [
        "header",
        "UID:S-1",
        "UID:R-1",
        "close:UID:S-1",
    ]
    assert blocks[2].title == "T"


def test_002_a_marker_inside_a_multiline_value_does_not_split():
    text = _doc(_req("R-1", "line\n[REQUIREMENT]\nnot a node\n[[/SECTION]]"))
    blocks = split_blocks(text)
    assert [b.kind for b in blocks] == ["header", "REQUIREMENT"]
    assert "".join(b.text for b in blocks) == text


def test_003_mid_wins_over_uid_and_a_block_without_identity_is_hashed():
    text = (
        "[DOCUMENT]\nTITLE: x\n\n"
        "[REQUIREMENT]\nMID: abc\nUID: R-1\nTITLE: t\n\n"
        "[TEXT]\nSTATEMENT: >>>\nfree\n<<<\n"
    )
    keys = [b.key for b in split_blocks(text)]
    assert keys[1] == "MID:abc"
    assert keys[2].startswith("hash:TEXT:")


def test_010_nothing_changed():
    text = _doc(_req("R-1", "one"), _req("R-2", "two"))
    regions = merge3(text, text, text)
    assert {r.kind for r in regions} == {SAME}
    assert assemble(regions, {}) == text


def test_011_changes_on_different_nodes_merge_without_conflict():
    base = _doc(_req("R-1", "one"), _req("R-2", "two"))
    local = _doc(_req("R-1", "one local"), _req("R-2", "two"))
    server = _doc(_req("R-1", "one"), _req("R-2", "two server"))
    regions = merge3(base, local, server)
    assert conflict_indexes(regions) == []
    assert assemble(regions, {}) == _doc(
        _req("R-1", "one local"), _req("R-2", "two server")
    )
    assert {r.kind for r in regions} == {SAME, LOCAL, SERVER}


def test_012_the_same_change_on_both_sides_is_not_a_conflict():
    base = _doc(_req("R-1", "one"))
    both = _doc(_req("R-1", "one changed"))
    regions = merge3(base, both, both)
    assert conflict_indexes(regions) == []
    assert assemble(regions, {}) == both


def test_013_two_different_changes_of_a_node_conflict():
    base = _doc(_req("R-1", "one"), _req("R-2", "two"))
    local = _doc(_req("R-1", "one local"), _req("R-2", "two"))
    server = _doc(_req("R-1", "one server"), _req("R-2", "two"))
    regions = merge3(base, local, server)
    [index] = conflict_indexes(regions)
    conflict = regions[index]
    assert conflict.kind == CONFLICT
    assert "one local" in conflict.local_text
    assert "one server" in conflict.server_text
    assert "one" in conflict.base_text
    for choice, expected in (
        ("local", "one local"),
        ("server", "one server"),
    ):
        text = assemble(regions, {index: conflict.choice_text(choice)})
        assert expected in text and "two" in text
    both = assemble(regions, {index: conflict.choice_text("both")})
    assert "one local" in both and "one server" in both


def test_014_a_deleted_node_against_a_changed_one_conflicts():
    base = _doc(_req("R-1", "one"), _req("R-2", "two"))
    local = _doc(_req("R-2", "two"))
    server = _doc(_req("R-1", "one changed"), _req("R-2", "two"))
    regions = merge3(base, local, server)
    [index] = conflict_indexes(regions)
    assert regions[index].local == []
    assert assemble(regions, {index: ""}) == _doc(_req("R-2", "two"))


def test_015_a_node_added_by_one_side_is_kept():
    base = _doc(_req("R-1", "one"))
    local = _doc(_req("R-1", "one"), _req("R-3", "three"))
    server = _doc(_req("R-0", "zero"), _req("R-1", "one"))
    regions = merge3(base, local, server)
    assert conflict_indexes(regions) == []
    merged = assemble(regions, {})
    assert merged.index("R-0") < merged.index("R-1") < merged.index("R-3")


def test_016_a_section_title_and_its_content_changed_apart_merge():
    base = _doc(SECTION_OPEN, _req("R-1", "one"), SECTION_CLOSE)
    local = _doc(
        SECTION_OPEN.replace("Section one", "Section 1"),
        _req("R-1", "one"),
        SECTION_CLOSE,
    )
    server = _doc(SECTION_OPEN, _req("R-1", "one server"), SECTION_CLOSE)
    regions = merge3(base, local, server)
    assert conflict_indexes(regions) == []
    merged = assemble(regions, {})
    assert "Section 1" in merged and "one server" in merged


def test_017_the_header_is_a_block_too():
    base = _doc(_req("R-1", "one"))
    local = base.replace("TITLE: Spec", "TITLE: Spec local")
    server = base.replace("TITLE: Spec", "TITLE: Spec server")
    regions = merge3(base, local, server)
    assert regions[0].kind == CONFLICT


def test_018_a_file_added_on_both_sides_conflicts_where_it_differs():
    local = _doc(_req("R-1", "one"), _req("R-2", "local"))
    server = _doc(_req("R-1", "one"), _req("R-2", "server"))
    regions = merge3("", local, server)
    assert [r.kind for r in regions].count(CONFLICT) == 1
    assert regions[0].kind == SAME
