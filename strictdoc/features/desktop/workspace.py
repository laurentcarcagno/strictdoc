"""
The folder of a project on the disk: the check of a chosen folder and the
clone of the project into it.

The clone and the update run Git with the environment of git_access.py: the
token of the signed-in user for the GitLab of the session, no other credential
and no question to the user.

@relation(SDOC-SRS-1230, scope=file)
@relation(SDOC-SRS-1239, scope=file)
@relation(SDOC-SRS-1241, scope=file)
@relation(SDOC-SRS-1246, scope=file)
"""

import os
import re
import shutil
import stat
import sys
import threading
from contextlib import nullcontext
from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional
from urllib.parse import urlsplit

# GitPython refuses to be imported when the git program is missing, which
# would stop the whole application. With "quiet" only the use of Git fails.
os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")

from git import Repo  # noqa: E402
from git.exc import (  # noqa: E402
    GitCommandError,
    GitError,
    InvalidGitRepositoryError,
)

from strictdoc.features.desktop.git_access import (  # noqa: E402
    GitAccess,
    UnsafeRepositoryError,
    check_repository_for_network,
    has_credentials_in_url,
)
from strictdoc.features.desktop.project_gate import ProjectGate  # noqa: E402
from strictdoc.features.desktop.project_runtime import (  # noqa: E402
    Inhibition,
    ProjectRuntime,
)
from strictdoc.features.i18n.i18n import gettext  # noqa: E402

REMOTE_NAME = "origin"

# A path of more than about 260 characters fails on Windows, and the project
# adds its own sub-folders to the folder that the user chooses.
WINDOWS_MAX_FOLDER_PATH_LENGTH = 200

# "git pull" is stopped after this time, for example on a network that drops.
PULL_TIMEOUT_SECONDS = 30.0

_SCP_LIKE_URL = re.compile(r"^[^@/:]+@([^:/]+):(?!//)(.+)$")


class FolderStatus(Enum):
    # An empty folder: the project is cloned into it.
    EMPTY = "empty"
    # A clone of this project: the application uses it as it is.
    SAME_REPOSITORY = "same_repository"
    REFUSED = "refused"


@dataclass(frozen=True)
class FolderCheck:
    status: FolderStatus
    # The reason of a refusal, for the user.
    reason: str = ""


class WorkspaceError(Exception):
    """A failure that the user can read, for example a failed clone."""


class UpdateDeferredError(WorkspaceError):
    """
    The update has things to bring and a page has an editor open: the files
    of the working copy do not change under the typing. The update applies when
    the last editor is closed.
    """


def normalize_clone_url(url: str) -> str:
    """
    A form of a repository URL that two spellings of one repository share: the
    scheme and the host in lower case, no user name or password, no final
    slash and no final ".git". The address "git@host:group/project.git" of
    SSH is the same as "ssh://host/group/project".
    """
    text = url.strip()
    scp_match = _SCP_LIKE_URL.match(text)
    if scp_match is not None:
        text = f"ssh://{scp_match.group(1)}/{scp_match.group(2)}"
    elif text.startswith("/"):
        text = f"file://{text}"
    parts = urlsplit(text)
    host = parts.hostname.lower() if parts.hostname is not None else ""
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    path = parts.path.rstrip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")].rstrip("/")
    return f"{parts.scheme.lower()}://{host}{path}"


