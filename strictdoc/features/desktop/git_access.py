"""
What Git may use to reach a remote, in the desktop application: the token of
the signed-in user for the GitLab of the session, and nothing else.

Every Git command of the application runs with the environment that
GitAccess.build_environment gives:

- the list of the credential helpers is emptied first (an entry
  "credential.helper" with no value), so that the helper of the computer
  neither gives a credential nor stores the token. Git reads the entries of the
  environment after those of every file, so the reset also clears a helper of
  the system file, of the global file or of the ".git/config" of the repository;
- then one helper for the origin of the session (scheme, host and port), and
  for no other: another host, a submodule of another host or an address that a
  redirect leads to get no token;
- the helper reads the token in the environment of the Git process when Git
  starts it, and answers to the operation "get" only. The token is in no
  command line, no file, no URL and no value of the Git configuration. Only the
  commands that reach a remote have it in their environment;
- Git never asks the user: no terminal prompt, no askpass program;
- a transfer that stops for more than the time limit ends, with no help of the
  operating system, so that the limit holds on Windows too;
- the personal setup of the computer is not read: the home folder of the Git
  processes is an empty folder of the application (no ".netrc", no keys, no
  hooks, no signature), and the global configuration is a file of the
  application that keeps only the settings of the network of the user (proxy,
  certificates). The configuration of the system stays, for the filters;
- an address with a user name or a password is refused (see
  check_repository_for_network), and so is a header of authentication of the
  repository: nothing but the token of the session goes to the server;
- only https, http and file are transports. SSH, the "git" protocol and the
  programs of "ext::" are never run.

The signed-in user decides: without a session, or when the access token has
ended, no credential is given at all.

@relation(SDOC-SRS-1239, scope=file)
@relation(SDOC-SRS-1241, scope=file)
@relation(SDOC-SRS-1257, scope=file)
"""

import os
import re
import subprocess
import sys
import threading
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Tuple,
)
from urllib.parse import urlsplit

# GitPython refuses to be imported when the git program is missing, which
# would stop the whole application. With "quiet" only the use of Git fails.
os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")

from git import GitCommandError  # noqa: E402

from strictdoc.features.desktop.bundled_tools import (  # noqa: E402
    get_hidden_window_flags,
    get_library_path_overrides,
    get_system_program_environment,
)
from strictdoc.features.desktop.paths import get_data_dir  # noqa: E402
from strictdoc.features.desktop.token_store import TokenKeeper  # noqa: E402
from strictdoc.features.git_config.git_service import (  # noqa: E402
    REMOTE,
    Author,
    GitService,
    GitServiceError,
    LineRevision,
    TagInfo,
)
from strictdoc.features.i18n.i18n import gettext  # noqa: E402
from strictdoc.helpers.file_system import file_open_read_utf8  # noqa: E402

if TYPE_CHECKING:
    from git import Repo

# The variable of the Git process that holds the token. The helper reads it.
GIT_TOKEN_VARIABLE = "STRICTDOC_DESKTOP_GIT_TOKEN"

# The variable that the GitLab features of the project read the token from. In
# the application, it names a variable that is never set: the project
# configuration cannot send the token to the address of its choice, and nothing
# creates a repository or a group on GitLab.
NO_GITLAB_TOKEN_VARIABLE = "STRICTDOC_DESKTOP_NO_GITLAB_TOKEN"

# A transfer that stops for this time ends.
NETWORK_TIMEOUT_SECONDS = 30.0

# The transports of Git that the application runs.
ALLOWED_PROTOCOLS = "https:http:file"

# The lines of ".git/info/exclude" that this application writes are in one
# block between these two lines. The rest of the file is the user's.
EXCLUDE_BLOCK_BEGIN = "# BEGIN StrictDoc copies of colleagues (do not edit)"
EXCLUDE_BLOCK_END = "# END StrictDoc copies of colleagues"

_PROFILE_FOLDER_NAME = "git"
_HOME_FOLDER_NAME = "home"
_CONFIGURATION_FILE_NAME = "gitconfig"

_DEFAULT_PORTS = {"http": 80, "https": 443}
_HOST_PATTERN = re.compile(r"^[a-z0-9._:-]+$")
# A token never holds a character that could add a line to the answer of the
# helper.
_TOKEN_PATTERN = re.compile(r"^[\x21-\x7e]+$")

# The settings of the global configuration that the application keeps: the
# network of the company. They are set for every address (http.<name>) or for
# one (http.<address>.<name>).
_KEPT_SETTING_NAMES = frozenset(
    {
        "proxy",
        "noproxy",
        "sslcainfo",
        "sslcapath",
        "sslbackend",
        "schannelcheckrevoke",
        "schannelusesslcainfo",
    }
)

