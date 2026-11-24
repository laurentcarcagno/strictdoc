"""
The web server of a project for the desktop application.

@relation(SDOC-SRS-1220, scope=file)
@relation(SDOC-SRS-1221, scope=file)
@relation(SDOC-SRS-1222, scope=file)
@relation(SDOC-SRS-1225, scope=file)
@relation(SDOC-SRS-1229, scope=file)
@relation(SDOC-SRS-1234, scope=file)
@relation(SDOC-SRS-1236, scope=file)
@relation(SDOC-SRS-1238, scope=file)
@relation(SDOC-SRS-1239, scope=file)
@relation(SDOC-SRS-1241, scope=file)
@relation(SDOC-SRS-1242, scope=file)
@relation(SDOC-SRS-1244, scope=file)
@relation(SDOC-SRS-1245, scope=file)
@relation(SDOC-SRS-1246, scope=file)
@relation(SDOC-SRS-1247, scope=file)
@relation(SDOC-SRS-1250, scope=file)
@relation(SDOC-SRS-1252, scope=file)
@relation(SDOC-SRS-1258, scope=file)
"""

import asyncio
import logging
import os
import signal
import socket
import threading
import time
from types import FrameType
from typing import Any, Callable, Dict, List, Optional

import uvicorn
from jinja2 import ChoiceLoader, FileSystemLoader
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

import strictdoc.server.app as server_app
from strictdoc import __version__
from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import (
    ProjectConfig,
    ProjectConfigLoader,
    ProjectFeature,
)
from strictdoc.features.desktop.ai_settings import AiRuntime
from strictdoc.features.desktop.application_language import (
    restore_application_language,
)
from strictdoc.features.desktop.bundled_tools import find_bundled_tools
from strictdoc.features.desktop.commit_author import (
    create_missing_author_provider,
)
from strictdoc.features.desktop.git_access import (
    NO_GITLAB_TOKEN_VARIABLE,
    DesktopGitService,
    GitAccess,
)
from strictdoc.features.desktop.paths import (
    get_project_output_dir,
    get_project_sdoc_cache_dir,
)
from strictdoc.features.desktop.permissions import (
    get_resolve_role,
    get_route_role_overrides,
)
from strictdoc.features.desktop.project_gate import (
    ProjectGate,
    ProjectGateMiddleware,
    get_project_gate,
)
from strictdoc.features.desktop.project_publish import create_publish_routes
from strictdoc.features.desktop.project_runtime import (
    ProjectRuntime,
    get_project_runtime,
)
from strictdoc.features.desktop.project_status import (
    INDICATOR_GLOBAL,
    TEMPLATES_DIR,
    ProjectStatus,
    ProjectStatusMiddleware,
    SendState,
    get_project_status,
)
from strictdoc.features.desktop.project_sync import (
    create_sync_routes,
    get_merge_key,
)
from strictdoc.features.desktop.send_queue import SendQueue
from strictdoc.features.desktop.session_token import (
    BOOTSTRAP_CODE_PARAMETER,
    BOOTSTRAP_PATH,
    PUBLIC_PATHS_STATE_NAME,
    DesktopSessionMiddleware,
    SessionCredentials,
)
from strictdoc.features.desktop.wording import install_application_wording
from strictdoc.features.git_config.committer import GitCommitter
from strictdoc.features.git_config.config import GitConfig
from strictdoc.features.git_config.git_service import Author
from strictdoc.features.git_config.setup import find_project_root
from strictdoc.features.roles.enforcement import RoleMiddleware
from strictdoc.features.roles.middleware import PrincipalMiddleware
from strictdoc.features.roles.principal import PrincipalProvider
from strictdoc.server.app import create_app

logger = logging.getLogger(__name__)

# The variables of the Jinja environment that turn on, in the templates of the
# synchronization, the words of the application and the role that resolves.
WORDING_GLOBAL = "desktop_application"
RESOLVE_ROLE_GLOBAL = "desktop_resolve_role"

