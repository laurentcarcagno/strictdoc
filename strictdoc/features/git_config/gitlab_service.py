"""
Creation of the repositories on the GitLab instance of the project.

The token is read from the environment variable that the configuration names,
at the time of the call; it is never stored or logged.
"""

import os
import re
from typing import Any, Dict, Optional

import gitlab
from gitlab.exceptions import GitlabError, GitlabGetError

from strictdoc.features.git_config.config import GitConfig

REPOSITORY_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
GROUP_PATH_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]*(/[A-Za-z0-9][A-Za-z0-9_.-]*)*$"
)


class GitLabServiceError(Exception):
    pass


class GitLabService:
    def __init__(self, config: GitConfig, client: Optional[Any] = None) -> None:
        self.config = config
        self._client = client

    def _connect(self) -> Any:
        if self._client is None:
            token = os.environ.get(self.config.token_env, "")
            if token == "":
                raise GitLabServiceError(
                    f"The environment variable {self.config.token_env} "
                    "holds no GitLab token."
                )
            self._client = gitlab.Gitlab(
                self.config.gitlab_url,
                private_token=token,
                ssl_verify=self.config.ca_bundle
                or os.environ.get("GIT_SSL_CAINFO")
                or True,
            )
        return self._client

    def create_repository(self, group_path: str, name: str) -> str:
        """Create the project in the group (and its parents); return its URL."""
        if REPOSITORY_NAME_PATTERN.match(name) is None:
            raise GitLabServiceError(f"Not a repository name: {name!r}.")
        if GROUP_PATH_PATTERN.match(group_path) is None:
            raise GitLabServiceError(f"Not a group path: {group_path!r}.")
        client = self._connect()
        try:
            group_id = self._ensure_group(client, group_path)
            project = client.projects.create(
                {"name": name, "path": name, "namespace_id": group_id}
            )
        except GitlabError as error:
            raise GitLabServiceError(f"GitLab refused: {error}") from error
        return str(project.http_url_to_repo)

    def ensure_repository(self, group_path: str, name: str) -> bool:
        """Create the project if it does not exist; True when it was created."""
        if REPOSITORY_NAME_PATTERN.match(name) is None:
            raise GitLabServiceError(f"Not a repository name: {name!r}.")
        if GROUP_PATH_PATTERN.match(group_path) is None:
            raise GitLabServiceError(f"Not a group path: {group_path!r}.")
        client = self._connect()
        try:
            client.projects.get(f"{group_path}/{name}")
            return False
        except GitlabGetError:
            pass
        except GitlabError as error:
            raise GitLabServiceError(f"GitLab refused: {error}") from error
        self.create_repository(group_path, name)
        return True

    @staticmethod
    def _ensure_group(client: Any, group_path: str) -> int:
        parts = group_path.split("/")
        parent_id: Optional[int] = None
        for depth in range(1, len(parts) + 1):
            full_path = "/".join(parts[:depth])
            try:
                group = client.groups.get(full_path)
            except GitlabGetError:
                data: Dict[str, Any] = {
                    "name": parts[depth - 1],
                    "path": parts[depth - 1],
                }
                if parent_id is not None:
                    data["parent_id"] = parent_id
                group = client.groups.create(data)
            parent_id = int(group.id)
        assert parent_id is not None
        return parent_id
