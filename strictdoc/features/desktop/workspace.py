"""
The folder of a project on the disk: the check of a chosen folder and the
clone of the project into it.

@relation(SDOC-SRS-1230, scope=file)
"""

import os
import re
import shutil
import stat
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from urllib.parse import urlsplit

# GitPython refuses to be imported when the git program is missing, which
# would stop the whole application. With "quiet" only the use of Git fails.
os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")

from git import Repo  # noqa: E402
from git.exc import GitError, InvalidGitRepositoryError  # noqa: E402

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
    host = (parts.hostname or "").lower()
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
            "The folder %(folder)s holds the clone of another repository: "
            "%(url)s."
        )
        % {"folder": full_path, "url": normalize_clone_url(origin_url)}
    )


def clone_project(clone_url: str, folder: str) -> None:
    """
    Clone the repository into an empty folder.

    The function checks the folder itself, just before the clone: a folder
    with anything in it is left untouched and raises a WorkspaceError. A
    failed clone empties the folder again, so that the user can retry with the
    same folder, and raises a WorkspaceError with a message to show. Git never
    asks for a password: without a credential, the clone fails.
    """
    if clone_url.strip().startswith("-"):
        raise WorkspaceError(_get_clone_failed_message("invalid URL"))
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
        _clone(clone_url, folder)
    except (GitError, OSError) as exception_:
        # Only a folder that was empty before is emptied. A missing folder is
        # created by Git, which removes it when the clone fails.
        if was_folder_present:
            _empty_folder(folder)
        raise WorkspaceError(
            _get_clone_failed_message(_get_error_summary(exception_))
        ) from exception_


def pull_project(
    folder: str, *, timeout_seconds: float = PULL_TIMEOUT_SECONDS
) -> bool:
    """
    Bring the project up to date from its remote, in the way of a
    fast-forward only: "git pull --ff-only".

    It returns True when the update changed files and False when there was
    nothing to change. It raises WorkspaceError when Git cannot do it: no
    remote, no network, a branch that has its own commits, a change that
    would be overwritten. In all these cases Git leaves the files as they
    were. Git never asks for a password, and it is stopped after the timeout.
    """
    try:
        repo = Repo(folder)
    except (GitError, OSError) as exception_:
        raise WorkspaceError(_get_error_summary(exception_)) from exception_
    try:
        head_before = repo.head.commit.hexsha if repo.head.is_valid() else None
        with repo.git.custom_environment(GIT_TERMINAL_PROMPT="0"):
            repo.git.pull(
                "--ff-only",
                kill_after_timeout=timeout_seconds,
            )
        head_after = repo.head.commit.hexsha if repo.head.is_valid() else None
        return head_before != head_after
    except (GitError, OSError, ValueError) as exception_:
        raise WorkspaceError(_get_error_summary(exception_)) from exception_
    finally:
        repo.close()


def _clone(clone_url: str, folder: str) -> None:
    repo = Repo.clone_from(clone_url, folder, env={"GIT_TERMINAL_PROMPT": "0"})
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
        stderr if isinstance(stderr, str) and stderr.strip() else str(exception)
    )
    lines = [line_.strip() for line_ in text.splitlines() if line_.strip()]
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
