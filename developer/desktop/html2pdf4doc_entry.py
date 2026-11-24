"""
Entry point of the frozen html2pdf4doc program of the desktop package.

The PDF export starts "html2pdf4doc" by its name. A frozen application has no
such program on its PATH, so the package carries this one in
tools/html2pdf4doc/.

On Windows the program is built without a console: the application has no
console either, and a program with one would open a window at each export.
Without a console it has no standard output, so the file descriptors 1 and 2
are pointed at the null device. The programs that it starts (chromedriver,
and Chrome for its version) are console programs too, and selenium starts
them with no flag: every subprocess gets the flag CREATE_NO_WINDOW.

@relation(SDOC-SRS-1258, scope=file)
"""

import os
import subprocess
import sys
from typing import Any

CREATE_NO_WINDOW = 0x08000000


def prepare_without_console() -> None:
    if sys.stdout is None or sys.stderr is None:
        null_descriptor = os.open(os.devnull, os.O_RDWR)
        os.dup2(null_descriptor, 1)
        os.dup2(null_descriptor, 2)
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
        sys.stderr = sys.stdout


def hide_subprocess_windows(popen_class: Any) -> None:
    """Add the flag CREATE_NO_WINDOW to every program that is started."""
    original_init = popen_class.__init__

    def init(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs["creationflags"] = (
            kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
        )
        original_init(self, *args, **kwargs)

    popen_class.__init__ = init


def main() -> int:
    prepare_without_console()
    if sys.platform == "win32":
        hide_subprocess_windows(subprocess.Popen)

    from html2pdf4doc.main import main as html2pdf4doc_main  # noqa: PLC0415

    return int(html2pdf4doc_main() or 0)


if __name__ == "__main__":
    sys.exit(main())
