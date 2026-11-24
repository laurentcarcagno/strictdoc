"""
The opening of a project chosen in the catalog: the clone of its repository
into the folder of the user, the memory of that folder, and the web server of
the project (project_servers.py).

The work takes seconds, so a job does it in a thread and the screen polls the
state of the job.

@relation(SDOC-SRS-1230, scope=file)
@relation(SDOC-SRS-1231, scope=file)
@relation(SDOC-SRS-1241, scope=file)
"""

import threading
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

from strictdoc.features.desktop.git_access import GitAccess
from strictdoc.features.desktop.project_servers import ProjectServerManager
from strictdoc.features.desktop.settings import load_settings, save_settings
from strictdoc.features.desktop.workspace import (
    WorkspaceError,
    clone_project,
)
from strictdoc.features.i18n.i18n import gettext
from strictdoc.features.project_catalog.catalog import CatalogProject


class JobState(str, Enum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class JobStep(str, Enum):
    CLONING = "cloning"
    OPENING = "opening"


@dataclass
class OpenJob:
    job_id: str
    project_title: str
    state: JobState = JobState.RUNNING
    step: JobStep = JobStep.OPENING
    # The message of a failed job, for the user.
    message: str = ""
    # The address that shows the project, once the job is done.
    url: str = ""


class ProjectOpener:
    """The jobs that clone a project, remember its folder and open it."""

    def __init__(
        self,
        *,
        manager: ProjectServerManager,
        settings_path: Optional[Path] = None,
        git_access: Optional[GitAccess] = None,
    ) -> None:
        self.manager: ProjectServerManager = manager
        self._git_access: Optional[GitAccess] = git_access
        self._settings_path: Optional[Path] = settings_path
        self._jobs: Dict[str, OpenJob] = {}
        self._lock: threading.Lock = threading.Lock()

    def start_job(
        self, project: CatalogProject, folder: str, *, is_clone_needed: bool
    ) -> OpenJob:
        job = OpenJob(
            job_id=uuid.uuid4().hex,
            project_title=project.title,
            step=JobStep.CLONING if is_clone_needed else JobStep.OPENING,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        thread = threading.Thread(
            target=self._run_job,
            args=(job, project, folder, is_clone_needed),
            name="strictdoc-open-project",
            daemon=True,
        )
        thread.start()
        return job

    def get_job(self, job_id: str) -> Optional[OpenJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def _run_job(
        self,
        job: OpenJob,
        project: CatalogProject,
        folder: str,
        is_clone_needed: bool,
    ) -> None:
        try:
            if is_clone_needed:
                clone_project(
                    project.clone_url, folder, git_access=self._git_access
                )
                job.step = JobStep.OPENING
            self._remember_folder(project.identifier, folder)
            # A project that was just cloned is up to date.
            job.url = self.manager.open(
                project.identifier,
                folder,
                is_update_needed=not is_clone_needed,
            )
        except WorkspaceError as exception_:
            job.message = str(exception_)
            job.state = JobState.FAILED
        except (Exception, SystemExit) as exception_:  # noqa: BLE001
            # A project that cannot be read is a message in the screen, not a
            # lost thread.
            job.message = gettext(
                "The project cannot be opened: %(reason)s"
            ) % {"reason": exception_}
            job.state = JobState.FAILED
        else:
            job.state = JobState.DONE

    def _remember_folder(self, identifier: str, folder: str) -> None:
        with self._lock:
            settings = load_settings(self._settings_path)
            settings.project_folders[identifier] = folder
            save_settings(settings, self._settings_path)
