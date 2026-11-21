"""
The web server of a project for the desktop application.

@relation(SDOC-SRS-1220, scope=file)
@relation(SDOC-SRS-1221, scope=file)
@relation(SDOC-SRS-1222, scope=file)
@relation(SDOC-SRS-1225, scope=file)
@relation(SDOC-SRS-1229, scope=file)
"""

import asyncio
import os
import signal
import socket
import threading
import time
from types import FrameType
from typing import Callable, Dict, List, Optional

import uvicorn
from starlette.applications import Starlette

import strictdoc.server.app as server_app
from strictdoc import __version__
from strictdoc.commands.server_config import ServerCommandConfig
from strictdoc.core.project_config import ProjectConfig, ProjectConfigLoader
from strictdoc.features.desktop.paths import (
    get_project_output_dir,
    get_project_sdoc_cache_dir,
)
from strictdoc.features.desktop.session_token import (
    BOOTSTRAP_CODE_PARAMETER,
    BOOTSTRAP_PATH,
    DesktopSessionMiddleware,
    SessionCredentials,
)
from strictdoc.server.app import create_app

# The host cannot be set: only the program on this computer reaches the server.
LOCAL_SERVER_HOST = "127.0.0.1"

_POLL_INTERVAL_SECONDS = 0.05


class LocalServerError(Exception):
    pass


def _print_no_welcome_message(project_config: ProjectConfig) -> None:
    """
    Replace the banner of "strictdoc server".

    Its "Server URL" is a URL that answers 403 here, because only the bootstrap
    URL gives the session cookie.
    """
    del project_config


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
    ) -> None:
        assert (project_config is None) != (application_factory is None), (
            "Give the project configuration or the application factory."
        )
        self._project_config: Optional[ProjectConfig] = project_config
        self._application_factory: Optional[Callable[[], Starlette]] = (
            application_factory
        )
        self._requested_port: Optional[int] = port
        self._socket: Optional[socket.socket] = None
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
    def start_url(self) -> str:
        """
        The URL that the window opens: it gives the session cookie to the
        window, once, and redirects to the home page.
        """
        return (
            f"{self.url}{BOOTSTRAP_PATH}"
            f"?{BOOTSTRAP_CODE_PARAMETER}={self._credentials.bootstrap_code}"
        )

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
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def _create_application(self) -> Starlette:
        if self._application_factory is not None:
            return self._application_factory()
        assert self._project_config is not None
        self._project_config.server_host = LOCAL_SERVER_HOST
        self._project_config.server_port = self.port
        # create_app starts the banner from its lifespan, which looks the
        # function up in the module when the server starts.
        server_app.print_welcome_message = _print_no_welcome_message
        return create_app(project_config=self._project_config)

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


def create_desktop_project_config(
    *, input_path: str, port: Optional[int]
) -> ProjectConfig:
    """
    Read the configuration of a project like the "server" command does.

    The HTML output and the cache go to the cache folder of the user, in one
    sub-folder per project, so that the project and the current folder stay
    free of generated files. The "output_dir" and "cache_dir" options of the
    project configuration are ignored in this mode.
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
    )
    project_config = ProjectConfigLoader.load_using_server_config(server_config)
    project_config.dir_for_sdoc_cache = os.path.join(
        str(get_project_sdoc_cache_dir(full_input_path)), __version__
    )
    return project_config


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