_CREDENTIAL_HELPER = (
    '!f() { test "$1" = get || exit 0; echo username=oauth2; '
    f'echo "password=${GIT_TOKEN_VARIABLE}"; }}; f'
)

_REMOTE_KEY_PATTERN = re.compile(r"^remote\.(.+)\.(?:url|pushurl)$")
_SUBMODULE_KEY_PATTERN = re.compile(r"^submodule\..+\.url$")
_ADDRESS_HEADER_KEY_PATTERN = re.compile(r"^http\..+\.extraheader$", re.I)


@dataclass(frozen=True)
class UnsentCommits:
    """The commits of a repository that the server does not have."""

    branch: str
    # The commit that is at the head of the branch when it is read: what is
    # sent, whatever is committed next.
    head: str
    count: int
    # The author address of each of them.
    author_emails: Tuple[str, ...]
    # The address of the remote "origin", "" when there is none.
    origin_url: str
    # Every address that "git push origin" writes to: "pushurl" and
    # "pushInsteadOf" can make it other than the address to read from.
    push_urls: Tuple[str, ...] = ()

    def get_destinations(self) -> Tuple[str, ...]:
        """The addresses that the commits can reach, the one to read too."""
        return (self.origin_url, *self.push_urls)


# What a Git operation that is not finished leaves in the Git folder.
_OPERATION_MARKERS = (
    "MERGE_HEAD",
    "CHERRY_PICK_HEAD",
    "REVERT_HEAD",
    "REBASE_HEAD",
    "rebase-merge",
    "rebase-apply",
)


class UnsafeRepositoryError(GitServiceError):
    """
    The repository holds an address with credentials or a header of
    authentication, which the application does not use. The message holds no
    secret.
    """


class GitAccess:
    """
    What the Git commands of the application may use, read at the time of each
    command: the GitLab of the session and its access token. Without
    arguments, there is no session, so no credential.
    """

    def __init__(
        self,
        *,
        get_gitlab_url: Optional[Callable[[], str]] = None,
        get_access_token: Optional[Callable[[], Optional[str]]] = None,
        network_timeout_seconds: float = NETWORK_TIMEOUT_SECONDS,
        profile_directory: Optional[Path] = None,
    ) -> None:
        self._get_gitlab_url: Callable[[], str] = (
            get_gitlab_url if get_gitlab_url is not None else lambda: ""
        )
        self._get_access_token: Callable[[], Optional[str]] = (
            get_access_token if get_access_token is not None else lambda: None
        )
        self.network_timeout_seconds: float = network_timeout_seconds
        self._profile: GitProfile = GitProfile(profile_directory)

    def get_access_token(self) -> Optional[str]:
        """The access token of the session, None without one."""
        return self._get_access_token()

    def build_environment(
        self,
        *,
        is_network: bool = True,
        credentials: Optional[Tuple[str, Optional[str]]] = None,
    ) -> Dict[str, str]:
        """
        The environment variables of one Git command. The token is in the
        environment of a command that reaches a remote only.

        With credentials, a GitLab and an access token that the caller read
        from one session, they are used in place of the ones of the session at
        this moment: the user that the caller checked is the one whose token
        goes.
        """
        if credentials is not None:
            gitlab_url, access_token = credentials
        else:
            gitlab_url = self._get_gitlab_url()
            access_token = self._get_access_token() if is_network else None
        environment = build_git_environment(
            gitlab_url,
            access_token if is_network else None,
            network_timeout_seconds=self.network_timeout_seconds,
        )
        environment.update(self._profile.get_environment())
        # For GitPython too: the Git of the system does not load the
        # libraries of a frozen package.
        environment.update(get_library_path_overrides())
        return environment


def create_git_access(keeper: TokenKeeper) -> GitAccess:
    """The access of the user who is signed in, or none when nobody is."""
    return GitAccess(
        get_gitlab_url=lambda: keeper.gitlab_url,
        get_access_token=keeper.get_access_token,
    )


def get_credential_origin(gitlab_url: str) -> Optional[str]:
    """
    The origin of a GitLab for the configuration of Git: the scheme, the host
    and the port (when it is not the one of the scheme). None when the address
    is not an address of a web server that Git can match.
    """
    parts = urlsplit(gitlab_url.strip())
    scheme = parts.scheme.lower()
    hostname = parts.hostname
    if scheme not in _DEFAULT_PORTS or hostname is None:
        return None
    if _HOST_PATTERN.match(hostname) is None:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    host = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None and port != _DEFAULT_PORTS[scheme]:
        host = f"{host}:{port}"
    return f"{scheme}://{host}"