def check_folder(
    folder: str,
    clone_url: str,
    *,
    max_path_length: Optional[int] = None,
) -> FolderCheck:
    """
    Tell what the application does with a folder that the user chose for the
    project whose repository has this URL.

    On Windows, a folder whose path is longer than the limit is refused. The
    argument sets another limit (the tests), or none.
    """
    if max_path_length is None and sys.platform == "win32":
        max_path_length = WINDOWS_MAX_FOLDER_PATH_LENGTH
    full_path = os.path.abspath(folder)
    if max_path_length is not None and len(full_path) > max_path_length:
        return _refuse(
            gettext(
                "The path of the folder is too long (%(length)s characters, "
                "the limit is %(limit)s). Choose a shorter path."
            )
            % {"length": len(full_path), "limit": max_path_length}
        )
    if not os.path.exists(full_path):
        return _refuse(
            gettext("The folder %(folder)s does not exist.")
            % {"folder": full_path}
        )
    if not os.path.isdir(full_path):
        return _refuse(
            gettext("%(folder)s is not a folder.") % {"folder": full_path}
        )
    if len(os.listdir(full_path)) == 0:
        return FolderCheck(FolderStatus.EMPTY)

    origin_url = _read_origin_url(full_path)
    if origin_url is not None and has_credentials_in_url(origin_url):
        # The reason does not show the address: it holds a secret.
        return _refuse(
            gettext(
                "The folder %(folder)s holds a clone whose address has a "
                "user name or a password. Choose another folder."
            )
            % {"folder": full_path}
        )
    if origin_url is None:
        return _refuse(
            gettext(
                "The folder %(folder)s is not empty and does not hold this "
                "project. Choose an empty folder."
            )
            % {"folder": full_path}
        )
    if normalize_clone_url(origin_url) == normalize_clone_url(clone_url):
        return FolderCheck(FolderStatus.SAME_REPOSITORY)
    return _refuse(
        gettext(
            "The folder %(folder)s holds the clone of another project: %(url)s."
        )
        % {"folder": full_path, "url": normalize_clone_url(origin_url)}
    )


def clone_project(
    clone_url: str, folder: str, *, git_access: Optional[GitAccess] = None
) -> None:
    """
    Clone the repository into an empty folder.

    The function checks the folder itself, just before the clone: a folder
    with anything in it is left untouched and raises a WorkspaceError. A
    failed clone empties the folder again, so that the user can retry with the
    same folder, and raises a WorkspaceError with a message to show. Git never
    asks for a password and never uses a credential of the computer: it has
    the token of the signed-in user, for the GitLab of the session only, or
    none. Without a credential, the clone of a private project fails.
    """
    if clone_url.strip().startswith("-"):
        raise WorkspaceError(_get_clone_failed_message("invalid URL"))
    if has_credentials_in_url(clone_url):
        # Nothing but the token of the session goes to a server.
        raise WorkspaceError(
            _get_clone_failed_message(
                gettext(
                    "The address of the project holds a user name or a "
                    "password."
                )
            )
        )
    full_path = os.path.abspath(folder)
    if os.path.lexists(full_path) and (
        not os.path.isdir(full_path) or len(os.listdir(full_path)) > 0
    ):
        raise WorkspaceError(
            gettext(
                "The folder %(folder)s is not empty and does not hold this "
                "project. Choose an empty folder."
            )
            % {"folder": full_path}
        )
    was_folder_present = os.path.isdir(full_path)
    try:
        _clone(
            clone_url,
            folder,
            git_access if git_access is not None else GitAccess(),
        )
    except (GitError, OSError) as exception_:
        # Only a folder that was empty before is emptied. A missing folder is
        # created by Git, which removes it when the clone fails.
        if was_folder_present:
            _empty_folder(folder)
        raise WorkspaceError(
            _get_clone_failed_message(_get_error_summary(exception_))
        ) from exception_


def fetch_project(
    folder: str,
    *,
    timeout_seconds: float = PULL_TIMEOUT_SECONDS,
    git_access: Optional[GitAccess] = None,
) -> None:
    """
    Bring what the server has into the repository, and change no file of the
    working copy. It takes no exclusion: the network is slow, and the user
    saves meanwhile. Git never asks for a password, it has the token of the
    signed-in user for the server of the session only (or no credential), and
    it is stopped after the timeout, on every platform. It raises
    WorkspaceError when it cannot be done: no server, no network.
    """
    try:
        repo = Repo(folder)
    except (GitError, OSError) as exception_:
        raise WorkspaceError(_get_error_summary(exception_)) from exception_
    is_timed_out = threading.Event()
    try:
        access = git_access if git_access is not None else GitAccess()
        environment = access.build_environment()
        check_repository_for_network(folder, environment)
        repo.git.update_environment(**environment)
        _fetch(repo, timeout_seconds, is_timed_out)
    except UnsafeRepositoryError as exception_:
        raise WorkspaceError(str(exception_)) from exception_
    except (GitError, OSError, ValueError) as exception_:
        if is_timed_out.is_set():
            raise WorkspaceError(
                f"The update stopped after {int(timeout_seconds)} seconds."
            ) from exception_
        raise WorkspaceError(_get_error_summary(exception_)) from exception_
    finally:
        repo.close()


