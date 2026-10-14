"""
The save interceptor: commits what the server has just written.

Called by the project context after a document is written or an asset is
uploaded. A failure never loses a save: it is kept in ``last_error`` (shown in
the interface) and logged. Assets uploaded while editing wait in
``pending_paths`` and join the next commit, so an image does not make a commit
of its own; ``flush`` commits them on request.
"""

import logging
import os
import shutil
from typing import Callable, List

from strictdoc.features.git_config.commit_message import (
    asset_message,
    document_message,
)
from strictdoc.features.git_config.git_service import (
    Author,
    GitService,
    GitServiceError,
)

logger = logging.getLogger(__name__)

LFS_PATTERN = "_assets/** filter=lfs diff=lfs merge=lfs -text"


class GitCommitter:
    def __init__(
        self,
        service: GitService,
        author_provider: Callable[[], Author],
        use_lfs: bool = False,
        asset_warning_bytes: int = 0,
    ) -> None:
        self.service = service
        self.author_provider = author_provider
        self.use_lfs = use_lfs
        self.asset_warning_bytes = asset_warning_bytes
        self.pending_paths: List[str] = []
        self.last_error: str = ""
        self.warnings: List[str] = []

    def on_asset_written(self, path: str) -> None:
        if path not in self.pending_paths:
            self.pending_paths.append(path)
        try:
            self._check_asset(path)
        except (GitServiceError, OSError) as error:
            self._fail(error)

    def _check_asset(self, path: str) -> None:
        size = os.path.getsize(path)
        if 0 < self.asset_warning_bytes < size:
            self.warnings.append(
                f"{os.path.basename(path)} is {size // 1024} KB: large files "
                "make the repository heavy."
            )
        if self.use_lfs:
            root = self.service.repository_root(path)
            attributes = os.path.join(root, ".gitattributes")
            existing = ""
            if os.path.exists(attributes):
                with open(attributes, encoding="utf8") as file:
                    existing = file.read()
            if LFS_PATTERN not in existing:
                with open(attributes, "a", encoding="utf8") as file:
                    if existing != "" and not existing.endswith("\n"):
                        file.write("\n")
                    file.write(LFS_PATTERN + "\n")
            if attributes not in self.pending_paths:
                self.pending_paths.append(attributes)

    def on_node_deleted(self, assets_dir: str, names: List[str]) -> int:
        """
        Remove the asset folders of a deleted node. The removal is committed
        with the next save (a deleted file is recoverable from Git). Returns
        the number of folders removed.
        """
        base = os.path.realpath(assets_dir)
        removed = 0
        for name in names:
            folder = os.path.realpath(os.path.join(base, name))
            if name == "" or os.path.dirname(folder) != base:
                continue
            if not os.path.isdir(folder):
                continue
            shutil.rmtree(folder)
            removed += 1
            if folder not in self.pending_paths:
                self.pending_paths.append(folder)
        return removed

    def on_document_written(self, path: str) -> None:
        try:
            diff = self.service.diff_of(path)
            with open(path, encoding="utf8") as file:
                content = file.read()
            message = document_message(path, diff, content)
            self._commit([path, *self.pending_paths], message)
        except (GitServiceError, OSError) as error:
            self._fail(error)

    def flush(self) -> bool:
        """Commit the pending assets. True if a commit was made."""
        if len(self.pending_paths) == 0:
            return False
        names = [os.path.basename(path) for path in self.pending_paths]
        try:
            return self._commit(list(self.pending_paths), asset_message(names))
        except GitServiceError as error:
            self._fail(error)
            return False

    def _commit(self, paths: List[str], message: str) -> bool:
        committed = self.service.commit_paths(
            paths, message, self.author_provider()
        )
        self.pending_paths = []
        self.last_error = ""
        return committed

    def _fail(self, error: Exception) -> None:
        self.last_error = str(error)
        logger.warning("git: %s", error)