def has_credentials_in_url(address: str) -> bool:
    """
    True when the address of a web server holds a user name or a password.
    An address that cannot be read counts as one that does.
    """
    try:
        parts = urlsplit(address.strip())
        return parts.scheme.lower() in _DEFAULT_PORTS and (
            parts.username is not None or parts.password is not None
        )
    except ValueError:
        return True


def build_git_environment(
    gitlab_url: str,
    access_token: Optional[str],
    *,
    network_timeout_seconds: float = NETWORK_TIMEOUT_SECONDS,
) -> Dict[str, str]:
    """
    The environment variables of the configuration of Git that every command
    of the application gets (GitAccess adds the folders of the profile). With
    no token, or with a GitLab that is not an address, the helpers of the
    computer are still cleared and no credential is given.
    """
    entries: List[Tuple[str, str]] = [("credential.helper", "")]
    environment: Dict[str, str] = {
        "GIT_TERMINAL_PROMPT": "0",
        # Empty: no program is run to ask for a password.
        "GIT_ASKPASS": "",
        "SSH_ASKPASS": "",
        "GCM_INTERACTIVE": "never",
        "GIT_ALLOW_PROTOCOL": ALLOWED_PROTOCOLS,
        # A command that only reads never writes the index (no "index.lock"
        # left by a command that is stopped).
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_HTTP_LOW_SPEED_LIMIT": "1",
        "GIT_HTTP_LOW_SPEED_TIME": str(max(1, int(network_timeout_seconds))),
    }
    origin = get_credential_origin(gitlab_url)
    if (
        origin is not None
        and access_token is not None
        and _TOKEN_PATTERN.match(access_token) is not None
    ):
        entries.append((f"credential.{origin}.helper", _CREDENTIAL_HELPER))
        environment[GIT_TOKEN_VARIABLE] = access_token
    entries.extend(
        [
            # No header of authentication from a file of the computer or of
            # the repository.
            ("http.extraHeader", ""),
            # Git itself stops at an address with a password.
            ("transfer.credentialsInUrl", "die"),
        ]
    )
    environment["GIT_CONFIG_COUNT"] = str(len(entries))
    for index_, (key_, value_) in enumerate(entries):
        environment[f"GIT_CONFIG_KEY_{index_}"] = key_
        environment[f"GIT_CONFIG_VALUE_{index_}"] = value_
    return environment


def check_repository_for_network(
    folder: str, environment: Dict[str, str]
) -> None:
    """
    Raise UnsafeRepositoryError when the repository of the folder holds what
    would send something else than the token of the session to a server: an
    address with a user name or a password (the address of a remote, an
    address that "insteadOf" gives, the address of a submodule), or a header
    of authentication for one address. Call it before a command that reaches a
    remote.
    """
    inspection_environment = _get_inspection_environment(environment)
    local_entries = _read_configuration(
        folder, inspection_environment, "--local"
    )
    if local_entries is None:
        # Not a repository: the command that follows tells it.
        return
    entries = list(local_entries)
    modules_path = os.path.join(folder, ".gitmodules")
    if os.path.isfile(modules_path):
        module_entries = _read_configuration(
            folder, inspection_environment, "--file", ".gitmodules"
        )
        if module_entries is not None:
            entries.extend(module_entries)
    addresses: List[str] = []
    remote_names: List[str] = []
    for key_, value_ in entries:
        if _ADDRESS_HEADER_KEY_PATTERN.match(key_) is not None:
            raise UnsafeRepositoryError(
                gettext(
                    "The project sets a header of authentication for an "
                    "address: the application does not use it."
                )
            )
        remote_match = _REMOTE_KEY_PATTERN.match(key_)
        if remote_match is not None:
            addresses.append(value_)
            if remote_match.group(1) not in remote_names:
                remote_names.append(remote_match.group(1))
        elif _SUBMODULE_KEY_PATTERN.match(key_) is not None:
            addresses.append(value_)
    for name_ in remote_names:
        for arguments_ in (
            ["ls-remote", "--get-url", name_],
            ["remote", "get-url", "--push", "--all", name_],
        ):
            addresses.extend(
                _run_inspection(folder, inspection_environment, arguments_)
            )
    if any(has_credentials_in_url(address_) for address_ in addresses):
        raise UnsafeRepositoryError(
            gettext(
                "The address of the server of the project holds a user name "
                "or a password: the application does not use it."
            )
        )


