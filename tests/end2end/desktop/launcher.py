"""
The command of the application for the end2end tests that need the rules of
the external AI servers.

The application reads these rules in the places of a deployment only (see
strictdoc/features/desktop/ai_policy.py): no setting, no variable of the
environment and no option of the command gives them. A test needs a file of its
own, so this launcher gives the path to the code of the application, then runs
the command as strictdoc.cli.main does:

    python -m tests.end2end.desktop.launcher --ai-policy PATH desktop ...
"""

import sys
from pathlib import Path

from strictdoc.cli.main import main
from strictdoc.features.desktop.ai_policy import configure_policy_paths

OPTION = "--ai-policy"


def run() -> None:
    arguments = sys.argv[1:]
    if len(arguments) >= 2 and arguments[0] == OPTION:
        configure_policy_paths([Path(arguments[1])])
        sys.argv = [sys.argv[0], *arguments[2:]]
    main()


if __name__ == "__main__":
    run()
