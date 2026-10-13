"""
Jobs: commands on a whole document take minutes with a local model, so they
run in a thread and the browser asks for the progress and the proposals found
so far. A job lives in memory, belongs to one user, and is forgotten an hour
after it ends. A person runs one job at a time.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from strictdoc.features.llm.assist.envelope import (
    Action,
    AssistResult,
    Finding,
    new_id,
)

MAX_JOBS = 50
KEEP_SECONDS = 3600.0
MAX_RUNNING = 4

STATE_RUNNING = "running"
STATE_DONE = "ok"
STATE_ERROR = "error"
STATE_CANCELLED = "cancelled"


class JobError(Exception):
    """A job cannot be started."""


class JobCancelled(Exception):
    """Raised inside a job when its owner cancelled it."""


@dataclass
class Job:
    id: str
    user: str
    command: str
    state: str = STATE_RUNNING
    done: int = 0
    total: int = 0
    label: str = ""
    message: str = ""
    error: str = ""
    actions: List[Action] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    meta: Dict[str, object] = field(default_factory=dict)
    created: float = field(default_factory=time.monotonic)
    finished: Optional[float] = None
    cancel_requested: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    # -- used by the worker ---------------------------------------------------

    def progress(self, done: int, total: int, label: str = "") -> None:
        with self.lock:
            self.done, self.total, self.label = done, total, label

    def check(self) -> None:
        if self.cancel_requested:
            raise JobCancelled()

    def add(
        self,
        actions: Optional[List[Action]] = None,
        findings: Optional[List[Finding]] = None,
        warnings: Optional[List[str]] = None,
    ) -> None:
        with self.lock:
            self.actions.extend(actions or [])
            self.findings.extend(findings or [])
            self.warnings.extend(warnings or [])

    # -- read by the router ---------------------------------------------------

    def snapshot(self) -> AssistResult:
        with self.lock:
            result = AssistResult(
                command=self.command,
                status=self.state,
                message=self.message or self.error,
                actions=list(self.actions),
                findings=list(self.findings),
                warnings=list(self.warnings),
                meta=dict(self.meta),
            )
            result.meta["job"] = {
                "id": self.id,
                "done": self.done,
                "total": self.total,
                "label": self.label,
                "running": self.state == STATE_RUNNING,
            }
            if self.error:
                result.meta["error"] = self.error
            return result


class JobManager:
    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def _forget_old(self) -> None:
        now = time.monotonic()
        for id_, job_ in list(self._jobs.items()):
            if job_.finished is not None and now - job_.finished > KEEP_SECONDS:
                del self._jobs[id_]
        while len(self._jobs) > MAX_JOBS:
            self._jobs.pop(next(iter(self._jobs)))

    def start(
        self,
        user: str,
        command: str,
        work: Callable[[Job], None],
        on_finish: Callable[[Job], None],
    ) -> Job:
        """Runs work(job) in a thread; on_finish(job) runs when it has ended."""
        with self._lock:
            self._forget_old()
            mine = [
                job_
                for job_ in self._jobs.values()
                if job_.user == user and job_.state == STATE_RUNNING
            ]
            running = [
                job_
                for job_ in self._jobs.values()
                if job_.state == STATE_RUNNING
            ]
            if mine:
                raise JobError(
                    "You already have a job running: wait for it or cancel it."
                )
            if len(running) >= MAX_RUNNING:
                raise JobError("Too many jobs are running: try again later.")
            job = Job(id=new_id("j"), user=user, command=command)
            self._jobs[job.id] = job

        def target() -> None:
            try:
                work(job)
                with job.lock:
                    job.state = STATE_DONE
            except JobCancelled:
                with job.lock:
                    job.state = STATE_CANCELLED
                    job.message = "Cancelled."
            except Exception as exception_:  # noqa: BLE001
                with job.lock:
                    job.state = STATE_ERROR
                    job.error = str(exception_) or "The job failed."
            finally:
                job.finished = time.monotonic()
                try:
                    on_finish(job)
                except Exception:  # noqa: BLE001, S110
                    pass

        threading.Thread(target=target, daemon=True).start()
        return job

    def get(self, job_id: str, user: str) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            return job if job is not None and job.user == user else None
