"""
Run "strictdoc desktop --no-window" on a project and stop it with SIGINT.

Usage: run_no_window.py <strictdoc command> <project> <user folder>
"""

import os
import sys
import urllib.request
from http.cookiejar import CookieJar
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from desktop_process import DesktopProcess  # noqa: E402


def main() -> int:
    strictdoc_command, project_path, user_path = sys.argv[1:4]
    working_path = os.getcwd()
    entries_before = sorted(os.listdir(working_path))

    desktop_process = DesktopProcess(
        strictdoc_command=strictdoc_command,
        project_path=project_path,
        user_path=user_path,
    )
    start_url = desktop_process.wait_for_start_url()
    if start_url is None:
        print("error: the server did not print its URL")  # noqa: T201
        return 1
    is_loopback = start_url.startswith("http://127.0.0.1:")
    print(f"URL is on the loopback address: {is_loopback}")  # noqa: T201

    # The bootstrap URL gives the cookie and redirects to the home page.
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )
    with opener.open(start_url, timeout=60) as response:
        print(f"Status of the home page: {response.status}")  # noqa: T201

    exit_code = desktop_process.stop()
    print(f"Exit code: {exit_code}")  # noqa: T201

    project_entries = sorted(os.listdir(project_path))
    print(f"Project folder: {project_entries}")  # noqa: T201
    print(  # noqa: T201
        "Current folder unchanged: "
        f"{sorted(os.listdir(working_path)) == entries_before}"
    )
    projects_path = os.path.join(user_path, "cache", "StrictDoc", "projects")
    output_paths: List[str] = [
        os.path.join(projects_path, fingerprint_, "output")
        for fingerprint_ in os.listdir(projects_path)
    ]
    print(  # noqa: T201
        "Output in the cache of the user: "
        f"{len(output_paths) == 1 and os.path.isdir(output_paths[0])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
