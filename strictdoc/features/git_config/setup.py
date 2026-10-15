"""Creation of the committer of a project, from its configuration."""

import os
import urllib.parse
from typing import Any, List, Optional, Tuple

from git import GitCommandError, Repo

from strictdoc.core.project_config import ProjectConfig
from strictdoc.features.git_config.asset_names import asset_folder_names
from strictdoc.features.git_config.committer import GitCommitter
from strictdoc.features.git_config.config import GitConfig
from strictdoc.features.git_config.git_service import (
    Author,
    GitService,
    GitServiceError,
)
from strictdoc.features.git_config.gitlab_service import (
    GitLabService,
    GitLabServiceError,
)


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
        GitService(
            root,
            token_env=project_config.git.token_env,
            ca_bundle=project_config.git.ca_bundle,
        ),
        lambda: author,
        use_lfs=project_config.git.use_lfs,
        asset_warning_bytes=project_config.git.asset_warning_bytes,
    )


def _split_repository_path(
    url: str, gitlab_url: str
) -> Optional[Tuple[str, str]]:
    """(group path, name) of a remote URL on the GitLab instance, or None."""
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname != urllib.parse.urlparse(gitlab_url).hostname:
        return None
    path = parsed.path.strip("/")
    path = path[: -len(".git")] if path.endswith(".git") else path
    group, _, name = path.rpartition("/")
    return (group, name) if group and name else None


def ensure_remote_repository(
    service: GitService, root: str, config: GitConfig
) -> str:
    """
    The remote of the repository is a project of the GitLab instance; it is
    created when it does not exist. Returns "" or what went wrong. Nothing is
    done without a token, or for a remote of another server.
    """
    if not os.environ.get(config.token_env):
        return ""
    url = service.remote_url(root)
    split = _split_repository_path(url, config.gitlab_url) if url else None
    if split is None:
        return ""
    try:
        GitLabService(config).ensure_repository(*split)
    except GitLabServiceError as error:
        return str(error)
    return ""


def provision_repository(folder: str, slug: str, config: GitConfig) -> str:
    """
    A project that the web interface creates: a Git repository with a first
    commit, the project of that name in the GitLab group of the configuration,
    the remote origin, and the first push. Returns "" or what went wrong; the
    project works without the remote. Nothing is done without a token.
    """
    if not os.environ.get(config.token_env):
        return ""
    try:
        Repo.init(folder, initial_branch="main")
        service = GitService(
            folder, token_env=config.token_env, ca_bundle=config.ca_bundle
        )
        author = Author(config.author_name, config.author_email)
        service.commit_paths([folder], f"Create the project {slug}", author)
        GitLabService(config).ensure_repository(config.group_path, slug)
        url = f"{config.gitlab_url.rstrip('/')}/{config.group_path}/{slug}.git"
        service.add_remote(folder, url)
        service.push(folder)
    except (GitServiceError, GitLabServiceError, GitCommandError) as error:
        return str(error)
    return ""


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