# The host cannot be set: only the program on this computer reaches the server.
LOCAL_SERVER_HOST = "127.0.0.1"

# The pages of the comparison of Git revisions, which the application hides.
COMPARISON_PATHS = ("/diff", "/diff_result")

_POLL_INTERVAL_SECONDS = 0.05


class LocalServerError(Exception):
    pass


class LocalServer:
    """
    One web server of the desktop application, run in a thread of this
    process: the server of one project, or the server of the home screen.

    The server of a project is given its project configuration. Another
    server is given a function that creates its application. Without a port,
    the server takes a free port of the loopback address.
    """

    def __init__(
        self,
        *,
        project_config: Optional[ProjectConfig] = None,
        application_factory: Optional[Callable[[], Starlette]] = None,
        port: Optional[int] = None,
        author_provider: Optional[Callable[[], Author]] = None,
        git_access: Optional[GitAccess] = None,
        send_queue: Optional[SendQueue] = None,
    ) -> None:
        assert (project_config is None) != (application_factory is None), (
            "Give the project configuration or the application factory."
        )
        self._project_config: Optional[ProjectConfig] = project_config
        self._application_factory: Optional[Callable[[], Starlette]] = (
            application_factory
        )
        self._requested_port: Optional[int] = port
        # The author of the commits of a project server, when the user is not
        # the one that the project configuration names.
        self._author_provider: Optional[Callable[[], Author]] = author_provider
        # What the Git commands of a project server may use.
        self._git_access: Optional[GitAccess] = git_access
        # The queue that sends the commits of a project server.
        self._send_queue: Optional[SendQueue] = send_queue
        self._socket: Optional[socket.socket] = None
        self._application: Optional[Starlette] = None
        self._server: Optional[uvicorn.Server] = None
        self._thread: Optional[threading.Thread] = None
        self._error: Optional[BaseException] = None
        self._credentials: SessionCredentials = SessionCredentials.create()

    @property
    def port(self) -> int:
        assert self._socket is not None, "The server is not started."
        port: int = self._socket.getsockname()[1]
        return port

    @property
    def url(self) -> str:
        return f"http://{LOCAL_SERVER_HOST}:{self.port}"

    @property
    def is_bootstrapped(self) -> bool:
        """
        True once the window has followed the start URL: it has the session
        cookie of this port, so that the direct URL works.
        """
        return self._credentials.is_bootstrap_code_used

    @property
    def direct_url(self) -> str:
        """The address of the home page, for a window that has the cookie."""
        return f"{self.url}/"

    @property
    def start_url(self) -> str:
        """
        The URL that the window opens: it gives the session cookie to the
        window, once, and redirects to the home page.
        """
        return (
            f"{self.url}{BOOTSTRAP_PATH}"
            f"?{BOOTSTRAP_CODE_PARAMETER}={self._credentials.bootstrap_code}"
        )

    def create_restart_path(self) -> str:
        """
        The path that gives the session cookie to a window that lost it, once:
        the user signed out and the window forgot all its cookies. It comes
        with a new bootstrap code, and the session token stays.
        """
        code = self._credentials.renew_bootstrap_code()
        return f"{BOOTSTRAP_PATH}?{BOOTSTRAP_CODE_PARAMETER}={code}"

    def set_bootstrap_listener(
        self, listener: Optional[Callable[[], None]]
    ) -> None:
        """Call the function when the window follows the start URL."""
        self._credentials.bootstrap_listener = listener

    def start(self) -> None:
        """
        Open the port, build the application and run the server in a thread.

        The caller waits in this method while the application reads the
        documents of the project.
        """
        assert self._thread is None, "The server is already started."
        server_socket = self._open_socket()
        try:
            self._socket = server_socket
            application = self._create_application()
            self._application = application
            application.state.desktop_create_restart_path = (
                self.create_restart_path
            )
            # Added last, so that it is the outermost: no route and no other
            # middleware sees a request that the window did not send.
            application.add_middleware(
                DesktopSessionMiddleware,
                credentials=self._credentials,
                port=self.port,
                allowed_hosts=frozenset(
                    {
                        f"{LOCAL_SERVER_HOST}:{self.port}",
                        f"localhost:{self.port}",
                    }
                ),
                # The application tells which paths can do without the
                # cookie, and when.
                public_paths=getattr(
                    application.state, PUBLIC_PATHS_STATE_NAME, {}
                ),
            )
        except BaseException:
            server_socket.close()
            self._socket = None
            raise

        config = uvicorn.Config(
            application,
            host=LOCAL_SERVER_HOST,
            port=self.port,
            log_level="info",
            # The access log shows the URL of every request, so it would show
            # the bootstrap code. The errors are still logged.
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        # Uvicorn installs signal handlers only in the main thread, so a thread
        # leaves the signals to the caller.
        self._thread = threading.Thread(
            target=self._run, name="strictdoc-local-server", daemon=True
        )
        self._thread.start()

    def wait_until_ready(self, timeout_seconds: float = 120.0) -> None:
        assert self._server is not None and self._thread is not None, (
            "The server is not started."
        )
        deadline = time.monotonic() + timeout_seconds
        while not self._server.started:
            if not self._thread.is_alive():
                raise LocalServerError(
                    "The server stopped before it was ready"
                    + (f": {self._error}" if self._error is not None else ".")
                )
            if time.monotonic() >= deadline:
                raise LocalServerError(
                    f"The server is not ready after {timeout_seconds} seconds."
                )
            time.sleep(_POLL_INTERVAL_SECONDS)

    def stop(self, timeout_seconds: float = 10.0) -> None:
        """Stop the server and close the port. Stopping twice is harmless."""
        if self._server is not None and self._thread is not None:
            self._server.should_exit = True
            self._thread.join(timeout_seconds)
            if self._thread.is_alive():
                self._server.force_exit = True
                self._thread.join(timeout_seconds)
        self._server = None
        self._thread = None
        if self._application is not None:
            release_hooks = getattr(
                self._application.state, "desktop_release_hooks", None
            )
            if release_hooks is not None:
                release_hooks()
            self._application = None
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def refresh_pages(self) -> None:
        """
        Make the pages of the project again when they are asked for next: the
        server keeps the pages that it made, and a page made in another
        language must not stay.
        """
        application = self._application
        context = (
            getattr(application.state, "project_context", None)
            if application is not None
            else None
        )
        if context is not None:
            context.export_action.traceability_index.update_last_updated()

    def _create_application(self) -> Starlette:
        if self._application_factory is not None:
            return self._application_factory()
        assert self._project_config is not None
        self._project_config.server_host = LOCAL_SERVER_HOST
        self._project_config.server_port = self.port
        # create_app starts the banner from its lifespan, which looks the
        # function up in the module when the server starts.
        server_app.print_welcome_message = _print_no_welcome_message
        return create_project_application(
            self._project_config,
            self._author_provider,
            self._git_access,
            self._send_queue,
        )

    def _open_socket(self) -> socket.socket:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if os.name != "nt":
                # Like uvicorn: a port in the TIME_WAIT state can be reused.
                server_socket.setsockopt(
                    socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
                )
            server_socket.bind(
                (
                    LOCAL_SERVER_HOST,
                    self._requested_port
                    if self._requested_port is not None
                    else 0,
                )
            )
        except OSError as exception_:
            server_socket.close()
            if self._requested_port is None:
                raise LocalServerError(
                    f"Cannot find a free port on {LOCAL_SERVER_HOST}: "
                    f"{exception_}"
                ) from exception_
            raise LocalServerError(
                f"Cannot listen on {LOCAL_SERVER_HOST}"
                f":{self._requested_port}: {exception_}"
            ) from exception_
        return server_socket

    def _run(self) -> None:
        assert self._server is not None and self._socket is not None
        try:
            asyncio.run(self._server.serve(sockets=[self._socket]))
        except (Exception, SystemExit) as exception_:
            self._error = exception_


def create_project_application(
    project_config: ProjectConfig,
    author_provider: Optional[Callable[[], Author]] = None,
    git_access: Optional[GitAccess] = None,
    send_queue: Optional[SendQueue] = None,
) -> Starlette:
    """
    The web application of a project of the desktop application. Every commit,
    tag and merge takes its author from the function that the application
    gives, and from nowhere else: without that function the committer refuses,
    and the author of GitConfig is never used. With a principal provider in the
    configuration, the user of the server is the one that the function gives.

    The committer exists for every project in a Git repository, whether or not
    the project declares the feature GIT. Its Git commands get the credential
    of git_access and no other: without it, none. No value of the GitConfig of
    the project chooses where the token goes, and the application creates no
    repository and no group on GitLab.

    Every commit goes to the queue that sends it (send_queue). The gate of the
    project, the commit at the end of a write request, the route of the status
    and the indicator of the pages are the ones of the application only: the
    web server has none of them.
    """
    runtime = _get_runtime_of_config(project_config)
    generation = runtime.get_change_generation() if runtime is not None else 0
    application = create_app(project_config=project_config)
    if runtime is not None:
        # The first index of a new server is built from the files as they are
        # now, so the project is no longer behind its files, whatever an
        # earlier server of the same folder left. A build that fails raises
        # before this line and leaves the saves refused.
        runtime.mark_index_built(generation)
    if project_config.principal_provider is not None:
        give_principal_provider(application, project_config.principal_provider)
    give_git_access(
        application,
        project_config,
        git_access if git_access is not None else GitAccess(),
    )
    give_author_provider(
        application,
        author_provider
        if author_provider is not None
        else create_missing_author_provider(),
    )
    give_sending(application, send_queue)
    give_synchronization(
        application,
        git_access if git_access is not None else GitAccess(),
        send_queue,
    )
    give_no_comparison(application)
    return application


def give_principal_provider(
    application: Starlette, principal_provider: PrincipalProvider
) -> None:
    """
    Give the function to the principal middleware of the application. The
    middleware stack is built at the first request, so the arguments of the
    middleware can still be completed here. Raise LocalServerError when it
    cannot be: the server would otherwise run with no user, or with the wrong
    one.
    """
    if application.middleware_stack is not None:
        raise LocalServerError(
            "The middleware of the application is already built: the "
            "principal provider is too late."
        )
    for middleware_ in application.user_middleware:
        if middleware_.cls is PrincipalMiddleware:
            middleware_.kwargs["principal_provider"] = principal_provider
            return
    raise LocalServerError("The application has no principal middleware.")


def give_git_access(
    application: Starlette,
    project_config: ProjectConfig,
    git_access: GitAccess,
) -> None:
    """
    Make the Git commands of the project use the credential of git_access: the
    committer of the project is built again on a DesktopGitService, and a
    project in a Git repository that had no committer gets one (the author is
    given afterwards, by give_author_provider).

    The variable for the token in the GitConfig of the project is set aside
    here too, for a configuration that enable_git did not see.
    """
    context = application.state.project_context
    if project_config.git is not None:
        project_config.git.token_env = NO_GITLAB_TOKEN_VARIABLE
    if project_config.input_paths is None:
        context.git_committer = None
        return
    root = find_project_root(project_config.input_paths[0])
    if root is None:
        context.git_committer = None
        return
    previous = context.git_committer
    context.git_committer = GitCommitter(
        DesktopGitService(root, git_access),
        create_missing_author_provider(),
        use_lfs=previous.use_lfs if previous is not None else False,
        asset_warning_bytes=(
            previous.asset_warning_bytes if previous is not None else 0
        ),
    )


def give_sending(
    application: Starlette, send_queue: Optional[SendQueue]
) -> None:
    """
    Put in the application what shares the changes of the project: the gate
    around the write requests with the commit at their end (the outermost
    middleware), the route of the status (inside the middleware of the
    principal, so that it asks for the same user as every route, and outside
    of the table of the roles), the function that sends each commit to the
    queue, and the indicator of the pages.
    """
    context = application.state.project_context
    committer = context.git_committer
    root: Optional[str] = (
        committer.service.project_root if committer is not None else None
    )
    runtime = get_project_runtime(root) if root is not None else None

    def get_merge_key_of_project() -> str:
        current = context.git_committer
        if current is None or not isinstance(
            current.service, DesktopGitService
        ):
            return ""
        return get_merge_key(current.service, current.service.project_root)

    def get_notice() -> Optional[ProjectStatus]:
        if runtime is None or runtime.sync_notice_state == "":
            return None
        return ProjectStatus(
            SendState(runtime.sync_notice_state),
            message=runtime.sync_notice_text,
        )

    def get_status() -> ProjectStatus:
        current = context.git_committer
        return get_project_status(
            current.last_error if current is not None else "",
            send_queue.get_status(root)
            if send_queue is not None and root is not None
            else None,
            is_index_outdated=(
                runtime.is_index_outdated if runtime is not None else False
            ),
            merge_key=get_merge_key_of_project(),
            notice=get_notice(),
        )

    if committer is not None and send_queue is not None and root is not None:
        committer.after_commit = lambda: send_queue.notify(root)
    principal_index = next(
        (
            index_
            for index_, middleware_ in enumerate(application.user_middleware)
            if middleware_.cls is PrincipalMiddleware
        ),
        -1,
    )
    if runtime is not None:
        _give_runtime_hooks(application, context, runtime)
    application.user_middleware.insert(
        principal_index + 1,
        Middleware(
            ProjectStatusMiddleware, get_status=get_status, runtime=runtime
        ),
    )
    application.add_middleware(
        ProjectGateMiddleware,
        gate=get_project_gate(root) if root is not None else ProjectGate(),
        get_committer=lambda: context.git_committer,
        runtime=runtime,
        is_merge_waiting=lambda: get_merge_key_of_project() != "",
    )
    environment = context.html_templates.jinja_environment().environment
    environment.loader = ChoiceLoader(
        [environment.loader, FileSystemLoader(TEMPLATES_DIR)]
    )
    environment.globals[INDICATOR_GLOBAL] = True
    # The templates of the synchronization (features/git_sync) use the words
    # of the application, and the role that decides, when these are set.
    environment.globals[WORDING_GLOBAL] = True
    environment.globals[RESOLVE_ROLE_GLOBAL] = get_resolve_role()
    install_application_wording(environment)


def give_synchronization(
    application: Starlette,
    git_access: GitAccess,
    send_queue: Optional[SendQueue],
) -> None:
    """
    Put in the application the synchronization of the desktop: its routes take
    the place of the ones of the web server for the update, the choice and the
    abandon of a merge (the same paths), and its role middleware gets the roles
    that permissions.py gives to these routes. A project that is not in a Git
    repository has no synchronization.
    """
    context = application.state.project_context
    committer = context.git_committer
    if committer is None or not isinstance(
        committer.service, DesktopGitService
    ):
        return
    root = committer.service.project_root
    runtime = get_project_runtime(root)
    router = create_sync_routes(
        context=context,
        folder=root,
        git_access=git_access,
        gate=get_project_gate(root),
        runtime=runtime,
        send_queue=send_queue,
    )
    routes = application.router.routes
    known = len(routes)
    router.include_router(
        create_publish_routes(
            context=context,
            folder=root,
            git_access=git_access,
            gate=get_project_gate(root),
            runtime=runtime,
        )
    )
    application.include_router(router)
    # The routes of the application come first: the paths are the ones of
    # the web server, and the first route that matches answers.
    added = routes[known:]
    del routes[known:]
    routes[0:0] = added
    for middleware_ in application.user_middleware:
        if middleware_.cls is RoleMiddleware:
            middleware_.kwargs["role_overrides"] = get_route_role_overrides()


def give_no_comparison(application: Starlette) -> None:
    """
    The comparison of Git revisions (the pages "/diff" and "/diff_result") is
    not offered: the web server answers these paths with its own message when
    the feature is off, and the application answers "not found", as for a page
    that does not exist. The routes come first.

    @relation(SDOC-SRS-1248, scope=function)
    """

    def answer_not_found(request: Request) -> Response:
        del request
        return PlainTextResponse("Not Found", status_code=404)

    application.router.routes[0:0] = [
        Route(path_, answer_not_found, methods=["GET", "HEAD"])
        for path_ in COMPARISON_PATHS
    ]


def give_author_provider(
    application: Starlette, author_provider: Callable[[], Author]
) -> None:
    """
    Make the committer of the project sign the commits with the author that
    the function gives, at the time of each commit. A project that does not
    commit (the feature GIT is off) has no committer and nothing to sign.
    """
    context = application.state.project_context
    if context.git_committer is not None:
        context.git_committer.author_provider = author_provider


def create_desktop_project_config(
    *,
    input_path: str,
    port: Optional[int],
    principal_provider: Optional[PrincipalProvider] = None,
    ai_runtime: Optional[AiRuntime] = None,
) -> ProjectConfig:
    """
    Read the configuration of a project like the "server" command does.

    The HTML output and the cache go to the cache folder of the user, in one
    sub-folder per project, so that the project and the current folder stay
    free of generated files. The "output_dir" and "cache_dir" options of the
    project configuration are ignored in this mode.

    With a principal provider, the server is in the authentication mode
    "desktop": the user of the server is the one that the function gives.

    With the AI runtime, the configuration of the assistant of the project is
    replaced by the one that the AI servers of the user make (ai_settings.py).

    The feature GIT is on for every project, with the GitConfig of the project
    or a default one: the history, the synchronization and the versions work
    in a project that does not declare them. The variable of the token of that
    GitConfig is one that nobody sets (see enable_git).
    """
    full_input_path = os.path.abspath(input_path)
    output_dir = str(get_project_output_dir(full_input_path))
    server_config = ServerCommandConfig(
        debug=False,
        command="desktop",
        input_path=full_input_path,
        output_path=output_dir,
        config=None,
        reload=False,
        host=LOCAL_SERVER_HOST,
        port=port,
        # The documents change under the server when the project is updated
        # from its remote: the server reads them again and tells the pages.
        watch=True,
    )
    project_config = ProjectConfigLoader.load_using_server_config(server_config)
    # The language of a project is not used here: the one of the application
    # stays (see application_language.py).
    restore_application_language()
    project_config.dir_for_sdoc_cache = os.path.join(
        str(get_project_sdoc_cache_dir(full_input_path)), __version__
    )
    use_bundled_pdf_tools(project_config)
    enable_git(project_config)
    disable_comparison(project_config)
    if ai_runtime is not None:
        # The assistant of the project is the one of the AI servers of the user.
        ai_runtime.attach(project_config)
    if principal_provider is not None:
        project_config.enable_desktop_mode(principal_provider)
    return project_config


def use_bundled_pdf_tools(project_config: ProjectConfig) -> None:
    """
    The PDF export uses the headless Chrome and the chromedriver of the
    package, when both are there: nothing is downloaded at run time and the
    browser of the computer is not needed.
    """
    tools = find_bundled_tools()
    if tools.chrome_binary is not None and tools.chromedriver is not None:
        project_config.chrome_binary = str(tools.chrome_binary)
        project_config.chromedriver = str(tools.chromedriver)


def disable_comparison(project_config: ProjectConfig) -> None:
    """
    Turn the feature DIFF off, even when the project declares it: the
    application does not offer the comparison of Git revisions (see
    give_no_comparison). The project file is not changed.

    @relation(SDOC-SRS-1248, scope=function)
    """
    project_config.project_features = [
        feature_
        for feature_ in project_config.project_features
        if feature_ != ProjectFeature.DIFF
    ]


def enable_git(project_config: ProjectConfig) -> None:
    """
    Turn the feature GIT on, with a default GitConfig when the project has
    none. The GitConfig of the project never chooses where the token goes: its
    variable for the token is one that nobody sets, so that no route of the
    project sends a token to the address of the project, or creates a
    repository or a group on GitLab.
    """
    if ProjectFeature.GIT not in project_config.project_features:
        project_config.project_features.append(ProjectFeature.GIT)
    if project_config.git is None:
        project_config.git = GitConfig()
    project_config.git.token_env = NO_GITLAB_TOKEN_VARIABLE


def run_until_stop_signal(on_ready: Callable[[], None]) -> None:
    """
    Call the function, then wait for SIGINT or SIGTERM.

    The handlers are in place before the call, so that a signal sent as soon as
    the caller has been told that the server is ready is not lost.
    """
    stop_event = threading.Event()

    def request_stop(signal_number: int, frame: Optional[FrameType]) -> None:
        del signal_number, frame
        stop_event.set()

    previous_handlers: Dict[int, object] = {}
    signal_numbers: List[int] = [signal.SIGINT, signal.SIGTERM]
    for signal_number_ in signal_numbers:
        previous_handlers[signal_number_] = signal.signal(
            signal_number_, request_stop
        )
    try:
        on_ready()
        # A timeout keeps the wait interruptible on every platform.
        while not stop_event.wait(0.5):
            pass
    finally:
        for signal_number_, handler_ in previous_handlers.items():
            signal.signal(signal_number_, handler_)  # type: ignore[arg-type]


def _give_runtime_hooks(
    application: Starlette, context: Any, runtime: ProjectRuntime
) -> None:
    """
    Tell the runtime of the project what the update needs from this server:
    to build the index again and tell the pages (the function that the watcher
    of the files calls), and to leave to the watcher the files that the update
    changed. A change of the files that comes from outside (an editor of the
    user, another program) raises the revision, so that a form that was opened
    before is not saved. The hooks end with the server.

    The index is outdated from the change of the files until a build of it
    succeeds, and no save passes meanwhile (the gate asks the runtime): a build
    that fails leaves the old index, and a save of it would write the old text
    over the files that the update brought. The revision rises before the
    build and after it, so that no page that was made on the old index has the
    final revision.
    """
    watcher = context.document_watcher
    if watcher is None:
        return
    build_index = context.rebuild_index

    def rebuild_index(lock_manager: Any) -> Optional[str]:
        generation = runtime.get_change_generation()
        build_error: Optional[str] = build_index(lock_manager)
        if build_error is None:
            runtime.mark_index_built(generation)
        else:
            logger.warning(
                "The project was changed and cannot be built: %s", build_error
            )
        runtime.bump_revision()
        return build_error

    context.rebuild_index = rebuild_index
    # The function of the router, that the watcher calls after a change: it
    # builds the index again and tells the pages to reload.
    notify_after_change = watcher._on_documents_changed

    def on_documents_changed() -> None:
        runtime.mark_files_changed()
        runtime.bump_revision()
        notify_after_change()

    watcher._on_documents_changed = on_documents_changed

    def inhibit_change(path: str) -> bool:
        if not watcher.is_watched_document(path):
            return False
        with watcher._lock:
            is_new = os.path.abspath(path) not in watcher._inhibited_paths
        watcher.inhibit_next_change(path)
        return is_new

    def release_change(path: str) -> None:
        if watcher.is_watched_document(path):
            with watcher._lock:
                watcher._inhibited_paths.discard(os.path.abspath(path))

    runtime.rebuild_and_notify = notify_after_change
    runtime.inhibit_change = inhibit_change
    runtime.release_change = release_change
    application.state.desktop_release_hooks = runtime.clear_hooks


def _get_runtime_of_config(
    project_config: ProjectConfig,
) -> Optional[ProjectRuntime]:
    if project_config.input_paths is None:
        return None
    root = find_project_root(project_config.input_paths[0])
    return get_project_runtime(root) if root is not None else None


def _print_no_welcome_message(project_config: ProjectConfig) -> None:
    """
    Replace the banner of "strictdoc server".

    Its "Server URL" is a URL that answers 403 here, because only the bootstrap
    URL gives the session cookie.
    """
    del project_config
