"""
The rules of the external AI servers, in the desktop application: the
classifications that never go to such a server, and the budget of tokens of a
month.

The rules come from a file that is deployed with the application and that the
user cannot change, in a folder of the system: /etc/strictdoc on Linux, the
folder StrictDoc of ProgramData on Windows. The file is read nowhere else: not
next to the executable (the installer of a user puts the program in a folder
that the user can write), not in the settings of the user, not in a variable of
the environment, not in the project. A file that is missing or that cannot be
read means no rule that could be trusted: no external server is used, and the
screen of the settings says so.

The file is a JSON object:

    {
      "version": 1,
      "cloud_blocked_classifications": ["Secret", "Restricted"],
      "cloud_token_budget_per_month": 200000
    }

The budget is in tokens, for the user, all the projects together (0: none).

The tests give the paths to the code of the application
(configure_policy_paths), not to an environment variable.

@relation(SDOC-SRS-1255, scope=file)
"""

import json
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional, Sequence

from strictdoc.features.i18n.i18n import gettext

POLICY_FILE_NAME = "ai_policy.json"
MAXIMUM_POLICY_BYTES = 64 * 1024
MAXIMUM_CLASSIFICATIONS = 100
MAXIMUM_CLASSIFICATION_LENGTH = 100
POLICY_VERSION = 1

_configured_paths: Optional[List[Path]] = None


class PolicyState(str, Enum):
    VALID = "valid"
    # No file in any place: no rule at all.
    ABSENT = "absent"
    INVALID = "invalid"


@dataclass(frozen=True)
class AiPolicy:
    state: PolicyState
    blocked_classifications: List[str] = field(default_factory=list)
    monthly_token_budget: int = 0
    # The file that was read, for the log.
    path: str = ""

    @property
    def is_valid(self) -> bool:
        return self.state is PolicyState.VALID


def configure_policy_paths(paths: Optional[Sequence[Path]]) -> None:
    """
    Give the places of the file, in the code of the application. A test of the
    application does it before the servers start; nothing else does. None gives
    the places of a deployment again.
    """
    global _configured_paths  # noqa: PLW0603
    _configured_paths = list(paths) if paths is not None else None


def get_policy_paths() -> List[Path]:
    """The places where the file is looked for, the first one first."""
    if _configured_paths is not None:
        return list(_configured_paths)
    return [_get_system_folder() / POLICY_FILE_NAME]


def load_ai_policy(paths: Optional[Sequence[Path]] = None) -> AiPolicy:
    """
    Read the rules. The first file that exists is the one: if it is invalid,
    the rules are invalid, and a file of another place does not take its
    place.
    """
    for path_ in paths if paths is not None else get_policy_paths():
        if path_.is_file():
            return _read_policy(path_)
    return AiPolicy(PolicyState.ABSENT)


def get_policy_message(policy: AiPolicy) -> str:
    """What the screen says about a policy that is not valid, "" otherwise."""
    if policy.state is PolicyState.ABSENT:
        return gettext(
            "The rules for external servers are not installed: no external "
            "server is used. Ask your administrator."
        )
    if policy.state is PolicyState.INVALID:
        return gettext(
            "The rules for external servers cannot be read: no external "
            "server is used. Ask your administrator."
        )
    return ""


def _get_system_folder() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(base) / "StrictDoc"
    return Path("/etc/strictdoc")


def _read_policy(path: Path) -> AiPolicy:
    invalid = AiPolicy(PolicyState.INVALID, path=str(path))
    try:
        if path.stat().st_size > MAXIMUM_POLICY_BYTES:
            return invalid
        content: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return invalid
    if (
        not isinstance(content, dict)
        or content.get("version") != POLICY_VERSION
    ):
        return invalid
    blocked = content.get("cloud_blocked_classifications", [])
    budget = content.get("cloud_token_budget_per_month", 0)
    if (
        not isinstance(blocked, list)
        or len(blocked) > MAXIMUM_CLASSIFICATIONS
        or any(
            not isinstance(name_, str)
            or len(name_.strip()) == 0
            or len(name_) > MAXIMUM_CLASSIFICATION_LENGTH
            for name_ in blocked
        )
        or not isinstance(budget, int)
        or isinstance(budget, bool)
        or budget < 0
    ):
        return invalid
    return AiPolicy(
        PolicyState.VALID,
        blocked_classifications=[name_.strip() for name_ in blocked],
        monthly_token_budget=budget,
        path=str(path),
    )
