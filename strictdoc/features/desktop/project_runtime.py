"""
What the pages, the update of the project and the server of the project share
for one project: the leases of the editors that are open, the revision of the
files on the disk, and the two functions that tell the server that files
changed.

A page that has an editor or a form open takes a lease (a short one, renewed
by the page). While a lease lives, the application does not change the files of
the working copy: the update that the server offered waits, and applies when
the last editor is closed. The lease cannot be the only defence: it ends if the
computer sleeps, if a hidden window slows its timers, if the page freezes. So
every change of the files from outside the saves of the user also raises the
revision, and a form that was opened on an older revision is not saved (see
project_gate.py): its text stays on the screen.

@relation(SDOC-SRS-1246, scope=file)
"""

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# The time that a page has to renew its lease. The page renews every 5
# seconds, and again when its window is shown. The lease is longer than the
# wait of a hidden window: Chromium wakes the timers of a window that is
# hidden once a minute, and the user who goes to another application with an
# editor open must still find it open. The page ends the lease itself when it
# closes its last editor. The variable is for the tests of the application
# only.
LEASE_SECONDS = 90.0
LEASE_SECONDS_VARIABLE = "STRICTDOC_DESKTOP_LEASE_SECONDS"


def get_lease_seconds() -> float:
    try:
        seconds = float(os.environ[LEASE_SECONDS_VARIABLE])
    except (KeyError, ValueError):
        return LEASE_SECONDS
    return seconds if seconds > 0 else LEASE_SECONDS


