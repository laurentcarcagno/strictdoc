"""
The web servers of the projects that the user opened.

The application keeps one server per project and the servers of the most
recent projects stay running: going back to a project that is open takes the
time of a page, not of a start. When the number of running servers is above
the setting "kept_servers", the server that was used the longest ago is
stopped.

Each open project is synchronized when it is opened and then every
"sync_interval_minutes" (project_sync.py). The timers end with the server of
the project, with the application, and with the session: a user who signed out
receives nothing, and the timers start again when somebody signs in.

@relation(SDOC-SRS-1232, scope=file)
@relation(SDOC-SRS-1233, scope=file)
@relation(SDOC-SRS-1236, scope=file)
@relation(SDOC-SRS-1238, scope=file)
@relation(SDOC-SRS-1241, scope=file)
@relation(SDOC-SRS-1245, scope=file)
@relation(SDOC-SRS-1246, scope=file)
@relation(SDOC-SRS-1252, scope=file)
"""

import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Set,
)

from strictdoc.features.desktop.commit_author import (
    create_missing_author_provider,
)
from strictdoc.features.desktop.git_access import GitAccess
from strictdoc.features.desktop.project_gate import get_project_gate
from strictdoc.features.desktop.project_runtime import get_project_runtime
from strictdoc.features.desktop.project_sync import (
    SyncOutcome,
    synchronize_project,
)
from strictdoc.features.desktop.settings import load_settings
from strictdoc.features.desktop.workspace import (
    UpdateDeferredError,
    WorkspaceError,
)
from strictdoc.features.git_config.git_service import Author
from strictdoc.features.roles.principal import PrincipalProvider

if TYPE_CHECKING:
    from strictdoc.features.desktop.ai_settings import AiRuntime
    from strictdoc.features.desktop.send_queue import SendQueue

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

    # None for a server with no user: its roles are not decided by the user.
    principal_provider: Optional[PrincipalProvider]
    author_provider: Callable[[], Author]
    # What the Git commands of the server may use. None: no credential at all.
    git_access: Optional[GitAccess] = None
    # The queue that sends the commits of the server. None: nothing is sent.
    send_queue: Optional["SendQueue"] = None
    # The AI servers of the user, which give the project its assistant. None:
    # the project keeps its own configuration.
    ai_runtime: Optional["AiRuntime"] = None


