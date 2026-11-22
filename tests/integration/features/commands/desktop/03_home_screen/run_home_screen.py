"""
Check the home screen of "strictdoc desktop --no-window" without a project.

The settings of the user are the defaults: the catalog provider is GitLab, and
the address of GitLab and the OAuth application are not given, so the page
shows a message that the settings are incomplete, and no catalog.

Usage: run_home_screen.py <strictdoc command> <user folder>
"""

import os
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from desktop_process import DesktopProcess  # noqa: E402


def main() -> int:
    strictdoc_command, user_path = sys.argv[1:3]
    desktop_process = DesktopProcess(
        strictdoc_command=strictdoc_command,
        project_path=None,
        user_path=user_path,
    )
    start_url = desktop_process.wait_for_start_url()
    if start_url is None:
        _report("error", "the server did not print its URL")
        return 1
    parts = urlsplit(start_url)
    base_url = f"{parts.scheme}://{parts.netloc}"

    _report("Home page without cookie", _status(base_url + "/"))

    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )
    with opener.open(start_url, timeout=60) as response:
        _report("Start with the code", response.status)
    with opener.open(base_url + "/", timeout=60) as response:
        _report("Home page with cookie", response.status)
        page = response.read().decode("utf-8")
    _report(
        "Welcome message on the first launch",
        'data-testid="home-welcome"' in page,
    )
    _report(
        "Settings message shown in the page",
        'data-testid="catalog-settings-incomplete"' in page,
    )
    _report("Python trace in the page", "Traceback" in page)

    _report("Exit code", desktop_process.stop())
    return 0


def _report(label: str, value: object) -> None:
    print(f"{label}: {value}")  # noqa: T201


def _status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return int(response.status)
    except urllib.error.HTTPError as exception_:
        return exception_.code


if __name__ == "__main__":
    sys.exit(main())
