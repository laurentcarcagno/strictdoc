"""
A "strictdoc desktop --no-window" process for the end2end tests.

It follows SDocTestServer: the same port choice, the same log files in the
temporary folder, the same wait for the start of uvicorn and the same stop,
which the context manager runs also when the test fails. It differs by the
command, and because the user of the application is a temporary one: its
settings, cache and data folders are in a temporary folder, and its settings
name a catalog read from a JSON file.

@relation(SDOC-SRS-1229, scope=file)
@relation(SDOC-SRS-1234, scope=file)
@relation(SDOC-SRS-1235, scope=file)
"""

import os
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from strictdoc.features.desktop.settings import DesktopSettings, save_settings
from tests.end2end.conftest import test_environment
from tests.end2end.server import ReadTimeout, SDocTestServer

# The keyring of the system is not used by the tests: the application finds a
# stand-in for the "keyring" package that keeps its secrets in a file of the
# temporary user folder.
STUB_KEYRING_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "stub_keyring"
)
KEYRING_FILE_VARIABLE = "STRICTDOC_TEST_KEYRING_FILE"
START_URL_PREFIX = "StrictDoc desktop server: "
APPLICATION_NAME = "StrictDoc"


class DesktopTestServer(SDocTestServer):
    def __init__(
        self,
        *,
        input_path: str,
        fake_catalog_path: Optional[str] = None,
        project_path: Optional[str] = None,
        language: Optional[str] = None,
        user_path: Optional[str] = None,
        kept_servers: Optional[int] = None,
        gitlab_url: Optional[str] = None,
        oauth_client_id: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        super().__init__(input_path=input_path, port=port)
        self.language: Optional[str] = language
        self.kept_servers: Optional[int] = kept_servers
        self.project_path: Optional[str] = project_path
        self.fake_catalog_path: Optional[str] = fake_catalog_path
        # The GitLab of the sign-in and the identifier of its OAuth
        # application: the settings that make the sign-in available.
        self.gitlab_url: Optional[str] = gitlab_url
        self.oauth_client_id: Optional[str] = oauth_client_id
        # The folders of the user. Without a given folder, run() creates a
        # temporary one that close() removes. A test that starts the
        # application twice gives the same folder to both runs: the second run
        # finds what the first one remembered.
        self.user_path: Optional[str] = user_path

    def run(self) -> None:
        if self.user_path is None:
            user_folder = tempfile.TemporaryDirectory()
            self.exit_stack.enter_context(user_folder)
            self.user_path = user_folder.name
        if self.fake_catalog_path is not None and not os.path.exists(
            self.get_settings_path()
        ):
            defaults = DesktopSettings()
            save_settings(
                DesktopSettings(
                    catalog_provider="fake",
                    fake_catalog_path=self.fake_catalog_path,
                    kept_servers=self.kept_servers
                    if self.kept_servers is not None
                    else defaults.kept_servers,
                    gitlab_url=self.gitlab_url
                    if self.gitlab_url is not None
                    else defaults.gitlab_url,
                    oauth_client_id=self.oauth_client_id
                    if self.oauth_client_id is not None
                    else defaults.oauth_client_id,
                ),
                # The path that platformdirs gives under XDG_CONFIG_HOME.
                path=Path(self.get_settings_path()),
            )
        super().run()

    def close(self, *, exit_due_exception: Optional[Exception]) -> None:
        # SDocTestServer.close() expects that the process started. When the
        # test fails before, only the temporary folders are left to remove,
        # and the error that stopped the start must not be hidden.
        if self.process is None:
            self.exit_stack.close()
            return
        super().close(exit_due_exception=exit_due_exception)

    def get_settings_path(self) -> str:
        assert self.user_path is not None
        return os.path.join(
            self.user_path, "config", APPLICATION_NAME, "settings.json"
        )

    def get_keyring_path(self) -> str:
        assert self.user_path is not None
        return os.path.join(self.user_path, "keyring.json")

    def get_home_url(self) -> str:
        """
        The home page, for a browser that has followed the start URL: it has
        the session cookie. It is what the menu "Projects" of the window opens.
        """
        parts = urlsplit(self.get_start_url())
        return f"{parts.scheme}://{parts.netloc}/"

    def get_start_url(self) -> str:
        """
        The URL that the window would open: it gives the session cookie, once,
        then redirects to the home page.
        """
        deadline = time.monotonic() + test_environment.wait_timeout_seconds
        while True:
            with open(self.path_to_out_log, encoding="utf-8") as file_:
                for line_ in file_:
                    if line_.startswith(START_URL_PREFIX):
                        return line_[len(START_URL_PREFIX) :].strip()
            if time.monotonic() >= deadline:
                raise ReadTimeout(float(test_environment.wait_timeout_seconds))
            time.sleep(test_environment.poll_timeout_seconds)

    def _get_strictdoc_command(self) -> Tuple[List[str], Dict[str, str]]:
        # The command of the web server, with the interpreter and the coverage
        # options of the other end2end tests, up to the name of the command.
        server_arguments, strictdoc_env = super()._get_strictdoc_command()
        command_index = server_arguments.index("server")
        strictdoc_arguments = server_arguments[:command_index] + [
            "desktop",
            "--no-window",
            "--port",
            str(self.server_port),
        ]
        if self.project_path is not None:
            strictdoc_arguments.append(self.project_path)
        assert self.user_path is not None
        strictdoc_env["XDG_CONFIG_HOME"] = os.path.join(
            self.user_path, "config"
        )
        strictdoc_env["XDG_CACHE_HOME"] = os.path.join(self.user_path, "cache")
        strictdoc_env["XDG_DATA_HOME"] = os.path.join(self.user_path, "data")
        strictdoc_env["PYTHONPATH"] = os.pathsep.join(
            [STUB_KEYRING_PATH, strictdoc_env["PYTHONPATH"]]
        )
        strictdoc_env[KEYRING_FILE_VARIABLE] = self.get_keyring_path()
        if self.language is not None:
            strictdoc_env["STRICTDOC_LANGUAGE"] = self.language
        return strictdoc_arguments, strictdoc_env