# Receives the folder and the identity of the server, if it has one.
ProjectServerFactory = Callable[[str, Optional[ProjectIdentity]], ProjectServer]
# Receives the identifier of a project: gives the identity of its server, or
# None for a server that has no user.
IdentityFactory = Callable[[str], Optional[ProjectIdentity]]
# Returns True when the update changed files. Raises WorkspaceError. The
# manager uses the synchronization (project_sync.py) when it is given none.
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
        git_access: Optional[GitAccess] = None,
        sync_interval_seconds: Optional[float] = None,
    ) -> None:
        self._identity_factory: Optional[IdentityFactory] = identity_factory
        self._server_factory: ProjectServerFactory = (
            server_factory
            if server_factory is not None
            else _create_local_server
        )
        self._updater: Optional[ProjectUpdater] = updater
        self._git_access: Optional[GitAccess] = git_access
        # The seconds between two synchronizations. Without a value, the
        # setting "sync_interval_minutes" of the user decides, read each time.
        self._sync_interval_seconds: Optional[float] = sync_interval_seconds
        # Who acts in each open project, and the timer of its next
        # synchronization.
        self._identities: Dict[str, Optional[ProjectIdentity]] = {}
        self._sync_timers: Dict[str, threading.Timer] = {}
        self._is_paused: bool = False
        self._settings_path: Optional[Path] = settings_path
        self._eviction_delay_seconds: float = eviction_delay_seconds
        # From the project used the longest ago to the most recent one.
        self._projects: OrderedDict[str, OpenProject] = OrderedDict()
        self._state_lock: threading.Lock = threading.Lock()
        # One server is started at a time. A reader of the state never waits
        # for it.
        self._start_lock: threading.Lock = threading.Lock()
        self._updating: Set[str] = set()
        # The projects whose update waits for the end of the typing, and the
        # folders whose leases this manager listens to.
        self._deferred: Dict[str, str] = {}
        # The projects whose update must run again when the one that runs ends:
        # the editors were closed while it looked.
        self._rerun: Dict[str, str] = {}
        self._listened_folders: Set[str] = set()
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
        else:
            self._schedule_next_sync(identifier, folder)
        return project.get_url()

    def get_open_identifiers(self) -> Set[str]:
        with self._state_lock:
            return set(self._projects)

    def stop_project(self, identifier: str) -> None:
        """Stop the server of a project that the user cannot open any more."""
        with self._state_lock:
            project = self._projects.pop(identifier, None)
            self._forget_project_locked(identifier)
        if project is not None:
            project.server.stop()

    def stop_servers(self) -> None:
        """
        Stop every server. A project opened afterwards starts a new one.
        """
        with self._state_lock:
            projects = list(self._projects.values())
            self._projects.clear()
            for identifier_ in list(self._sync_timers):
                self._cancel_sync_timer_locked(identifier_)
            for project_ in projects:
                self._forget_project_locked(project_.identifier)
        for project_ in projects:
            project_.server.stop()

    def stop_all(self) -> None:
        """Stop every server, when the application ends."""
        with self._state_lock:
            self._is_stopped = True
        self.stop_servers()

    def synchronize_project(self, identifier: str, folder: str) -> None:
        """
        Synchronize the project now, in the background: the button "Update".
        Nothing happens when a synchronization of the project already runs.
        """
        self._update_in_background(identifier, folder)

    def apply_settings(self) -> None:
        """
        The user changed the settings: no restart. The timers of the open
        projects start again with the new time between two updates, and the
        pages that the servers keep are made again in the new language when
        they are asked for next.
        """
        with self._state_lock:
            projects = [
                (identifier_, project_.folder)
                for identifier_, project_ in self._projects.items()
            ]
            servers = [project_.server for project_ in self._projects.values()]
        for identifier_, folder_ in projects:
            self._schedule_next_sync(identifier_, folder_)
        for server_ in servers:
            refresh_pages = getattr(server_, "refresh_pages", None)
            if refresh_pages is not None:
                refresh_pages()

    def pause_timers(self) -> None:
        """
        Nobody is signed in: no project receives anything. The timers end, and
        resume_timers starts them again.
        """
        with self._state_lock:
            self._is_paused = True
            for identifier_ in list(self._sync_timers):
                self._cancel_sync_timer_locked(identifier_)

    def resume_timers(self) -> None:
        """Somebody signed in: every open project is synchronized at once."""
        with self._state_lock:
            self._is_paused = False
            projects = [
                (identifier_, project_.folder)
                for identifier_, project_ in self._projects.items()
            ]
        for identifier_, folder_ in projects:
            self._update_in_background(identifier_, folder_)

    def _start_server(self, identifier: str, folder: str) -> OpenProject:
        with self._state_lock:
            previous_project = self._projects.pop(identifier, None)
            if previous_project is not None:
                self._forget_project_locked(identifier)
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
        with self._state_lock:
            self._identities[identifier] = identity
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
                identifier_, project = self._projects.popitem(last=False)
                self._forget_project_locked(identifier_)
                stopped_projects.append(project)
        for project_ in stopped_projects:
            project_.server.stop()

    def _update_in_background(self, identifier: str, folder: str) -> None:
        with self._state_lock:
            if not self._is_open_locked(identifier, folder):
                return
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

    def _defer_update(self, identifier: str, folder: str) -> bool:
        """
        Apply the update when the last editor of the project is closed. The
        update is the same call: the fetch is quick, and the files change then.
        It returns True when the editors were closed since the update looked:
        the caller asks for the update again, when this one has ended.
        """
        runtime = get_project_runtime(folder)
        with self._state_lock:
            if not self._is_open_locked(identifier, folder):
                # The project was closed while the update looked: nothing
                # waits for it.
                runtime.is_update_waiting = False
                return False
            runtime.is_update_waiting = True
            self._deferred[identifier] = folder
            if folder not in self._listened_folders:
                self._listened_folders.add(folder)
                runtime.leases.add_listener(
                    lambda: self._on_editing_ended(folder)
                )
        logger.info("Project %s: the update waits for the typing.", identifier)
        return not runtime.leases.is_editing()

    def _on_editing_ended(self, folder: str) -> None:
        with self._state_lock:
            identifiers = [
                identifier_
                for identifier_, folder_ in self._deferred.items()
                if folder_ == folder
            ]
            for identifier_ in identifiers:
                del self._deferred[identifier_]
        for identifier_ in identifiers:
            with self._state_lock:
                if not self._is_open_locked(identifier_, folder):
                    continue
                if identifier_ in self._updating:
                    self._rerun[identifier_] = folder
                    continue
            self._update_in_background(identifier_, folder)

    def _update(self, identifier: str, folder: str) -> None:
        """
        Offline, without a remote or with a conflict, the update does nothing:
        the reason goes to the log and the screen shows nothing. The update
        is announced as waiting only while it waits for the end of the typing:
        any other end, a failure too, takes the announcement back.
        """
        with self._state_lock:
            if not self._is_open_locked(identifier, folder):
                # The project was closed since the update was asked for.
                self._updating.discard(identifier)
                return
        is_retry_needed = False
        is_postponed = False
        try:
            is_changed = self._run_update(identifier, folder)
            logger.info(
                "Project %s: %s.",
                identifier,
                "updated from its remote"
                if is_changed
                else "already up to date",
            )
        except UpdateDeferredError:
            is_postponed = True
            is_retry_needed = self._defer_update(identifier, folder)
        except WorkspaceError as exception_:
            logger.warning(
                "Project %s: not updated from its remote: %s",
                identifier,
                exception_,
            )
        except Exception:
            logger.exception("Project %s: the update failed.", identifier)
        finally:
            if not is_postponed:
                get_project_runtime(folder).is_update_waiting = False
            with self._state_lock:
                self._updating.discard(identifier)
                rerun_folder = self._rerun.pop(identifier, None)
            self._schedule_next_sync(identifier, folder)
        if is_retry_needed:
            self._on_editing_ended(folder)
        if rerun_folder is not None:
            self._update_in_background(identifier, rerun_folder)

    def _run_update(self, identifier: str, folder: str) -> bool:
        if self._updater is not None:
            return self._updater(folder)
        with self._state_lock:
            identity = self._identities.get(identifier)
        role: Optional[str] = None
        if identity is not None and identity.principal_provider is not None:
            principal = identity.principal_provider()
            if principal is None:
                raise WorkspaceError("Nobody is signed in to this project.")
            role = principal.role
        outcome = synchronize_project(
            folder,
            git_access=(
                identity.git_access
                if identity is not None and identity.git_access is not None
                else self._git_access
                if self._git_access is not None
                else GitAccess()
            ),
            gate=get_project_gate(folder),
            runtime=get_project_runtime(folder),
            author_provider=(
                identity.author_provider
                if identity is not None
                else create_missing_author_provider()
            ),
            role=role,
            send_queue=identity.send_queue if identity is not None else None,
        )
        return outcome is SyncOutcome.UPDATED

    def _get_interval_seconds(self) -> float:
        if self._sync_interval_seconds is not None:
            return self._sync_interval_seconds
        minutes = load_settings(self._settings_path).sync_interval_minutes
        return float(minutes) * 60.0

    def _schedule_next_sync(self, identifier: str, folder: str) -> None:
        """
        Look again after the interval, while the project is open, the
        application runs and somebody is signed in.
        """
        interval = self._get_interval_seconds()
        with self._state_lock:
            self._cancel_sync_timer_locked(identifier)
            project = self._projects.get(identifier)
            if (
                self._is_stopped
                or self._is_paused
                or project is None
                or project.folder != folder
            ):
                return
            timer = threading.Timer(
                interval, self._on_sync_timer, args=(identifier, folder)
            )
            timer.daemon = True
            self._sync_timers[identifier] = timer
            timer.start()

    def _is_open_locked(self, identifier: str, folder: str) -> bool:
        """True while the project is open, with this folder."""
        project = self._projects.get(identifier)
        return (
            project is not None
            and project.folder == folder
            and not self._is_stopped
        )

    def _forget_project_locked(self, identifier: str) -> None:
        """
        The server of the project stops: its timer ends, and no update waits
        for it or runs again for it.
        """
        self._cancel_sync_timer_locked(identifier)
        self._rerun.pop(identifier, None)
        folder = self._deferred.pop(identifier, None)
        if folder is not None:
            get_project_runtime(folder).is_update_waiting = False

    def _cancel_sync_timer_locked(self, identifier: str) -> None:
        timer = self._sync_timers.pop(identifier, None)
        if timer is not None:
            timer.cancel()

    def _on_sync_timer(self, identifier: str, folder: str) -> None:
        with self._state_lock:
            self._sync_timers.pop(identifier, None)
            project = self._projects.get(identifier)
            is_open = (
                project is not None
                and project.folder == folder
                and not self._is_stopped
                and not self._is_paused
            )
        if is_open:
            self._update_in_background(identifier, folder)


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
        ai_runtime=identity.ai_runtime if identity is not None else None,
    )
    return LocalServer(
        project_config=project_config,
        author_provider=(
            identity.author_provider if identity is not None else None
        ),
        git_access=identity.git_access if identity is not None else None,
        send_queue=identity.send_queue if identity is not None else None,
    )
