"""
Entry point of strictdoc-desktop.exe, the program without a console window.

It runs the command "strictdoc desktop" with the arguments it gets. A program
without a console has no standard output: the file descriptors 1 and 2 are
pointed at the null device, so that the code that prints does not fail.

@relation(SDOC-SRS-1257, scope=file)
"""

import os
import sys


def main() -> None:
    if sys.stdout is None or sys.stderr is None:
        null_descriptor = os.open(os.devnull, os.O_RDWR)
        os.dup2(null_descriptor, 1)
        os.dup2(null_descriptor, 2)
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
        sys.stderr = sys.stdout
    sys.argv = [sys.argv[0], "desktop", *sys.argv[1:]]

    from strictdoc.cli.main import main as strictdoc_main  # noqa: PLC0415

    strictdoc_main()


if __name__ == "__main__":
    main()