class GitProfile:
    """
    The personal setup that the Git commands get in place of the one of the
    computer: an empty home folder, and a global configuration that keeps the
    settings of the network of the user, read in the global configuration of
    the computer. The file is made again when the global configuration changes.
    """

    def __init__(self, directory: Optional[Path] = None) -> None:
        self._directory: Optional[Path] = directory
        self._lock: threading.Lock = threading.Lock()
        self._signature: Optional[Tuple[object, ...]] = None

    def get_environment(self) -> Dict[str, str]:
        directory = (
            self._directory
            if self._directory is not None
            else get_data_dir() / _PROFILE_FOLDER_NAME
        )
        home = directory / _HOME_FOLDER_NAME
        configuration_path = directory / _CONFIGURATION_FILE_NAME
        with self._lock:
            # The file may hold the password of a proxy: only the user reads
            # it.
            for folder_ in (directory, home):
                folder_.mkdir(mode=0o700, parents=True, exist_ok=True)
                os.chmod(folder_, 0o700)
            signature = (str(directory), *_get_source_signature())
            if signature != self._signature or not configuration_path.exists():
                _write_kept_settings(configuration_path, home)
                self._signature = signature
        return {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "XDG_CONFIG_HOME": str(home),
            "GIT_CONFIG_GLOBAL": str(configuration_path),
        }


