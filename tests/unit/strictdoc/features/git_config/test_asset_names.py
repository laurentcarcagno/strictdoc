from types import SimpleNamespace

from strictdoc.features.git_config.asset_names import asset_folder_names


def _node(mid: str, uid: str = "", children=()):  # type: ignore[no-untyped-def]
    return SimpleNamespace(
        reserved_mid=mid,
        reserved_uid=uid or None,
        section_contents=list(children),
    )


def test_names_of_a_node_and_its_descendants() -> None:
    tree = _node("m1", "REQ 1/a", [_node("m2", "REQ-2"), _node("m3")])
    assert asset_folder_names(tree) == [
        "m1",
        "REQ_1_a",
        "m2",
        "REQ-2",
        "m3",
    ]


def test_node_without_children_attribute() -> None:
    leaf = SimpleNamespace(reserved_mid="m", reserved_uid=None)
    assert asset_folder_names(leaf) == ["m"]
