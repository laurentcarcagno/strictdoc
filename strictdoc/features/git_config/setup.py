"""Creation of the committer of a project, from its configuration."""

import os
from typing import Any, List, Optional

from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.git_config.asset_names import asset_folder_names
from strictdoc.features.git_config.committer import GitCommitter
from strictdoc.features.git_config.git_service import Author, GitService


def find_project_root(input_path: str) -> Optional[str]:
    """The innermost Git repository that contains the input path."""
    current = os.path.realpath(input_path)
    if not os.path.isdir(current):
        current = os.path.dirname(current)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def create_committer(project_config: ProjectConfig) -> Optional[GitCommitter]:
    if not project_config.is_activated_git():
        return None
    assert project_config.git is not None
    assert project_config.input_paths is not None
    author = Author(
        project_config.git.author_name, project_config.git.author_email
    )
    root = find_project_root(project_config.input_paths[0])
    if root is None:
        return None
    return GitCommitter(
        GitService(root),
        lambda: author,
        use_lfs=project_config.git.use_lfs,
        asset_warning_bytes=project_config.git.asset_warning_bytes,
    )


def collect_node_assets(node: Any) -> List[str]:
    """Call before a node is deleted: the asset folders it owns."""
    return asset_folder_names(node)


def remove_node_assets(
    project_config: ProjectConfig,
    committer: Optional[GitCommitter],
    document: Any,
    names: List[str],
) -> None:
    """Call after a node is deleted, with what collect_node_assets returned."""
    if committer is None or document.meta is None:
        return
    assert project_config.input_paths is not None
    base = os.path.dirname(os.path.abspath(project_config.input_paths[0]))
    assets_dir = os.path.join(
        base, document.meta.input_doc_assets_dir_rel_path.relative_path
    )
    committer.on_node_deleted(assets_dir, names)