class DesktopGitService(GitService):
    """
    The Git operations of a project of the desktop application. Each command
    gets the environment of GitAccess and no other way to a credential: the
    token of the project configuration (GitConfig) and the CA bundle of that
    configuration are not used. The commands that reach a remote check the
    repository first and are the only ones that have the token.
    """

    def __init__(self, project_root: str, git_access: GitAccess) -> None:
        super().__init__(project_root)
        self._git_access: GitAccess = git_access
        self._state: threading.local = threading.local()

    # ---- What the sending of the changes reads

    def read_unsent_commits(self, path: str) -> Optional[UnsentCommits]:
        """
        The commits of the branch that no branch of "origin" has, or None
        when there is no branch (a detached head, no commit yet). The command
        reads the repository only and never reaches the remote.
        """
        repo = self._repo(self.repository_root(path))
        try:
            if repo.head.is_detached or not repo.head.is_valid():
                return None
            branch = str(repo.active_branch.name)
            head = str(repo.head.commit.hexsha)
            listing = str(
                repo.git.log(
                    "--format=%ae", "HEAD", "--not", "--remotes=origin"
                )
            )
            try:
                origin_url = str(repo.git.remote("get-url", "origin"))
            except GitCommandError:
                origin_url = ""
            try:
                # The addresses that "git push" uses, with "pushurl" and
                # "pushInsteadOf" applied, in the environment of this service.
                push_listing = str(
                    repo.git.remote("get-url", "--push", "--all", "origin")
                )
            except GitCommandError:
                push_listing = ""
        except GitCommandError as error:
            raise GitServiceError(f"read failed: {error}") from error
        emails = tuple(line_ for line_ in listing.splitlines() if line_ != "")
        push_urls = tuple(
            line_ for line_ in push_listing.splitlines() if line_ != ""
        )
        return UnsentCommits(
            branch, head, len(emails), emails, origin_url, push_urls
        )

    def is_operation_in_progress(self, path: str) -> bool:
        """
        True while a merge, a rebase, a cherry-pick or a revert waits to be
        finished: the files of the project are then the ones of that operation.
        """
        repo = self._repo(self.repository_root(path))
        git_directory = str(repo.git_dir)
        return any(
            os.path.exists(os.path.join(git_directory, marker_))
            for marker_ in _OPERATION_MARKERS
        )

    def read_merge_key(self, path: str) -> str:
        """
        The identifier of the merge that waits ("" when none does): the commit
        of the other side. A merge that is abandoned and started again has the
        same one while the server did not move.
        """
        repo = self._repo(self.repository_root(path))
        marker = os.path.join(str(repo.git_dir), "MERGE_HEAD")
        try:
            with file_open_read_utf8(marker) as file_:
                return file_.read().strip()
        except OSError:
            return ""

    def history_of_lines(
        self, path: str, first_line: int, last_line: int, limit: int = 20
    ) -> List[LineRevision]:
        """
        The history of the lines of a node as the user may read it: no
        identifier of a commit, no header of Git in the patch, and no message
        of a merge in the words of the tool.
        """
        return [
            replace(
                revision_,
                commit="",
                subject=get_business_subject(revision_.subject),
                patch=_remove_git_header(revision_.patch),
            )
            for revision_ in super().history_of_lines(
                path, first_line, last_line, limit
            )
        ]

    def version_tags_of(self, path: str) -> List[TagInfo]:
        """The versions of the project, with what changed in words of work."""
        return [
            replace(tag_, subject=get_business_subject(tag_.subject))
            for tag_ in super().version_tags_of(path)
        ]

    def fetch_tags(self, path: str) -> None:
        """Bring the version tags that the server has."""
        with self._reach_remote(path):
            repo = self._repo(self.repository_root(path))
            try:
                repo.git.fetch(REMOTE, "--tags")
            except GitCommandError as error:
                raise GitServiceError(f"fetch failed: {error}") from error

    def has_remote_tag(self, path: str, name: str) -> bool:
        """True when the server has a tag of this name."""
        with self._reach_remote(path):
            repo = self._repo(self.repository_root(path))
            try:
                listing = str(
                    repo.git.ls_remote("--tags", REMOTE, f"refs/tags/{name}")
                )
            except GitCommandError as error:
                raise GitServiceError(f"read failed: {error}") from error
        return listing.strip() != ""

    def push_only_tag(self, path: str, name: str) -> bool:
        """
        Send this tag and nothing else, without force: the commit that it
        marks is already on the server. It returns False when the server
        already has a tag of this name (somebody published the same version
        first), and raises GitServiceError when it could not be sent.
        """
        if self.has_remote_tag(path, name):
            return False
        with self._reach_remote(path):
            repo = self._repo(self.repository_root(path))
            try:
                repo.git.push(REMOTE, f"refs/tags/{name}")
            except GitCommandError as error:
                failure = GitServiceError(f"push failed: {error}")
            else:
                return True
        # A refusal because the tag appeared meanwhile is not a failure of the
        # network.
        if self.has_remote_tag(path, name):
            return False
        raise failure

    def delete_local_tag(self, path: str, name: str) -> None:
        """Remove a tag that was not published: no orphan stays."""
        repo = self._repo(self.repository_root(path))
        try:
            repo.git.tag("-d", name)
        except GitCommandError as error:
            raise GitServiceError(f"tag removal failed: {error}") from error

    def read_head(self, path: str) -> Optional[str]:
        """The commit that the project is at, None when there is none."""
        repo = self._repo(self.repository_root(path))
        if not repo.head.is_valid():
            return None
        return str(repo.head.commit.hexsha)

    def read_heads(self, path: str, branch: str) -> "tuple[str, str]":
        """The commit of the branch here, and the one of the server."""
        repo = self._repo(self.repository_root(path))
        try:
            return (
                str(repo.git.rev_parse("HEAD")),
                str(repo.git.rev_parse(f"{REMOTE}/{branch}")),
            )
        except GitCommandError as error:
            raise GitServiceError(f"read failed: {error}") from error

    def list_touched_paths(self, path: str, head: Optional[str]) -> List[str]:
        """
        The files of the working copy that differ from this commit, as
        absolute paths: what an update, a merge that waits, or a merge that was
        abandoned changed since the commit was the head. The names are read
        with "-z", so that no name is quoted.
        """
        root = self.repository_root(path)
        repo = self._repo(root)
        try:
            listing = str(
                repo.git.diff(
                    "--name-only", "-z", head if head is not None else "HEAD"
                )
            )
        except GitCommandError as error:
            raise GitServiceError(f"diff failed: {error}") from error
        return [
            os.path.join(root, name_)
            for name_ in listing.split("\0")
            if name_ != ""
        ]

    def list_incoming_paths(self, path: str, branch: str) -> List[str]:
        """
        The files that an update from the server (a fast-forward, a merge) can
        change, as absolute paths: the ones that differ between HEAD and the
        branch of the server. Read before Git writes the files, so that the
        watcher is told before the files move.
        """
        root = self.repository_root(path)
        repo = self._repo(root)
        try:
            listing = str(
                repo.git.diff("--name-only", "-z", "HEAD", f"{REMOTE}/{branch}")
            )
        except GitCommandError as error:
            raise GitServiceError(f"diff failed: {error}") from error
        return [
            os.path.join(root, name_)
            for name_ in listing.split("\0")
            if name_ != ""
        ]

    def keep_both_versions(
        self, path: str, relative: str, copy_relative: str
    ) -> str:
        """
        Settle a file of a merge that is not a document, with no loss: the
        local version stays, and the version of the other side is saved next to
        it under the name copy_relative (the bytes as they are). When one side
        removed the file, the side that kept it wins. It returns "local" or
        "server", the side whose version is the file now. The file is added to
        the merge. The copy is not: it stays on this computer, outside of the
        index, and ".git/info/exclude" hides it, so that no commit takes it and
        nothing goes to the team.

        @relation(SDOC-SRS-1247, scope=function)
        """
        root = self.repository_root(path)
        repo = self._repo(root)
        try:
            local = self._read_stage(repo, 2, relative)
            server = self._read_stage(repo, 3, relative)
            if local is not None:
                repo.git.checkout("--ours", "--", relative)
                if server is not None:
                    # Hidden before it exists: no commit can take it.
                    self._exclude_path(repo, root, copy_relative)
                    with open(os.path.join(root, copy_relative), "wb") as file_:
                        file_.write(server)
                repo.git.add("--", relative)
                return "local"
            repo.git.checkout("--theirs", "--", relative)
            repo.git.add("--", relative)
            return "server"
        except (GitCommandError, OSError) as error:
            raise GitServiceError(f"keep failed: {error}") from error

    def prune_local_copies(self, path: str) -> List[str]:
        """
        Forget the copies of colleagues that do not exist any more: the lines
        of the block of the application in ".git/info/exclude" whose file is
        gone (the user removed it or renamed it). A file that is later saved at
        that path is then an ordinary file, and it is shared. A line that cannot
        be read back as a path is kept. It returns the paths that were
        forgotten, relative to the project.

        @relation(SDOC-SRS-1247, scope=function)
        """
        root = self.repository_root(path)
        repo = self._repo(root)
        try:
            exclude_path = self._get_exclude_path(repo, root)
            lines = _read_exclude_lines(exclude_path)
            block = _find_exclude_block(lines)
            if block is None:
                return []
            begin, end = block
            kept: List[str] = []
            forgotten: List[str] = []
            for line_ in lines[begin + 1 : end]:
                relative = _unescape_exclude_pattern(line_)
                if relative is not None and not os.path.lexists(
                    os.path.join(root, relative)
                ):
                    forgotten.append(relative)
                else:
                    kept.append(line_)
            if len(forgotten) == 0:
                return []
            new_block = (
                [EXCLUDE_BLOCK_BEGIN, *kept, EXCLUDE_BLOCK_END]
                if len(kept) > 0
                else []
            )
            _write_exclude_lines(
                exclude_path, lines[:begin] + new_block + lines[end + 1 :]
            )
        except (GitCommandError, OSError) as error:
            raise GitServiceError(f"exclude failed: {error}") from error
        return forgotten

    @staticmethod
    def _read_stage(repo: "Repo", stage: int, relative: str) -> Optional[bytes]:
        try:
            content: bytes = repo.git.show(
                f":{stage}:{relative}", stdout_as_string=False
            )
        except GitCommandError:
            return None
        return content

    def list_changed_paths(self, path: str) -> List[str]:
        """
        The files that differ from the last commit, as absolute paths: the
        modified, the deleted and the new ones that ".gitignore" does not
        ignore. A submodule is not in the list, nor is a file that waits for a
        merge to be finished.
        """
        root = self.repository_root(path)
        repo = self._repo(root)
        try:
            listing = str(
                repo.git.status(
                    "--porcelain=v1",
                    "-z",
                    "--untracked-files=all",
                    "--no-renames",
                )
            )
        except GitCommandError as error:
            raise GitServiceError(f"status failed: {error}") from error
        paths: List[str] = []
        for entry_ in listing.split("\0"):
            if len(entry_) < 4:
                continue
            status, relative = entry_[:2], entry_[3:]
            if "U" in status or status in ("AA", "DD"):
                continue
            absolute = os.path.join(root, relative)
            if os.path.isdir(os.path.join(absolute, ".git")) or os.path.isfile(
                os.path.join(absolute, ".git")
            ):
                continue
            paths.append(absolute)
        return paths

    # ---- Commands that reach a remote

    def push(self, path: str, tag: Optional[str] = None) -> None:
        """
        Fast-forward from the remote if needed, push the branch (and the tag).
        What is slow is the network, which never holds the gate of the project.
        What changes the files is the fast-forward, which holds it.
        """
        # Imported here: the module of the gate needs this one.
        from strictdoc.features.desktop.project_gate import (  # noqa: PLC0415
            get_project_gate,
        )

        with self._reach_remote(path):
            root = self.repository_root(path)
            repo = self._repo(root)
            if repo.head.is_detached:
                raise GitServiceError(
                    f"{root} has no branch checked out; check out a branch "
                    "first."
                )
            branch = repo.active_branch.name
            try:
                repo.git.fetch(REMOTE, "--tags")
                remote_branch = f"{REMOTE}/{branch}"
                if remote_branch in [
                    ref_.name for ref_ in repo.remotes[REMOTE].refs
                ]:
                    behind, ahead = self._behind_ahead(repo, remote_branch)
                    if behind > 0 and ahead > 0:
                        raise GitServiceError(
                            f"{branch} has diverged from {remote_branch} in "
                            f"{root}; resolve it with Git."
                        )
                    if behind > 0:
                        with get_project_gate(root).hold():
                            repo.git.merge("--ff-only", remote_branch)
                repo.git.push(REMOTE, branch)
                if tag is not None:
                    self._push_tag(repo, tag)
            except GitCommandError as error:
                raise GitServiceError(
                    f"push failed in {root}: {error}"
                ) from error

    def push_with_submodules(self, path: str) -> None:
        with self._reach_remote(path):
            super().push_with_submodules(path)

    def fetch(self, path: str) -> None:
        with self._reach_remote(path):
            super().fetch(path)

    def push_tags(self, path: str) -> str:
        try:
            with self._reach_remote(path):
                return super().push_tags(path)
        except UnsafeRepositoryError as error:
            return str(error)

    def submodule_add(
        self, path: str, url: str, relative_path: str, author: Author
    ) -> None:
        if has_credentials_in_url(url):
            raise UnsafeRepositoryError(
                gettext(
                    "The address of a submodule holds a user name or a "
                    "password."
                )
            )
        with self._reach_remote(path):
            super().submodule_add(path, url, relative_path, author)

    def submodule_update(self, path: str) -> None:
        with self._reach_remote(path):
            super().submodule_update(path)

    def _repo(self, root: str, author: Optional[Author] = None) -> "Repo":
        repo = super()._repo(root, author)
        repo.git.update_environment(
            **self._git_access.build_environment(
                is_network=getattr(self._state, "depth", 0) > 0
            )
        )
        return repo

    def _remote_environment(self, repo: "Repo") -> Dict[str, str]:
        # The environment of the remote is the one of _repo: GitAccess.
        del repo
        return {}

    @staticmethod
    def _get_exclude_path(repo: "Repo", root: str) -> str:
        exclude_path = str(repo.git.rev_parse("--git-path", "info/exclude"))
        if not os.path.isabs(exclude_path):
            exclude_path = os.path.join(root, exclude_path)
        return exclude_path

    @staticmethod
    def _exclude_path(repo: "Repo", root: str, relative: str) -> None:
        """
        Add the file to the block of the application in ".git/info/exclude" of
        the repository: one line, a pattern anchored by "/" that matches this
        file only. Git patterns are read with their special characters, so the
        name is escaped. The line is written once.
        """
        exclude_path = DesktopGitService._get_exclude_path(repo, root)
        pattern = "/" + _escape_exclude_pattern(relative.replace(os.sep, "/"))
        lines = _read_exclude_lines(exclude_path)
        block = _find_exclude_block(lines)
        if block is None:
            lines = [*lines, EXCLUDE_BLOCK_BEGIN, pattern, EXCLUDE_BLOCK_END]
        else:
            begin, end = block
            if pattern in lines[begin + 1 : end]:
                return
            lines.insert(end, pattern)
        _write_exclude_lines(exclude_path, lines)

    @contextmanager
    def _reach_remote(self, path: str) -> Iterator[None]:
        root = self.repository_root(path)
        check_repository_for_network(
            root, self._git_access.build_environment(is_network=False)
        )
        self._state.depth = getattr(self._state, "depth", 0) + 1
        try:
            yield
        finally:
            self._state.depth -= 1


