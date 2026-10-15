"""
The Git operations of the configuration management, on a local project.

A project is a repository whose documents may be submodules. A path is always
committed in the repository that owns it; a commit in a submodule is followed by
a commit of the new pointer in each parent up to the project root. Only the
given paths are committed, never the rest of the working tree. Nothing is ever
merged or forced: a push that is not a fast-forward is refused.
"""

import os
import re
import urllib.parse
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

# GitPython refuses to be imported when the git program is missing, which
# would stop the whole server. With "quiet" only the use of Git fails.
os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")

from git import GitCommandError, Repo  # noqa: E402

from strictdoc.features.git_config.versioning import (
    NoMajorVersionToTag,
    latest_valid_tag,
    next_intermediate_tag,
    next_major_tag,
)

REMOTE = "origin"
SUBMODULE_MODE = "160000"
DEFAULT_IDENTITY_NAME = "Laurent Carcagno"
DEFAULT_IDENTITY_EMAIL = "laurent.carcagno@hemeria-group.com"


class GitServiceError(Exception):
    pass


@dataclass(frozen=True)
class Author:
    name: str
    email: str

    @property
    def line(self) -> str:
        return f"{self.name} <{self.email}>"


@dataclass(frozen=True)
class RepositoryState:
    relative_path: str
    branch: str
    latest_tag: str
    next_intermediate: str
    next_major: Optional[str]
    dirty: bool


SCP_URL_PATTERN = re.compile(
    r"^[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+:[A-Za-z0-9_./-]+$"
)


