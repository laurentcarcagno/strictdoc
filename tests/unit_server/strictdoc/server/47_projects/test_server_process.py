import http.client
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from tests.support.projects_fixture import make_specs

REGISTRY = """from strictdoc.features.projects.registry import ProjectSpec


def create_projects():
    return [
        ProjectSpec(slug="alpha", title="Alpha program", path="data/alpha"),
        ProjectSpec(slug="beta", title="Beta program", path="data/beta"),
    ]
"""


def _free_port() -> int:
    with socket.socket() as sock_:
        sock_.bind(("127.0.0.1", 0))
        return int(sock_.getsockname()[1])


def _get(port: int, host: str, path: str, project: str = ""):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Host": host}
    if project:
        # The current project of a browser is a cookie.
        headers["Cookie"] = f"sdoc_project={project}"
    connection.request("GET", path, headers=headers)
    response = connection.getresponse()
    body = response.read().decode("utf8", "replace")
    connection.close()
    return response.status, body


def test_001_the_command_serves_the_projects_of_a_registry(tmp_path):
    make_specs(tmp_path)
    (tmp_path / "projects.py").write_text(REGISTRY, encoding="utf8")
    port = _free_port()
    environment = {
        key_: value_
        for key_, value_ in os.environ.items()
        if not key_.startswith("STRICTDOC_")
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "strictdoc.cli.main",
            "server",
            "--projects",
            str(tmp_path / "projects.py"),
            "--root-host",
            "strictdoc.test",
            "--data-root",
            str(tmp_path / "data"),
            "--output-path",
            str(tmp_path / "output"),
            "--port",
            str(port),
        ],
        cwd=str(Path(__file__).parents[4]),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.time() + 90
        status = 0
        while time.time() < deadline:
            if process.poll() is not None:
                break
            try:
                status, _ = _get(port, "strictdoc.test", "/healthz")
                if status == 200:
                    break
            except OSError:
                time.sleep(0.5)
        output = b""
        if status != 200:
            process.terminate()
            output = process.communicate(timeout=20)[0]
        assert status == 200, output.decode("utf8", "replace")[-3000:]

        status, page = _get(port, "strictdoc.test", "/_projects")
        assert (
            status == 200 and "Alpha program" in page and "Beta program" in page
        )
        status, page = _get(
            port, "strictdoc.test", "/alpha/alpha_doc.html", "alpha"
        )
        assert (
            status == 200 and "Alpha spec" in page and "Beta spec" not in page
        )
        status, page = _get(
            port, "strictdoc.test", "/beta/beta_doc.html", "beta"
        )
        assert (
            status == 200 and "Beta spec" in page and "Alpha spec" not in page
        )
        status, page = _get(port, "gamma.strictdoc.test", "/_projects")
        assert (status, page) == (404, "Not found")
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