def pull_project(
    folder: str,
    *,
    timeout_seconds: float = PULL_TIMEOUT_SECONDS,
    git_access: Optional[GitAccess] = None,
    gate: Optional[ProjectGate] = None,
    runtime: Optional[ProjectRuntime] = None,
) -> bool:
    """
    Bring the project up to date from its remote, in the way of a
    fast-forward only: a fetch, then a merge that is a fast-forward or
    nothing.

    It returns True when the update changed files and False when there was
    nothing to change. It raises WorkspaceError when Git cannot do it: no
    remote, no network, a branch that has its own commits, a change that
    would be overwritten. In all these cases Git leaves the files as they
    were. Git never asks for a password, it has the token of the signed-in
    user for the GitLab of the session only (or no credential), and it is
    stopped after the timeout, on every platform.

    With the gate of the project, the fetch runs outside of it (the network is
    slow) and the change of the files holds it: a save and the update never
    cross.

    With the runtime of the project, the update does not change the files
    while a page has an editor open: the fetch is done, and the function
    raises UpdateDeferredError (the caller applies the update when the editors
    are closed). When the files change, the server of the project is told in
    the same time, with the gate held: the index is built again before any
    save passes.
    """
    try:
        repo = Repo(folder)
    except (GitError, OSError) as exception_:
        raise WorkspaceError(_get_error_summary(exception_)) from exception_
    is_timed_out = threading.Event()
    try:
        access = git_access if git_access is not None else GitAccess()
        environment = access.build_environment()
        check_repository_for_network(folder, environment)
        repo.git.update_environment(**environment)
        _fetch(repo, timeout_seconds, is_timed_out)
        with gate.hold() if gate is not None else nullcontext():
            head_before = (
                repo.head.commit.hexsha if repo.head.is_valid() else None
            )
            # The merge is local: it needs no token.
            repo.git.update_environment(
                **access.build_environment(is_network=False)
            )
            if runtime is not None and runtime.leases.is_editing():
                if _has_update_to_apply(repo):
                    raise UpdateDeferredError(
                        "The update waits for the end of the typing."
                    )
                return False
            # The watcher is told before Git writes the files: it looks at a
            # change 0.3 seconds after it, and a slow Git must not be seen
            # first.
            incoming = (
                _list_changed_paths(repo, "HEAD", "@{upstream}")
                if runtime is not None and head_before is not None
                else []
            )
            inhibition = (
                runtime.inhibit_paths(incoming)
                if runtime is not None
                else Inhibition()
            )
            try:
                repo.git.merge("--ff-only", "@{upstream}")
            except BaseException:
                if runtime is not None:
                    runtime.release_inhibition(inhibition)
                raise
            head_after = (
                repo.head.commit.hexsha if repo.head.is_valid() else None
            )
            if runtime is not None and head_before != head_after:
                runtime.apply_update(
                    _list_changed_paths(repo, head_before, head_after),
                    inhibition=inhibition,
                )
            elif runtime is not None:
                runtime.release_inhibition(inhibition)
        return head_before != head_after
    except UpdateDeferredError:
        raise
    except UnsafeRepositoryError as exception_:
        raise WorkspaceError(str(exception_)) from exception_
    except (GitError, OSError, ValueError) as exception_:
        if is_timed_out.is_set():
            # Only the log shows it: the screen shows nothing of an update.
            raise WorkspaceError(
                f"The update stopped after {int(timeout_seconds)} seconds."
            ) from exception_
        raise WorkspaceError(_get_error_summary(exception_)) from exception_
    finally:
        repo.close()


