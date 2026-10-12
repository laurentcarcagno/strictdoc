"""
What the administrators change while the server runs: the projects they have
created and the members of every project. One JSON file, written atomically,
next to the registry file (the registry file lists the projects that a
deployment defines; this file lists the others and the members of all).

    {"projects": {"revalto": {"title": "...", "created_by": "ann", "created": "..."}},
     "members": {"revalto": {"ann": "administrator", "bob": "author"}}}

A member is a user name as the login proxy reports it (lower case), with a
role of roles.py. The groups of the login server give roles too; the highest
of the two applies.
"""

import json
import os
import re
import tempfile
import threading
from typing import Dict, List, Optional

from strictdoc.features.i18n.i18n import gettext
from strictdoc.features.roles.roles import ROLES
from strictdoc.helpers.exception import StrictDocException

USER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._@+-]{0,62}$")


def clean_user(name: str) -> str:
    """The canonical form of a user name. Raises StrictDocException."""
    user = name.strip().lower()
    if USER_PATTERN.match(user) is None:
        raise StrictDocException(
            gettext(
                "Invalid user name '%(name)s': use letters, digits and "
                ". _ @ + -."
            )
            % {"name": name}
        )
    return user


class ProjectStore:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.RLock()

    # -- reading ------------------------------------------------------------

    def _load(self) -> Dict[str, Dict[str, Dict[str, object]]]:
        try:
            with open(self.path, encoding="utf8") as file_:
                data = json.load(file_)
        except FileNotFoundError:
            data = {}
        except (OSError, ValueError) as exception_:
            raise StrictDocException(
                f"The project store {self.path} cannot be read: {exception_}."
            ) from exception_
        data.setdefault("projects", {})
        data.setdefault("members", {})
        return data  # type: ignore[no-any-return]

    def projects(self) -> Dict[str, Dict[str, str]]:
        with self._lock:
            return dict(self._load()["projects"])  # type: ignore[arg-type]

    def members(self, slug: str) -> Dict[str, str]:
        with self._lock:
            found = self._load()["members"].get(slug, {})
            return {user_: str(role_) for user_, role_ in found.items()}

    def role_of(self, slug: str, user: str) -> Optional[str]:
        return self.members(slug).get(user.strip().lower())

    def slugs_of(self, user: str) -> List[str]:
        """The projects in which the user is a member."""
        name = user.strip().lower()
        with self._lock:
            return [
                slug_
                for slug_, members_ in self._load()["members"].items()
                if name in members_
            ]

    # -- writing ------------------------------------------------------------

    def _save(self, data: Dict[str, Dict[str, Dict[str, object]]]) -> None:
        folder = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(folder, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=folder, suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf8") as file_:
                json.dump(data, file_, indent=2, sort_keys=True)
            os.replace(temporary, self.path)
        except BaseException:
            if os.path.exists(temporary):
                os.unlink(temporary)
            raise

    def add_project(
        self, slug: str, title: str, created_by: str, created: str
    ) -> None:
        with self._lock:
            data = self._load()
            data["projects"][slug] = {
                "title": title,
                "created_by": created_by,
                "created": created,
            }
            self._save(data)

    def set_member(self, slug: str, user: str, role: str) -> None:
        if role not in ROLES:
            raise StrictDocException(
                f"'{role}' is not a role. Use one of {', '.join(ROLES)}."
            )
        name = clean_user(user)
        with self._lock:
            data = self._load()
            data["members"].setdefault(slug, {})[name] = role
            self._save(data)

    def remove_member(self, slug: str, user: str) -> bool:
        name = user.strip().lower()
        with self._lock:
            data = self._load()
            members = data["members"].get(slug, {})
            if name not in members:
                return False
            del members[name]
            self._save(data)
            return True