class GitService:
    def __init__(
        self,
        project_root: str,
        allowed_url_schemes: Tuple[str, ...] = ("https", "ssh"),
        token_env: str = "",
        ca_bundle: str = "",
    ) -> None:
        self.project_root = os.path.realpath(project_root)
        self.allowed_url_schemes = allowed_url_schemes
        # The name of the environment variable that holds the token of the
        # remote (never the token itself) and the CA bundle of its server.
        self.token_env = token_env
        self.ca_bundle = ca_bundle

    # ---- Repositories

    def repository_root(self, path: str) -> str:
        """The innermost repository that contains the path."""
        real_path = os.path.realpath(path)
        if not self._is_inside(real_path, self.project_root):
            raise GitServiceError(f"{path} is outside of the project.")
        current = (
            real_path
            if os.path.isdir(real_path)
            else os.path.dirname(real_path)
        )
        while True:
            if os.path.exists(os.path.join(current, ".git")):
                return current
            if current == self.project_root:
                raise GitServiceError(f"{path} is not in a Git repository.")
            current = os.path.dirname(current)

    @staticmethod
    def _is_inside(path: str, folder: str) -> bool:
        return path == folder or path.startswith(folder + os.sep)

    def _repo(self, root: str, author: Optional[Author] = None) -> Repo:
        repo = Repo(root)
        identity = author or Author(
            DEFAULT_IDENTITY_NAME, DEFAULT_IDENTITY_EMAIL
        )
        repo.git.update_environment(
            GIT_COMMITTER_NAME=identity.name,
            GIT_COMMITTER_EMAIL=identity.email,
            GIT_AUTHOR_NAME=identity.name,
            GIT_AUTHOR_EMAIL=identity.email,
            GIT_TERMINAL_PROMPT="0",
            **self._remote_environment(repo),
        )
        return repo

    def _remote_environment(self, repo: Repo) -> Dict[str, str]:
        """
        What git needs to reach the remote: the CA bundle, and the token for
        the host of the remote (an https URL), given through a credential
        helper that reads the environment variable when git runs it. The token
        is in no command line, no file and no URL.
        """
        found: Dict[str, str] = {}
        if self.ca_bundle:
            found["GIT_SSL_CAINFO"] = self.ca_bundle
        if self.token_env and os.environ.get(self.token_env):
            try:
                url = repo.remotes[REMOTE].url
            except (IndexError, AttributeError):
                return found
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme == "https" and parsed.hostname:
                helper = (
                    "!f() { echo username=oauth2; "
                    f'echo "password=${self.token_env}"; }}; f'
                )
                found.update(
                    GIT_CONFIG_COUNT="1",
                    GIT_CONFIG_KEY_0=f"credential.https://{parsed.hostname}.helper",
                    GIT_CONFIG_VALUE_0=helper,
                )
        return found

    # ---- Commits

    def commit_paths(
        self, paths: Sequence[str], message: str, author: Author
    ) -> bool:
        """Commit the paths in their repositories. True if a commit was made."""
        by_repository: Dict[str, List[str]] = {}
        for path in paths:
            root = self.repository_root(path)
            by_repository.setdefault(root, []).append(os.path.realpath(path))

        committed = False
        for root, repository_paths in by_repository.items():
            if self._commit_in_repository(
                root, repository_paths, message, author
            ):
                committed = True
                self._commit_pointers(root, author)
        return committed

    def _commit_in_repository(
        self, root: str, paths: List[str], message: str, author: Author
    ) -> bool:
        repo = self._repo(root, author)
        relative = [os.path.relpath(path, root) for path in paths]
        try:
            repo.git.add("-A", "--", *relative)
            if repo.git.diff("--cached", "--name-only", "--", *relative) == "":
                return False
            repo.git.commit(
                "-m",
                message,
                "--author",
                author.line,
                "--only",
                "--",
                *relative,
            )
        except GitCommandError as error:
            raise GitServiceError(
                f"commit failed in {root}: {error}"
            ) from error
        return True

    def _commit_pointers(self, root: str, author: Author) -> None:
        """After a commit in a submodule, record it in each parent."""
        current = root
        while current != self.project_root:
            parent = self.repository_root(os.path.dirname(current))
            parent_repo = self._repo(parent, author)
            relative = os.path.relpath(current, parent)
            tracked = parent_repo.git.ls_files("-s", "--", relative)
            if not tracked.startswith(SUBMODULE_MODE):
                return
            parent_repo.git.add("--", relative)
            if (
                parent_repo.git.diff("--cached", "--name-only", "--", relative)
                == ""
            ):
                return
            sha = self._repo(current).git.rev_parse("--short", "HEAD")
            parent_repo.git.commit(
                "-m",
                f"chore(submodule): update {os.path.basename(current)} to {sha}",
                "--author",
                author.line,
                "--only",
                "--",
                relative,
            )
            current = parent

    def diff_of(self, path: str) -> str:
        """The unified diff (no context) of a path against HEAD."""
        root = self.repository_root(path)
        relative = os.path.relpath(os.path.realpath(path), root)
        repo = self._repo(root)
        try:
            return str(repo.git.diff("HEAD", "-U0", "--", relative))
        except GitCommandError:
            return ""

    # ---- Tags

    def list_tags(self, path: str) -> List[str]:
        repo = self._repo(self.repository_root(path))
        return [tag.name for tag in repo.tags]

    def next_intermediate_tag(self, path: str) -> str:
        return next_intermediate_tag(self.list_tags(path))

    def next_major_tag(self, path: str) -> str:
        try:
            return next_major_tag(self.list_tags(path))
        except NoMajorVersionToTag as error:
            raise GitServiceError(str(error)) from error

    def create_tag(
        self, path: str, name: str, author: Optional[Author] = None
    ) -> None:
        repo = self._repo(self.repository_root(path), author)
        if name in [tag.name for tag in repo.tags]:
            raise GitServiceError(f"The tag {name} already exists.")
        try:
            repo.git.tag("-a", name, "-m", f"Version {name}")
        except GitCommandError as error:
            raise GitServiceError(f"tag failed: {error}") from error

    # ---- Push

    def remote_url(self, path: str) -> str:
        """The URL of the remote of the repository ("" if it has none)."""
        repo = self._repo(self.repository_root(path))
        if REMOTE not in [remote.name for remote in repo.remotes]:
            return ""
        return str(repo.remotes[REMOTE].url)

    def add_remote(self, path: str, url: str) -> None:
        repo = self._repo(self.repository_root(path))
        repo.create_remote(REMOTE, url)

    def has_remote(self, path: str) -> bool:
        """The repository has the remote that a push goes to."""
        repo = self._repo(self.repository_root(path))
        return REMOTE in [remote.name for remote in repo.remotes]

    def push(self, path: str, tag: Optional[str] = None) -> None:
        """Fast-forward from the remote if needed, push the branch (and tag)."""
        root = self.repository_root(path)
        repo = self._repo(root)
        if repo.head.is_detached:
            raise GitServiceError(
                f"{root} has no branch checked out; check out a branch first."
            )
        branch = repo.active_branch.name
        try:
            repo.git.fetch(REMOTE, "--tags")
            remote_branch = f"{REMOTE}/{branch}"
            if remote_branch in [ref.name for ref in repo.remotes[0].refs]:
                behind, ahead = self._behind_ahead(repo, remote_branch)
                if behind > 0 and ahead > 0:
                    raise GitServiceError(
                        f"{branch} has diverged from {remote_branch} in {root}; "
                        "resolve it with Git."
                    )
                if behind > 0:
                    repo.git.merge("--ff-only", remote_branch)
            repo.git.push(REMOTE, branch)
            if tag is not None:
                self._push_tag(repo, tag)
        except GitCommandError as error:
            raise GitServiceError(f"push failed in {root}: {error}") from error

    @staticmethod
    def _behind_ahead(repo: Repo, remote_branch: str) -> "tuple[int, int]":
        counts = repo.git.rev_list(
            "--left-right", "--count", f"{remote_branch}...HEAD"
        )
        behind, ahead = counts.split()
        return int(behind), int(ahead)

    @staticmethod
    def _push_tag(repo: Repo, tag: str) -> None:
        local = repo.git.rev_parse(f"{tag}^{{}}")
        listing = str(
            repo.git.ls_remote(
                "--tags", REMOTE, f"refs/tags/{tag}^{{}}", f"refs/tags/{tag}"
            )
        )
        remote_shas = {line.split()[0] for line in listing.splitlines()}
        if len(remote_shas) > 0:
            if local in remote_shas:
                return
            raise GitServiceError(
                f"The tag {tag} already exists on the remote for another commit."
            )
        repo.git.push(REMOTE, f"refs/tags/{tag}")

    def push_with_submodules(self, path: str) -> None:
        """Push each submodule first, so no pointer refers to an unpublished commit."""
        root = self.repository_root(path)
        repo = self._repo(root)
        for submodule in repo.submodules:
            if os.path.isdir(submodule.abspath):
                self.push_with_submodules(str(submodule.abspath))
        self.push(root)

    # ---- Submodules

    def _check_submodule_arguments(self, url: str, path: str) -> None:
        if url.startswith("-"):
            raise GitServiceError("The URL of a submodule cannot start with -.")
        scheme = urllib.parse.urlparse(url).scheme
        is_scp_form = "ssh" in self.allowed_url_schemes and (
            SCP_URL_PATTERN.match(url) is not None
        )
        if scheme not in self.allowed_url_schemes and not is_scp_form:
            raise GitServiceError(
                f"The URL of a submodule uses one of {self.allowed_url_schemes}."
            )
        parts = path.split("/")
        if (
            path == ""
            or os.path.isabs(path)
            or any(
                part in ("", ".", "..") or part.startswith("-")
                for part in parts
            )
            or parts[0] == ".git"
            or ".git" in parts
        ):
            raise GitServiceError(f"Not a path for a submodule: {path!r}.")

    def submodule_add(
        self, path: str, url: str, relative_path: str, author: Author
    ) -> None:
        """Add the repository at url as a submodule and commit it."""
        self._check_submodule_arguments(url, relative_path)
        root = self.repository_root(path)
        repo = self._repo(root, author)
        try:
            repo.git.submodule("add", "--", url, relative_path)
            repo.git.commit(
                "-m",
                f"chore(submodule): add {relative_path}",
                "--author",
                author.line,
                "--only",
                "--",
                ".gitmodules",
                relative_path,
            )
        except GitCommandError as error:
            raise GitServiceError(f"submodule add failed: {error}") from error

    def submodule_update(self, path: str) -> None:
        """Initialise and update the submodules, recursively."""
        repo = self._repo(self.repository_root(path))
        try:
            repo.git.submodule("update", "--init", "--recursive")
        except GitCommandError as error:
            raise GitServiceError(
                f"submodule update failed: {error}"
            ) from error

    # ---- State

    def describe_repositories(self) -> List[RepositoryState]:
        """The project repository and its initialised submodules, recursively."""
        states: List[RepositoryState] = []
        self._describe(self.project_root, states)
        return states

    def _describe(self, root: str, states: List[RepositoryState]) -> None:
        repo = self._repo(root)
        tags = [tag.name for tag in repo.tags]
        latest = latest_valid_tag(tags)
        try:
            major: Optional[str] = next_major_tag(tags)
        except NoMajorVersionToTag:
            major = None
        states.append(
            RepositoryState(
                relative_path=os.path.relpath(root, self.project_root),
                branch="" if repo.head.is_detached else repo.active_branch.name,
                latest_tag=latest,
                next_intermediate=next_intermediate_tag(tags),
                next_major=major,
                dirty=repo.is_dirty(untracked_files=True),
            )
        )
        for submodule in repo.submodules:
            if os.path.exists(os.path.join(submodule.abspath, ".git")):
                self._describe(os.path.realpath(submodule.abspath), states)