def _has_update_to_apply(repo: Repo) -> bool:
    """True when the branch that is followed has commits that this one lacks."""
    count = repo.git.rev_list("--count", "HEAD..@{upstream}")
    return int(count) > 0


def _list_changed_paths(
    repo: Repo, head_before: Optional[str], head_after: Optional[str]
) -> List[str]:
    """The files that the update changed, as absolute paths."""
    if head_before is None or head_after is None:
        return []
    # "-z": Git writes the names as they are, separated by a NUL. Without it,
    # a name with an accent is quoted, with its bytes in octal.
    names = str(repo.git.diff("--name-only", "-z", head_before, head_after))
    root = str(repo.working_tree_dir)
    return [
        os.path.join(root, name_) for name_ in names.split("\0") if name_ != ""
    ]


def _fetch(
    repo: Repo, timeout_seconds: float, is_timed_out: threading.Event
) -> None:
    process = repo.git.fetch(as_process=True)
    timer = threading.Timer(
        timeout_seconds, _stop_process, args=(process, is_timed_out)
    )
    timer.daemon = True
    timer.start()
    try:
        # Reads both streams while the command runs: a long list of the
        # changed files would otherwise fill the pipe and stop Git.
        _, errors = process.communicate()
    finally:
        timer.cancel()
    if process.proc.returncode != 0:
        raise GitCommandError(["git", "fetch"], process.proc.returncode, errors)


def _stop_process(process: Any, is_timed_out: threading.Event) -> None:
    is_timed_out.set()
    try:
        process.terminate()
    except OSError:
        pass


def _clone(clone_url: str, folder: str, git_access: GitAccess) -> None:
    repo = Repo.clone_from(
        clone_url, folder, env=git_access.build_environment()
    )
    repo.close()


def _refuse(reason: str) -> FolderCheck:
    return FolderCheck(FolderStatus.REFUSED, reason)


def _read_origin_url(folder: str) -> Optional[str]:
    """The URL of the remote "origin" of the Git repository of the folder."""
    try:
        repo = Repo(folder)
    except (InvalidGitRepositoryError, GitError, OSError):
        return None
    try:
        for remote_ in repo.remotes:
            if remote_.name == REMOTE_NAME:
                url: str = remote_.url
                return url
        return None
    except (GitError, OSError, ValueError):
        return None
    finally:
        repo.close()


def _get_clone_failed_message(summary: str) -> str:
    return gettext("The clone of the project failed: %(reason)s") % {
        "reason": summary
    }


def _get_error_summary(exception: BaseException) -> str:
    """
    The line of the error that Git printed ("fatal: repository ... does not
    exist"), or else the first line of the error.
    """
    stderr = getattr(exception, "stderr", None)
    text = (
        stderr
        if isinstance(stderr, str) and stderr.strip() != ""
        else str(exception)
    )
    lines = [
        line_.strip() for line_ in text.splitlines() if line_.strip() != ""
    ]
    fatal_lines = [
        line_
        for line_ in lines
        if line_.lower().startswith(("fatal:", "error:"))
    ]
    if len(fatal_lines) > 0:
        return fatal_lines[-1]
    return lines[0] if len(lines) > 0 else type(exception).__name__


def _empty_folder(folder: str) -> None:
    """Remove what is inside the folder, not the folder itself."""
    if not os.path.isdir(folder):
        return
    for name_ in os.listdir(folder):
        path = os.path.join(folder, name_)
        if os.path.isdir(path) and not os.path.islink(path):
            _make_tree_writable(path)
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                os.unlink(path)
            except OSError:
                pass


def _make_tree_writable(path: str) -> None:
    # The files of the objects of Git are read-only, which Windows refuses to
    # remove.
    for root_, directories_, files_ in os.walk(path):
        for directory_ in directories_:
            _try_chmod(os.path.join(root_, directory_), stat.S_IRWXU)
        for file_ in files_:
            _try_chmod(os.path.join(root_, file_), stat.S_IREAD | stat.S_IWRITE)


def _try_chmod(path: str, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass
