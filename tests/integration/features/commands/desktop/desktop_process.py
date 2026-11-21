"""
A "strictdoc desktop --no-window" process for the integration tests.
"""

import os
import shlex
import signal
import subprocess
import threading
from typing import List, Optional

SERVER_LINE_PREFIX = "StrictDoc desktop server: "
STARTUP_TIMEOUT_SECONDS = 120.0
STOP_TIMEOUT_SECONDS = 60.0


class DesktopProcess:
    """
    The folders of the user (configuration, cache and data) are inside the
    given folder, so that nothing is written in the real folders of the user.
    """

    def __init__(
        self, *, strictdoc_command: str, project_path: str, user_path: str
    ) -> None:
        environment = dict(os.environ)
        environment["XDG_CACHE_HOME"] = os.path.join(user_path, "cache")
        environment["XDG_CONFIG_HOME"] = os.path.join(user_path, "config")
        environment["XDG_DATA_HOME"] = os.path.join(user_path, "data")
        self._lines: List[str] = []
        self._start_url: Optional[str] = None
        self._url_printed = threading.Event()
        self._process = subprocess.Popen(
            shlex.split(strictdoc_command)
            + ["desktop", "--no-window", project_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
        )
        self._reader = threading.Thread(target=self._read_lines, daemon=True)
        self._reader.start()

    def wait_for_start_url(self) -> Optional[str]:
        """The bootstrap URL, or None when the server does not print it."""
        if not self._url_printed.wait(STARTUP_TIMEOUT_SECONDS):
            self._process.kill()
            return None
        return self._start_url

    def stop(self) -> int:
        """Send SIGINT and return the exit code, or 1 when it does not stop."""
        self._process.send_signal(signal.SIGINT)
        try:
            exit_code = self._process.wait(STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            self._process.kill()
            return 1
        self._reader.join(STOP_TIMEOUT_SECONDS)
        return exit_code

    def get_output(self) -> str:
        return "".join(self._lines)

    def _read_lines(self) -> None:
        assert self._process.stdout is not None
        for line_ in self._process.stdout:
            self._lines.append(line_)
            if line_.startswith(SERVER_LINE_PREFIX):
                self._start_url = line_[len(SERVER_LINE_PREFIX) :].strip()
                self._url_printed.set()
        # The process ended: wake up a caller that waits for the URL.
        self._url_printed.set()
