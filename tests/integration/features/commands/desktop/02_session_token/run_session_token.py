"""
Check the session token of "strictdoc desktop --no-window" with HTTP requests.

Usage: run_session_token.py <strictdoc command> <project> <user folder>
"""

import http.client
import os
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from typing import Dict, Optional
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from desktop_process import DesktopProcess  # noqa: E402


def main() -> int:
    strictdoc_command, project_path, user_path = sys.argv[1:4]
    desktop_process = DesktopProcess(
        strictdoc_command=strictdoc_command,
        project_path=project_path,
        user_path=user_path,
    )
    start_url = desktop_process.wait_for_start_url()
    if start_url is None:
        _report("error", "the server did not print its URL")
        return 1
    parts = urlsplit(start_url)
    base_url = f"{parts.scheme}://{parts.netloc}"
    cookie_name = f"strictdoc_desktop_session_{parts.port}"
    _report("Start path", parts.path)

    _report("Home page without cookie", _status(base_url + "/"))
    # The case of a web page of another site that sends a form to the server.
    edit_url = base_url + "/actions/document/update_requirement"
    _report("Edit without cookie", _status(edit_url, b"x=1"))
    _report(
        "Start with a wrong code",
        _status(base_url + parts.path + "?code=x"),
    )

    cookie_jar = CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookie_jar)
    )
    with opener.open(start_url, timeout=60) as response:
        _report("Start with the code", response.status)
    cookies = [cookie_ for cookie_ in cookie_jar if cookie_.name == cookie_name]
    _report("Cookies", len(cookies))
    cookie = cookies[0]
    _report("Cookie name", cookie.name)
    _report("Cookie HttpOnly", cookie.has_nonstandard_attr("HttpOnly"))
    _report("Cookie SameSite", cookie.get_nonstandard_attr("SameSite"))
    _report("Cookie is a session cookie", cookie.expires is None)

    with opener.open(base_url + "/", timeout=60) as response:
        _report("Home page with cookie", response.status)

    _report("Start with the code again", _status(start_url))
    cookie_header = f"{cookie_name}={cookie.value}"
    _report(
        "Wrong Host with cookie",
        _status_with_headers(
            parts.netloc, {"Host": "evil.example", "Cookie": cookie_header}
        ),
    )
    _report(
        "localhost Host with cookie",
        _status_with_headers(
            parts.netloc,
            {"Host": f"localhost:{parts.port}", "Cookie": cookie_header},
        ),
    )

    exit_code = desktop_process.stop()
    _report("Exit code", exit_code)
    _report(
        "Token in the output", str(cookie.value) in desktop_process.get_output()
    )
    return 0


def _report(label: str, value: object) -> None:
    print(f"{label}: {value}")  # noqa: T201


def _status(url: str, data: Optional[bytes] = None) -> int:
    try:
        with urllib.request.urlopen(url, data=data, timeout=60) as response:
            return int(response.status)
    except urllib.error.HTTPError as exception_:
        return exception_.code


def _status_with_headers(netloc: str, headers: Dict[str, str]) -> int:
    connection = http.client.HTTPConnection(netloc, timeout=60)
    try:
        connection.request("GET", "/", headers=headers)
        return connection.getresponse().status
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
