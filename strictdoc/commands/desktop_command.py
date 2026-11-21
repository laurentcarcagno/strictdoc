"""
@relation(SDOC-SRS-1220, scope=file)
@relation(SDOC-SRS-1221, scope=file)
@relation(SDOC-SRS-1229, scope=file)
"""

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from strictdoc.cli.argument_int_range import IntRange
from strictdoc.cli.base_command import BaseCommand, CLIValidationError
from strictdoc.commands.desktop_config import DesktopCommandConfig
from strictdoc.helpers.parallelizer import Parallelizer

if TYPE_CHECKING:
    from strictdoc.features.desktop.local_server import LocalServer

HOME_WINDOW_TITLE = "StrictDoc"


class DesktopCommand(BaseCommand):
    HELP = "Open StrictDoc in a desktop window."
    DETAILED_HELP = (
        HELP + " With the path of a project, the window shows that project."
        " Without a path, it shows the catalog of the projects."
        " The web server listens on 127.0.0.1 only and stops when the window"
        " is closed."
    )

    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "input_path",
            nargs="?",
            default=None,
            help="Path to a project. Without it, the home screen is shown.",
        )
        parser.add_argument(
            "--no-window",
            default=False,
            action="store_true",
            help=(
                "Run the server without a window: print its URL, then wait "
                "for SIGINT or SIGTERM."
            ),
        )
        parser.add_argument(
            "--port",
            type=IntRange(1024, 65000),
            help="Port of the server. By default, a free port is used.",
        )

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.config: DesktopCommandConfig = DesktopCommandConfig(**vars(args))

    def run(self, parallelizer: Parallelizer) -> None:  # noqa: ARG002
        self.config.validate()
        # The feature needs the optional platformdirs package. The command
        # stays registered when the package is missing.
        try:
            from strictdoc.features.desktop import (  # noqa: PLC0415
                home_app as home_app_module,
            )
            from strictdoc.features.desktop import (  # noqa: PLC0415
                home_server as home_server_module,
            )
            from strictdoc.features.desktop import (  # noqa: PLC0415
                local_server as local_server_module,
            )
            from strictdoc.features.desktop import (  # noqa: PLC0415
                paths as paths_module,
            )
        except ImportError as exception_:
            if exception_.name != "platformdirs":
                raise
            raise CLIValidationError(
                "The desktop application needs the 'platformdirs' package. "
                "Install it with: pip install platformdirs."
            ) from exception_

        if not self.config.no_window:
            # Before the server starts, which takes time: fail at once when
            # there is no window to show.
            self._check_window_available()

        local_server: LocalServer
        if self.config.input_path is None:
            try:
                home_app_module.set_language_from_environment()
            except ValueError as exception_:
                raise CLIValidationError(
                    f"STRICTDOC_LANGUAGE: {exception_}"
                ) from exception_
            title = HOME_WINDOW_TITLE
            local_server = home_server_module.create_home_server(
                port=self.config.port
            )
        else:
            project_config = local_server_module.create_desktop_project_config(
                input_path=self.config.get_full_input_path(),
                port=self.config.port,
            )
            title = f"StrictDoc - {project_config.project_title}"
            local_server = local_server_module.LocalServer(
                project_config=project_config, port=self.config.port
            )
        local_server.start()
        try:
            local_server.wait_until_ready()
            if self.config.no_window:

                def print_url() -> None:
                    print(  # noqa: T201
                        f"StrictDoc desktop server: {local_server.start_url}",
                        flush=True,
                    )

                local_server_module.run_until_stop_signal(print_url)
            else:
                self._run_window(
                    title=title,
                    url=local_server.start_url,
                    storage_path=paths_module.get_data_dir() / "webview",
                )
        finally:
            local_server.stop()

    @staticmethod
    def _check_window_available() -> None:
        from strictdoc.features.desktop import window  # noqa: PLC0415

        try:
            window.check_window_available()
        except window.DesktopWindowError as exception_:
            raise CLIValidationError(str(exception_)) from exception_

    @staticmethod
    def _run_window(*, title: str, url: str, storage_path: Path) -> None:
        from strictdoc.features.desktop import window  # noqa: PLC0415

        window.run_window(title=title, url=url, storage_path=storage_path)