def get_business_subject(subject: str) -> str:
    """
    The subject of a commit in words of work: the message that the application
    makes for a merge says what happened, not how.
    """
    if subject.startswith("Merge "):
        return gettext("Changes of colleagues combined with yours")
    return subject


def _remove_git_header(patch: str) -> str:
    """A patch without the line "diff --git" that Git writes above each file."""
    return "\n".join(
        line_
        for line_ in patch.split("\n")
        if not line_.startswith("diff --git")
    )


def _get_inspection_environment(environment: Dict[str, str]) -> Dict[str, str]:
    """
    The environment of the commands that read the configuration: the profile
    of the application, and no entry of the command line of Git.
    """
    merged = get_system_program_environment({**os.environ, **environment})
    for name_ in list(merged):
        if name_ == "GIT_CONFIG_COUNT" or name_.startswith(
            ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")
        ):
            del merged[name_]
    return merged


def _read_configuration(
    folder: str, environment: Dict[str, str], *selection: str
) -> Optional[List[Tuple[str, str]]]:
    try:
        result = subprocess.run(
            ["git", "config", *selection, "--list", "-z"],
            cwd=folder,
            env=environment,
            capture_output=True,
            check=False,
            timeout=30,
            creationflags=get_hidden_window_flags(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return _parse_configuration(result.stdout)


def _parse_configuration(output: bytes) -> List[Tuple[str, str]]:
    entries: List[Tuple[str, str]] = []
    for item_ in output.decode("utf8", errors="replace").split("\0"):
        if item_ == "":
            continue
        key, _, value = item_.partition("\n")
        entries.append((key, value))
    return entries


def _run_inspection(
    folder: str, environment: Dict[str, str], arguments: List[str]
) -> List[str]:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=folder,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            creationflags=get_hidden_window_flags(),
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [line_ for line_ in result.stdout.splitlines() if line_ != ""]


def _get_source_files() -> List[Path]:
    """The files that make the global configuration of the computer."""
    explicit = os.environ.get("GIT_CONFIG_GLOBAL")
    if explicit is not None:
        return [Path(explicit)]
    home = Path(os.path.expanduser("~"))
    configuration_home = os.environ.get("XDG_CONFIG_HOME")
    return [
        home / ".gitconfig",
        (
            Path(configuration_home)
            if configuration_home is not None and configuration_home != ""
            else home / ".config"
        )
        / "git"
        / "config",
    ]


def _get_source_signature() -> Tuple[object, ...]:
    signature: List[object] = []
    for path_ in _get_source_files():
        try:
            status = path_.stat()
        except OSError:
            signature.append((str(path_), None))
            continue
        signature.append((str(path_), status.st_mtime_ns, status.st_size))
    return tuple(signature)


def _write_kept_settings(configuration_path: Path, home: Path) -> None:
    """Write the file of the profile with the settings that are kept."""
    lines: List[str] = []
    if sys.platform == "win32":
        # The paths of a project can pass 260 characters.
        lines.append("[core]\n\tlongpaths = true\n")
    for key_, value_ in _read_global_configuration(home):
        section, _, rest = key_.partition(".")
        subsection, _, name = rest.rpartition(".")
        if section.lower() != "http" or name.lower() not in _KEPT_SETTING_NAMES:
            continue
        if rest == name:
            lines.append(f"[http]\n\t{name} = {_quote(value_)}\n")
        else:
            lines.append(
                f'[http "{_escape(subsection)}"]\n\t{name} = {_quote(value_)}\n'
            )
    temporary_path = configuration_path.with_name(
        f"{configuration_path.name}.{os.getpid()}.{threading.get_ident()}"
    )
    # The mode is the one of the creation, and set again for a file that a
    # crash left: the text is written after it.
    descriptor = os.open(
        temporary_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
    )
    try:
        os.chmod(temporary_path, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf8") as file_:
            file_.write("".join(lines))
    except BaseException:
        os.unlink(temporary_path)
        raise
    os.replace(temporary_path, configuration_path)


def _read_global_configuration(folder: Path) -> List[Tuple[str, str]]:
    try:
        result = subprocess.run(
            ["git", "config", "--global", "--list", "-z"],
            cwd=folder,
            env=get_system_program_environment(),
            capture_output=True,
            check=False,
            timeout=30,
            creationflags=get_hidden_window_flags(),
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    return _parse_configuration(result.stdout)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "")


def _quote(value: str) -> str:
    return (
        '"'
        + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        + '"'
    )


def _escape_exclude_pattern(relative: str) -> str:
    """
    The name of a file as a pattern of ".gitignore" that matches this name
    only: the backslash, "[", "*" and "?" are escaped, the spaces at the end
    are kept by an escape, and a line break, which a line cannot hold, becomes
    the wildcard "?". The "#" and "!" of a name are no special case: the
    pattern starts with "/".
    """
    escaped = re.sub(r"([\\\[*?])", r"\\\1", relative)
    escaped = escaped.replace("\n", "?").replace("\r", "?")
    stripped = escaped.rstrip(" ")
    return stripped + "\\ " * (len(escaped) - len(stripped))


def _unescape_exclude_pattern(pattern: str) -> Optional[str]:
    """
    The path that a line of the block of the application stands for, the
    reverse of _escape_exclude_pattern. None for a line that is not a path
    that this application wrote (no leading "/", a wildcard that stands for a
    line break).
    """
    if not pattern.startswith("/"):
        return None
    characters: List[str] = []
    index = 1
    while index < len(pattern):
        character = pattern[index]
        if character == "\\":
            index += 1
            if index >= len(pattern):
                return None
            character = pattern[index]
        elif character in "*?[":
            return None
        characters.append(character)
        index += 1
    return "".join(characters)


def _read_exclude_lines(exclude_path: str) -> List[str]:
    if not os.path.isfile(exclude_path):
        return []
    with file_open_read_utf8(exclude_path) as file_:
        text = file_.read()
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


def _write_exclude_lines(exclude_path: str, lines: List[str]) -> None:
    os.makedirs(os.path.dirname(exclude_path), exist_ok=True)
    text = "".join(f"{line_}\n" for line_ in lines)
    with open(exclude_path, "w", encoding="utf-8", newline="\n") as file_:
        file_.write(text)


def _find_exclude_block(lines: List[str]) -> Optional[Tuple[int, int]]:
    """The indexes of the first and the last line of the block, if any."""
    if EXCLUDE_BLOCK_BEGIN not in lines:
        return None
    begin = lines.index(EXCLUDE_BLOCK_BEGIN)
    if EXCLUDE_BLOCK_END not in lines[begin + 1 :]:
        return None
    return begin, lines.index(EXCLUDE_BLOCK_END, begin + 1)
