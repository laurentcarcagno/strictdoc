"""The names of the _assets sub-folders that belong to a node and its children."""

from typing import Any, List


def asset_folder_names(node: Any) -> List[str]:
    """
    A node's files are in _assets/<MID> or, without MIDs, _assets/<UID> with
    spaces and slashes replaced (see resolve_uploaded_asset_subfolder).
    """
    names: List[str] = []
    mid = getattr(node, "reserved_mid", None)
    if mid:
        names.append(str(mid))
    uid = getattr(node, "reserved_uid", None)
    if uid:
        names.append(str(uid).replace(" ", "_").replace("/", "_"))
    for child in getattr(node, "section_contents", None) or []:
        names.extend(asset_folder_names(child))
    return names