class EditingLeases:
    """
    The pages of a project that have an editor open. A page is known by an
    identifier that it makes. A lease ends when the page releases it or when
    its time runs out. The functions of the listeners are called, with no
    argument and without a lock, when the last lease ends.
    """

    def __init__(
        self,
        *,
        ttl_seconds: Optional[float] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds: float = (
            ttl_seconds if ttl_seconds is not None else get_lease_seconds()
        )
        self._clock: Callable[[], float] = clock
        self._lock: threading.Lock = threading.Lock()
        self._expiries: Dict[str, float] = {}
        self._listeners: List[Callable[[], None]] = []
        self._timer: Optional[threading.Timer] = None

    def renew(self, page_id: str) -> None:
        """The page has an editor open: its lease lasts from now."""
        with self._lock:
            self._expiries[page_id] = self._clock() + self._ttl_seconds
            self._schedule_locked()

    def release(self, page_id: str) -> None:
        """The page closed its last editor."""
        with self._lock:
            was_editing = len(self._expiries) > 0
            self._expiries.pop(page_id, None)
            is_over = was_editing and len(self._expiries) == 0
            self._schedule_locked()
        if is_over:
            self._notify()

    def is_editing(self) -> bool:
        """True while at least one page has a lease that did not end."""
        with self._lock:
            was_editing = len(self._expiries) > 0
            self._remove_expired_locked()
            is_over = was_editing and len(self._expiries) == 0
            is_editing = len(self._expiries) > 0
        if is_over:
            self._notify()
        return is_editing

    def get_page_count(self) -> int:
        with self._lock:
            self._remove_expired_locked()
            return len(self._expiries)

    def add_listener(self, listener: Callable[[], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def close(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def _remove_expired_locked(self) -> None:
        now = self._clock()
        for page_id_ in [
            page_id_
            for page_id_, expiry_ in self._expiries.items()
            if expiry_ <= now
        ]:
            del self._expiries[page_id_]

    def _schedule_locked(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if len(self._expiries) == 0:
            return
        delay = max(0.0, min(self._expiries.values()) - self._clock())
        # A little after the end, so that the lease is over when it looks.
        timer = threading.Timer(delay + 0.01, self._on_timer)
        timer.daemon = True
        timer.start()
        self._timer = timer

    def _on_timer(self) -> None:
        # is_editing() removes what ended, tells the listeners, and the next
        # end is scheduled again by the next renewal or release.
        if self.is_editing():
            with self._lock:
                self._schedule_locked()

    def _notify(self) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener_ in listeners:
            try:
                listener_()
            except Exception:
                logger.exception("The listener of the editing leases failed.")


@dataclass
class Inhibition:
    """
    The files that the watcher of the files was told to leave alone, before
    they change. "owned" holds the ones that nobody had inhibited yet: only
    these are taken back, because an inhibition that was there already waits
    for the change of somebody else (a save).
    """

    paths: List[str] = field(default_factory=list)
    owned: List[str] = field(default_factory=list)

    def add(self, other: "Inhibition") -> None:
        self.paths.extend(other.paths)
        self.owned.extend(other.owned)


class ProjectRuntime:
    """The state of one project that its pages and its updates share."""

    def __init__(self) -> None:
        self.leases: EditingLeases = EditingLeases()
        self._revision: int = 0
        self._lock: threading.Lock = threading.Lock()
        # Set by the server of the project while it runs. Both are called
        # with the gate of the project held.
        self.rebuild_and_notify: Optional[Callable[[], None]] = None
        # Returns False when the file was inhibited already.
        self.inhibit_change: Optional[Callable[[str], Optional[bool]]] = None
        # Takes back an inhibition that no change used.
        self.release_change: Optional[Callable[[str], None]] = None
        # True while an update waits for the end of the typing.
        self.is_update_waiting: bool = False
        # What the last synchronization has to tell the user, that no state
        # of the sending says: "" or the name of a state (see project_sync.py)
        # with its text. It lasts until the next synchronization that brings
        # something.
        self.sync_notice_state: str = ""
        self.sync_notice_text: str = ""
        # The state of the files that the last synchronization could not
        # combine, to leave them alone until one of the two sides moves:
        # the heads of the project and of the server.
        self.blocked_heads: Optional[tuple[str, str]] = None
        # The files change (the generation rises) before the index is built
        # again from them, and the index is the one of the disk only when a
        # build that started after the last change succeeded.
        self._change_generation: int = 0
        self._built_generation: int = 0

    @property
    def revision(self) -> int:
        """The number of the state of the files, raised by each change."""
        with self._lock:
            return self._revision

    @property
    def is_index_outdated(self) -> bool:
        """
        True while the index of the server is not the one of the files: the
        files changed and the index was not built again from them (the build
        failed, or it did not end). A save then writes the old text over the
        files.
        """
        with self._lock:
            return self._built_generation != self._change_generation

    def bump_revision(self) -> int:
        with self._lock:
            self._revision += 1
            return self._revision

    def mark_files_changed(self) -> None:
        """The files changed: the index is outdated until it is built again."""
        with self._lock:
            self._change_generation += 1

    def get_change_generation(self) -> int:
        """Read it before a build of the index, give it to mark_index_built."""
        with self._lock:
            return self._change_generation

    def mark_index_built(self, generation: int) -> None:
        """
        A build that started at this generation succeeded. A change that came
        during the build keeps the index outdated.
        """
        with self._lock:
            self._built_generation = max(self._built_generation, generation)

    def inhibit_paths(self, paths: List[str]) -> Inhibition:
        """
        The watcher of the files leaves these files alone for their next
        change. Call it before the files change, never after: the watcher
        looks at a change 0.3 seconds after it, and an inhibition that comes
        later stays and hides the next change from outside.
        """
        inhibition = Inhibition()
        if self.inhibit_change is not None:
            for path_ in paths:
                inhibition.paths.append(path_)
                if self.inhibit_change(path_) is not False:
                    inhibition.owned.append(path_)
        return inhibition

    def release_inhibition(self, inhibition: Inhibition) -> None:
        """Take back the inhibitions of a change that did not happen."""
        self._release_paths(inhibition.owned)

    def apply_update(
        self,
        changed_paths: List[str],
        *,
        inhibition: Optional[Inhibition] = None,
    ) -> None:
        """
        Tell the server of the project that the update changed these files:
        the revision is raised, the index is built again and the pages are
        told. Call it with the gate, right after the files changed: nothing
        writes with the old index. If the index cannot be built, it stays
        outdated and nothing is saved until a build succeeds (see
        project_gate.py).

        The watcher of the files must not look at these files again. The
        caller inhibits them before the files change (inhibit_paths) and gives
        the inhibition: the ones that did not change are taken back, and the
        ones that changed without it are inhibited now. Without an
        inhibition, all of them are inhibited now.
        """
        before = inhibition if inhibition is not None else Inhibition()
        asked = {os.path.normpath(path_) for path_ in before.paths}
        changed = {os.path.normpath(path_) for path_ in changed_paths}
        self.mark_files_changed()
        self.inhibit_paths(
            [
                path_
                for path_ in changed_paths
                if os.path.normpath(path_) not in asked
            ]
        )
        self._release_paths(
            [
                path_
                for path_ in before.owned
                if os.path.normpath(path_) not in changed
            ]
        )
        self.bump_revision()
        if self.rebuild_and_notify is not None:
            self.rebuild_and_notify()

    def clear_hooks(self) -> None:
        self.rebuild_and_notify = None
        self.inhibit_change = None
        self.release_change = None

    def _release_paths(self, paths: List[str]) -> None:
        if self.release_change is not None:
            for path_ in paths:
                self.release_change(path_)


_runtimes: Dict[str, ProjectRuntime] = {}
_runtimes_lock: threading.Lock = threading.Lock()


def get_project_runtime(folder: str) -> ProjectRuntime:
    """The runtime of the project in the folder, the same for every caller."""
    key = os.path.normcase(os.path.realpath(folder))
    with _runtimes_lock:
        runtime = _runtimes.get(key)
        if runtime is None:
            runtime = ProjectRuntime()
            _runtimes[key] = runtime
        return runtime
