"""
Measures the memory of a StrictDoc server with 1, 2 and 5 projects (plan 5,
step P4): one process, the same document in every project.

    python developer/design/measure_projects_memory.py NODES [COUNT...]

Every project holds one synthetic document of NODES requirements (131 is the
size of REQ_02, 3000 a large project). Prints the resident memory (VmRSS, from /proc) of the server process after it
answered the first request of every project. Linux only.
"""

import http.client
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List

REGISTRY = """from strictdoc.features.projects.registry import ProjectSpec


def create_projects():
    return [
{specs}
    ]
"""


def _free_port() -> int:
    with socket.socket() as sock_:
        sock_.bind(("127.0.0.1", 0))
        return int(sock_.getsockname()[1])


def _get(port: int, host: str, path: str) -> int:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
    connection.request("GET", path, headers={"Host": host})
    status = connection.getresponse().status
    connection.close()
    return status


def _rss_mb(pid: int) -> float:
    with open(f"/proc/{pid}/status", encoding="utf8") as file_:
        for line_ in file_:
            if line_.startswith("VmRSS:"):
                return int(line_.split()[1]) / 1024
    return 0.0


def synthetic_document(nodes: int) -> str:
    lines = ["[DOCUMENT]", "TITLE: Synthetic", ""]
    for number in range(nodes):
        lines += [
            "[REQUIREMENT]",
            f"UID: SYN-{number}",
            f"TITLE: Requirement {number}",
            "STATEMENT: >>>",
            (
                f"The function number {number} shall answer within {number} "
                "ms when the command is received in the nominal mode."
            ),
            "<<<",
            "",
        ]
    return "\n".join(lines)


def measure(nodes: int, count: int) -> float:
    with tempfile.TemporaryDirectory() as root_:
        root = Path(root_)
        specs: List[str] = []
        for number in range(count):
            folder = root / "data" / f"p{number}"
            folder.mkdir(parents=True)
            (folder / "synthetic.sdoc").write_text(
                synthetic_document(nodes), encoding="utf8"
            )
            specs.append(
                f"        ProjectSpec(slug='p{number}', title='P{number}',"
                f" path='data/p{number}'),"
            )
        (root / "projects.py").write_text(
            REGISTRY.format(specs="\n".join(specs)), encoding="utf8"
        )
        port = _free_port()
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "strictdoc.cli.main",
                "server",
                "--projects",
                str(root / "projects.py"),
                "--root-host",
                "m.test",
                "--output-path",
                str(root / "output"),
                "--port",
                str(port),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.time() + 600
            while time.time() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("The server stopped at start.")
                try:
                    if _get(port, "m.test", "/healthz") == 200:
                        break
                except OSError:
                    time.sleep(0.5)
            for number in range(count):
                _get(port, f"p{number}.m.test", f"/p{number}/synthetic.html")
            return _rss_mb(process.pid)
        finally:
            process.terminate()
            process.wait(timeout=30)


if __name__ == "__main__":
    nodes_ = int(sys.argv[1])
    counts = [int(arg_) for arg_ in sys.argv[2:]] or [1, 2, 5]
    for count_ in counts:
        sys.stdout.write(
            f"{count_} project(s) of {nodes_} nodes: "
            f"{measure(nodes_, count_):.0f} MB\n"
        )
        sys.stdout.flush()
    assert os.name == "posix"
