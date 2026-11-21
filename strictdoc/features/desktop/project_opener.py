"""
The opening of a project chosen in the catalog: the clone of its repository
into the folder of the user, the memory of that folder, and the web server of
the project.

The work takes seconds, so a job does it in a thread and the screen polls the
state of the job.

@relation(SDOC-SRS-1230, scope=file)
@relation(SDOC-SRS-1231, scope=file)
"""

import threading
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Optional, Protocol

from strictdoc.features.desktop.settings import load_settings, save_settings
from strictdoc.features.desktop.workspace import (
    WorkspaceError,
    clone_project,
)
from strictdoc.features.i18n.i18n import gettext
from strictdoc.features.project_catalog.catalog import CatalogProject


class ProjectServer(Protocol):
    """The part of LocalServer that the opener uses."""

    @property
    def start_url(self) -> str: ...

    def start(self) -> None: ...

    def wait_until_ready(self) -> None: ...

    def stop(self) -> None: ...


ProjectServerFactory = Callable[[str], ProjectServer]


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
    """
    The jobs that open a project, and the web servers that they started.

    A project that is opened again gets a new server, after the previous one
    of the same project is stopped.
    """

    def __init__(
        self,
        *,
        server_factory: Optional[ProjectServerFactory] = None,
        settings_path: Optional[Path] = None,
    ) -> None:
        self._server_factory: ProjectServerFactory = (
            server_factory
            if server_factory is not None
            else _create_local_server
        )
        self._settings_path: Optional[Path] = settings_path
        self._jobs: Dict[str, OpenJob] = {}
        self._servers: Dict[str, ProjectServer] = {}
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

    def stop_all(self) -> None:
        """Stop the servers of the projects, when the application ends."""
        with self._lock:
            servers = list(self._servers.values())
            self._servers.clear()
        for server_ in servers:
            server_.stop()

    def _run_job(
        self,
        job: OpenJob,
        project: CatalogProject,
        folder: str,
        is_clone_needed: bool,
    ) -> None:
        try:
            if is_clone_needed:
                clone_project(project.clone_url, folder)
                job.step = JobStep.OPENING
            self._remember_folder(project.identifier, folder)
            job.url = self._open_server(project.identifier, folder)
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

    def _open_server(self, identifier: str, folder: str) -> str:
        with self._lock:
            previous_server = self._servers.pop(identifier, None)
        if previous_server is not None:
            previous_server.stop()
        server = self._server_factory(folder)
        server.start()
        try:
            server.wait_until_ready()
        except BaseException:
            server.stop()
            raise
        with self._lock:
            self._servers[identifier] = server
        return server.start_url


def _create_local_server(folder: str) -> ProjectServer:
    # Imported here: the module needs the web server of the project, which
    # the unit tests of the opener do not start.
    from strictdoc.features.desktop.local_server import (  # noqa: PLC0415
        LocalServer,
        create_desktop_project_config,
    )

    project_config = create_desktop_project_config(input_path=folder, port=None)
    return LocalServer(project_config=project_config)
