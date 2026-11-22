"""
The web servers of the projects that the user opened.

The application keeps one server per project and the servers of the most
recent projects stay running: going back to a project that is open takes the
time of a page, not of a start. When the number of running servers is above
the setting "kept_servers", the server that was used the longest ago is
stopped.

@relation(SDOC-SRS-1232, scope=file)
@relation(SDOC-SRS-1233, scope=file)
@relation(SDOC-SRS-1236, scope=file)
@relation(SDOC-SRS-1238, scope=file)
"""

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Protocol, Set

from strictdoc.features.desktop.settings import load_settings
from strictdoc.features.desktop.workspace import WorkspaceError, pull_project
from strictdoc.features.git_config.git_service import Author
from strictdoc.features.roles.principal import PrincipalProvider

logger = logging.getLogger(__name__)

# The server that is stopped is stopped after the window has loaded the page of
# the new project, so that no visible request is cut.
EVICTION_DELAY_SECONDS = 1.5


class ProjectServer(Protocol):
    """The part of LocalServer that the manager uses."""

    @property
    def start_url(self) -> str: ...

    @property
    def direct_url(self) -> str: ...

    @property
    def is_bootstrapped(self) -> bool: ...

    def set_bootstrap_listener(
        self, listener: Optional[Callable[[], None]]
    ) -> None: ...

    def start(self) -> None: ...

    def wait_until_ready(self) -> None: ...

    def stop(self) -> None: ...


@dataclass(frozen=True)
class ProjectIdentity:
    """Who acts in the server of a project, and who signs its commits."""

    principal_provider: PrincipalProvider
    author_provider: Callable[[], Author]


# Receives the folder and the identity of the server, if it has one.
ProjectServerFactory = Callable[[str, Optional[ProjectIdentity]], ProjectServer]
# Receives the identifier of a project: gives the identity of its server, or
# None for a server that has no user.
IdentityFactory = Callable[[str], Optional[ProjectIdentity]]
# Returns True when the update changed files. Raises WorkspaceError.
ProjectUpdater = Callable[[str], bool]


@dataclass
class OpenProject:
    identifier: str
    folder: str
    server: ProjectServer

    def get_url(self) -> str:
        """
        The address that shows the project in the window. A window that has
        followed the start URL has the cookie of the server, so that it uses
        the direct address. Otherwise it needs the start URL.
        """
        if self.server.is_bootstrapped:
            return self.server.direct_url
        return self.server.start_url


