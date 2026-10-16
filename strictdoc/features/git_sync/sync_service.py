"""
Pull then push of the repository of a project, and the merge of the documents
that both sides changed.

The state of a merge in progress is Git's own (MERGE_HEAD and the unmerged
files of the index): the server keeps nothing in memory, so a restart loses
nothing. The documents (.sdoc) that Git cannot merge by lines are merged again
node by node (merge3.py); what both sides changed is left to the person, in
the view of the conflicts.
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from strictdoc.backend.sdoc.reader import SDReader
from strictdoc.features.git_config.config import GitConfig
from strictdoc.features.git_config.git_service import (
    Author,
    GitService,
    GitServiceError,
)
from strictdoc.features.git_config.gitlab_service import GitLabServiceError
from strictdoc.features.git_config.setup import ensure_remote_repository
from strictdoc.features.git_sync.merge3 import (
    Region,
    assemble,
    conflict_indexes,
    merge3,
)
from strictdoc.helpers.exception import StrictDocException

# The states of a synchronization.
UP_TO_DATE = "up_to_date"
PULLED = "pulled"
MERGED = "merged"
CONFLICTS = "conflicts"
NO_REMOTE = "no_remote"
ERROR = "error"


@dataclass
class SyncResult:
    status: str
    message: str = ""
    # The documents that wait for a person (relative paths).
    conflicts: List[str] = field(default_factory=list)
    pulled: int = 0
    pushed: bool = False


@dataclass
class ConflictFile:
    path: str
    regions: List[Region]
    local_text: str = ""
    server_text: str = ""

    @property
    def conflict_indexes(self) -> List[int]:
        return conflict_indexes(self.regions)

    @property
    def regions_local_text(self) -> str:
        return "".join(region_.local_text for region_ in self.regions)


def _duplicate_identity(document: Any) -> str:
    """A MID or a UID that two nodes of the document have, or ""."""
    seen: Dict[str, str] = {}
    stack = list(document.section_contents)
    while stack:
        node = stack.pop(0)
        stack = list(getattr(node, "section_contents", []) or []) + stack
        for name_, value_ in (
            ("MID", getattr(node, "reserved_mid", None)),
            ("UID", getattr(node, "reserved_uid", None)),
        ):
            if value_ is None:
                continue
            key = f"{name_} {value_}"
            if key in seen:
                return key
            seen[key] = key
    return ""


class SyncService:
    def __init__(
        self,
        service: GitService,
        git_config: GitConfig,
        author: Author,
    ) -> None:
        self.service = service
        self.git_config = git_config
        self.author = author
        self.root = service.project_root

    # ---- Pull and push

    def sync(self) -> SyncResult:
        if self.service.merge_in_progress(self.root):
            return SyncResult(
                CONFLICTS,
                "A synchronization is waiting for the conflicts to be solved.",
                conflicts=self.conflict_paths(),
            )
        try:
            return self._sync()
        except (GitServiceError, GitLabServiceError) as error:
            return SyncResult(ERROR, str(error))

    def _sync(self) -> SyncResult:
        service = self.service
        if not service.has_remote(self.root):
            return SyncResult(
                NO_REMOTE, "The repository has no remote (origin)."
            )
        problem = ensure_remote_repository(service, self.root, self.git_config)
        if problem:
            return SyncResult(ERROR, problem)
        if service.is_dirty(self.root):
            service.commit_paths(
                [self.root],
                "chore: save the changes before the synchronization",
                self.author,
            )
        branch = service.current_branch(self.root)
        service.fetch(self.root)
        result = SyncResult(UP_TO_DATE)
        if service.remote_branch_exists(self.root, branch):
            behind, ahead = service.ahead_behind(self.root, branch)
            if behind > 0 and ahead == 0:
                service.fast_forward(self.root, branch)
                result = SyncResult(PULLED, pulled=behind)
            elif behind > 0:
                clean = service.start_merge(self.root, branch, self.author)
                if not clean:
                    remaining = self.auto_resolve()
                    if remaining:
                        return SyncResult(
                            CONFLICTS,
                            "Both sides changed the same nodes.",
                            conflicts=remaining,
                            pulled=behind,
                        )
                service.commit_merge(
                    self.root,
                    f"Merge origin/{branch}",
                    self.author,
                )
                result = SyncResult(MERGED, pulled=behind)
        self._push(result)
        return result

    def _push(self, result: SyncResult) -> None:
        try:
            self.service.push(self.root)
        except GitServiceError as error:
            result.status = ERROR
            result.message = str(error)
            return
        note = self.service.push_tags(self.root)
        if note:
            result.message = f"The tags were not pushed: {note}"
        result.pushed = True

    # ---- Conflicts

    def auto_resolve(self) -> List[str]:
        """
        Merges again node by node the documents that Git stopped on. Returns
        the documents that still have conflicts. A conflict that is not in a
        document cannot be solved here: the merge is abandoned.
        """
        remaining: List[str] = []
        for relative_ in self.service.unmerged_paths(self.root):
            loaded = self._load(relative_)
            if loaded is None:
                self.service.abort_merge(self.root)
                raise GitServiceError(
                    f"{relative_} cannot be merged here (it is not a "
                    "document, or one side removed it): resolve it with "
                    "Git. The synchronization was abandoned."
                )
            if loaded.conflict_indexes:
                remaining.append(relative_)
                # Git wrote conflict markers in the file; the server reads
                # this file, so it gets the local text back until the
                # conflicts are solved (the index still has them unmerged).
                self.service.write_working_file(
                    self.root, relative_, loaded.regions_local_text
                )
            else:
                self.service.write_resolved(
                    self.root, relative_, assemble(loaded.regions, {})
                )
        return remaining

    def _load(self, relative: str) -> Optional[ConflictFile]:
        if not relative.endswith(".sdoc"):
            return None
        local = self.service.stage_text(self.root, relative, 2)
        server = self.service.stage_text(self.root, relative, 3)
        if local is None or server is None:
            return None
        base = self.service.stage_text(self.root, relative, 1) or ""
        return ConflictFile(
            relative, merge3(base, local, server), local, server
        )

    def conflict_paths(self) -> List[str]:
        return self.service.unmerged_paths(self.root)

    def conflict_file(self, relative: str) -> ConflictFile:
        if relative not in self.conflict_paths():
            raise StrictDocException(f"{relative} has no conflict.")
        loaded = self._load(relative)
        if loaded is None:
            raise StrictDocException(f"{relative} cannot be merged here.")
        return loaded

    def resolve(self, relative: str, chosen: Dict[int, str]) -> None:
        """
        Writes a document with the text chosen for each of its conflicts (by
        region index) and marks it resolved. Nothing is written when a choice
        is missing or when the result does not read back as a document.
        """
        loaded = self.conflict_file(relative)
        missing = [i_ for i_ in loaded.conflict_indexes if i_ not in chosen]
        if missing:
            raise StrictDocException(
                f"{relative}: {len(missing)} conflict(s) without a choice."
            )
        merged = assemble(loaded.regions, chosen)
        try:
            document = SDReader.read(
                merged, file_path=os.path.join(self.root, relative)
            )
        except StrictDocException as error:
            raise StrictDocException(
                f"{relative}: the result is not a valid document: {error}"
            ) from error
        duplicate = _duplicate_identity(document)
        if duplicate:
            raise StrictDocException(
                f"{relative}: {duplicate} would be twice in the document "
                "(keeping both sides of a node that both changed): keep one "
                "side, or edit the result."
            )
        self.service.write_resolved(self.root, relative, merged)

    def complete(self) -> SyncResult:
        """
        When every document is resolved: commits the merge and pushes.
        Otherwise the documents that remain.
        """
        remaining = self.conflict_paths()
        if remaining:
            return SyncResult(CONFLICTS, conflicts=remaining)
        branch = self.service.current_branch(self.root)
        self.service.commit_merge(
            self.root, f"Merge origin/{branch}", self.author
        )
        result = SyncResult(MERGED)
        self._push(result)
        return result

    def finish(self, texts: Dict[str, Dict[int, str]]) -> SyncResult:
        """Resolves the documents given, then completes the merge."""
        for relative_ in self.conflict_paths():
            self.resolve(relative_, texts.get(relative_, {}))
        return self.complete()

    def abort(self) -> None:
        self.service.abort_merge(self.root)
