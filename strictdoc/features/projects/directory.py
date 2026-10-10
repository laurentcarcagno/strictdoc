"""
The list of the users of the login server (Keycloak), for the members page of
a project: the administrator picks real accounts instead of typing names.

The server asks the administration API of Keycloak with a service account of its
own (the client ``strictdoc-directory``, which has the role ``view-users`` of the
realm and nothing else). The secret of that client comes from the environment
(``STRICTDOC_KEYCLOAK_CLIENT_SECRET``, a Podman secret in a deployment), never from
a file. Only the user name, the display name and the e-mail are read.

Only administrators of a project see the list (the members page is theirs).
When Keycloak does not answer, the page still works: the name is typed by hand.
"""

import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

PAGE_SIZE = 200
# More than this is not a team tool: stop reading.
MAX_USERS = 5000


class DirectoryError(Exception):
    """The directory could not be read."""


@dataclass(frozen=True)
class DirectoryUser:
    username: str
    name: str
    email: str

    def label(self) -> str:
        details = " ".join(part_ for part_ in (self.name, self.email) if part_)
        return details


class KeycloakDirectory:
    def __init__(
        self,
        *,
        base_url: str,
        realm: str,
        client_id: str,
        client_secret: str,
        ca_file: Optional[str] = None,
        ttl: float = 300.0,
        timeout: float = 5.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._realm = realm
        self._client_id = client_id
        self._client_secret = client_secret
        self._ttl = ttl
        self._timeout = timeout
        self._context = (
            ssl.create_default_context(cafile=ca_file) if ca_file else None
        )
        self._lock = threading.Lock()
        self._token: Optional[str] = None
        self._token_expires = 0.0
        self._users: List[DirectoryUser] = []
        self._users_expire = 0.0

    # -- HTTP ---------------------------------------------------------------

    def _request(
        self,
        url: str,
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        request = urllib.request.Request(url, data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(  # noqa: S310 (url from the deployment)
                request, timeout=self._timeout, context=self._context
            ) as response:
                return json.loads(response.read().decode("utf8"))
        except (urllib.error.URLError, OSError, ValueError) as exception_:
            raise DirectoryError(f"Keycloak: {exception_}") from exception_

    def _bearer(self) -> str:
        if self._token is not None and time.monotonic() < self._token_expires:
            return self._token
        answer = self._request(
            f"{self._base_url}/realms/{self._realm}"
            "/protocol/openid-connect/token",
            data=urllib.parse.urlencode(
                {
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                }
            ).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token = answer.get("access_token") if isinstance(answer, dict) else None
        if not isinstance(token, str):
            raise DirectoryError("Keycloak gave no access token.")
        self._token = token
        self._token_expires = time.monotonic() + max(
            float(answer.get("expires_in", 60)) - 30.0, 5.0
        )
        return token

    # -- users --------------------------------------------------------------

    def _read_users(self) -> List[DirectoryUser]:
        headers = {"Authorization": f"Bearer {self._bearer()}"}
        users: List[DirectoryUser] = []
        first = 0
        while first < MAX_USERS:
            page = self._request(
                f"{self._base_url}/admin/realms/{self._realm}/users"
                f"?first={first}&max={PAGE_SIZE}&briefRepresentation=true",
                headers=headers,
            )
            if not isinstance(page, list):
                raise DirectoryError("Keycloak gave no list of users.")
            for item_ in page:
                username = str(item_.get("username", "")).strip().lower()
                if len(username) == 0 or item_.get("enabled") is False:
                    continue
                name = " ".join(
                    str(item_.get(key_, "")).strip()
                    for key_ in ("firstName", "lastName")
                ).strip()
                users.append(
                    DirectoryUser(
                        username=username,
                        name=name,
                        email=str(item_.get("email", "")).strip(),
                    )
                )
            if len(page) < PAGE_SIZE:
                break
            first += PAGE_SIZE
        return sorted(users, key=lambda user_: user_.username)

    def users(self) -> List[DirectoryUser]:
        """The enabled users, cached. Raises DirectoryError."""
        with self._lock:
            if time.monotonic() >= self._users_expire:
                try:
                    self._users = self._read_users()
                except DirectoryError:
                    # A stale token may be the cause: ask for a new one next time.
                    self._token = None
                    raise
                self._users_expire = time.monotonic() + self._ttl
            return list(self._users)

    def has(self, username: str) -> bool:
        name = username.strip().lower()
        return any(user_.username == name for user_ in self.users())


def directory_from_environment() -> Optional[KeycloakDirectory]:
    """The directory that the deployment configures, or None."""
    base_url = os.environ.get("STRICTDOC_KEYCLOAK_URL")
    secret = os.environ.get("STRICTDOC_KEYCLOAK_CLIENT_SECRET")
    if not base_url or not secret:
        return None
    return KeycloakDirectory(
        base_url=base_url,
        realm=os.environ.get("STRICTDOC_KEYCLOAK_REALM", "infra"),
        client_id=os.environ.get(
            "STRICTDOC_KEYCLOAK_CLIENT_ID", "strictdoc-directory"
        ),
        client_secret=secret,
        ca_file=os.environ.get("STRICTDOC_KEYCLOAK_CA") or None,
    )