class ProjectServerManager:
    """
    Thread-safe: the requests of the home server and the threads of the jobs
    call it at the same time.
    """

    def __init__(
        self,
        *,
        server_factory: Optional[ProjectServerFactory] = None,
        updater: Optional[ProjectUpdater] = None,
        settings_path: Optional[Path] = None,
        eviction_delay_seconds: float = EVICTION_DELAY_SECONDS,
        identity_factory: Optional[IdentityFactory] = None,
    ) -> None:
        self._identity_factory: Optional[IdentityFactory] = identity_factory
        self._server_factory: ProjectServerFactory = (
            server_factory
            if server_factory is not None
            else _create_local_server
        )
        self._updater: ProjectUpdater = (
            updater if updater is not None else pull_project
        )
        self._settings_path: Optional[Path] = settings_path
        self._eviction_delay_seconds: float = eviction_delay_seconds
        # From the project used the longest ago to the most recent one.
        self._projects: OrderedDict[str, OpenProject] = OrderedDict()
        self._state_lock: threading.Lock = threading.Lock()
        # One server is started at a time. A reader of the state never waits
        # for it.
        self._start_lock: threading.Lock = threading.Lock()
        self._updating: Set[str] = set()
        self._is_stopped: bool = False

    def get_open_url(self, identifier: str, folder: str) -> Optional[str]:
        """
        The address of the project when its server runs, or None. It does not
        start anything: it is the fast way back to an open project. The
        project is updated in the background.
        """
        with self._state_lock:
            project = self._projects.get(identifier)
            if project is None or project.folder != folder:
                return None
            self._projects.move_to_end(identifier)
            url = project.get_url()
        self._update_in_background(identifier, folder)
        return url

    def open(
        self, identifier: str, folder: str, *, is_update_needed: bool = True
    ) -> str:
        """
        The address of the project. It starts the server of the project if it
        does not run. The caller waits for the start, which takes seconds.
        """
        url = self.get_open_url(identifier, folder)
        if url is not None:
            return url
        with self._start_lock:
            # Another thread may have started the server while this one waited.
            url = self.get_open_url(identifier, folder)
            if url is not None:
                return url
            self._stop_excess_servers()
            project = self._start_server(identifier, folder)
        if is_update_needed:
            self._update_in_background(identifier, folder)
        return project.get_url()

    def get_open_identifiers(self) -> Set[str]:
        with self._state_lock:
            return set(self._projects)

    def stop_project(self, identifier: str) -> None:
        """Stop the server of a project that the user cannot open any more."""
        with self._state_lock:
            project = self._projects.pop(identifier, None)
        if project is not None:
            project.server.stop()

    def stop_all(self) -> None:
        """Stop every server, when the application ends."""
        with self._state_lock:
            self._is_stopped = True
            projects = list(self._projects.values())
            self._projects.clear()
        for project_ in projects:
            project_.server.stop()

    def _start_server(self, identifier: str, folder: str) -> OpenProject:
        with self._state_lock:
            previous_project = self._projects.pop(identifier, None)
        if previous_project is not None:
            # The folder of the project changed: the old server shows the
            # old folder.
            previous_project.server.stop()
        identity = (
            self._identity_factory(identifier)
            if self._identity_factory is not None
            else None
        )
        server = self._server_factory(folder, identity)
        server.start()
        try:
            server.wait_until_ready()
        except BaseException:
            server.stop()
            raise
        project = OpenProject(identifier, folder, server)
        with self._state_lock:
            if self._is_stopped:
                # The application ended while the server started.
                server.stop()
                raise RuntimeError("The application is stopping.")
            self._projects[identifier] = project
        # The window follows the start URL, which gives it the cookie. The
        # oldest server stops after that, when the page is shown.
        server.set_bootstrap_listener(self._schedule_stop_of_excess_servers)
        return project

    def _schedule_stop_of_excess_servers(self) -> None:
        timer = threading.Timer(
            self._eviction_delay_seconds, self._stop_excess_servers
        )
        timer.daemon = True
        timer.start()

    def _stop_excess_servers(self) -> None:
        """Stop the servers used the longest ago, above "kept_servers"."""
        kept_servers = load_settings(self._settings_path).kept_servers
        stopped_projects: List[OpenProject] = []
        with self._state_lock:
            while len(self._projects) > kept_servers:
                _, project = self._projects.popitem(last=False)
                stopped_projects.append(project)
        for project_ in stopped_projects:
            project_.server.stop()

    def _update_in_background(self, identifier: str, folder: str) -> None:
        with self._state_lock:
            if identifier in self._updating:
                return
            self._updating.add(identifier)
        thread = threading.Thread(
            target=self._update,
            args=(identifier, folder),
            name="strictdoc-update-project",
            daemon=True,
        )
        thread.start()

    def _update(self, identifier: str, folder: str) -> None:
        """
        Offline, without a remote or with a conflict, the update does nothing:
        the reason goes to the log and the screen shows nothing.
        """
        try:
            is_changed = self._updater(folder)
            logger.info(
                "Project %s: %s.",
                identifier,
                "updated from its remote"
                if is_changed
                else "already up to date",
            )
        except WorkspaceError as exception_:
            logger.warning(
                "Project %s: not updated from its remote: %s",
                identifier,
                exception_,
            )
        except Exception:
            logger.exception("Project %s: the update failed.", identifier)
        finally:
            with self._state_lock:
                self._updating.discard(identifier)


def _create_local_server(
    folder: str, identity: Optional[ProjectIdentity]
) -> ProjectServer:
    # Imported here: the module needs the web server of the project, which
    # the unit tests of the manager do not start.
    from strictdoc.features.desktop.local_server import (  # noqa: PLC0415
        LocalServer,
        create_desktop_project_config,
    )

    project_config = create_desktop_project_config(
        input_path=folder,
        port=None,
        principal_provider=(
            identity.principal_provider if identity is not None else None
        ),
    )
    return LocalServer(
        project_config=project_config,
        author_provider=(
            identity.author_provider if identity is not None else None
        ),
    )
