"""
Who is acting: the identity that the web server reads from the headers that
oauth2-proxy adds to every request it forwards.

oauth2-proxy replaces these headers with the values of the logged-in user, so
a client cannot forge them through the proxy. The server still trusts them
only from the networks listed in the project option ``trusted_proxies``
(see middleware.py).

What oauth2-proxy sends (checked on the deployed proxy, plan 1 step R1):

- ``X-Forwarded-User``: the identifier of the user in Keycloak (a UUID).
- ``X-Forwarded-Preferred-Username``: the user name ("laurent.carcagno").
- ``X-Forwarded-Email``.
- ``X-Forwarded-Groups``: the groups and the realm roles of the user, comma
  separated; roles are prefixed with "role:".

The ``X-Auth-Request-*`` headers are never read: the proxy does not replace
them when a client sends them.
"""

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

HEADER_SUBJECT = "x-forwarded-user"
HEADER_USERNAME = "x-forwarded-preferred-username"
HEADER_EMAIL = "x-forwarded-email"
HEADER_GROUPS = "x-forwarded-groups"

_ROLE_PREFIX = "role:"

ANONYMOUS_USER = "anonymous"


@dataclass(frozen=True)
class Principal:
    # The name shown to people and written in logs.
    user: str
    # The stable identifier of the user (does not change when the name does).
    subject: str = ""
    email: str = ""
    groups: Tuple[str, ...] = ()
    # False for the anonymous principal of the "none" authentication mode.
    authenticated: bool = True

    @staticmethod
    def anonymous() -> "Principal":
        return Principal(user=ANONYMOUS_USER, authenticated=False)


def groups_from_header(value: str) -> Tuple[str, ...]:
    """The groups of an X-Forwarded-Groups value, without the realm roles."""
    groups = []
    for item_ in value.split(","):
        group = item_.strip()
        if len(group) > 0 and not group.startswith(_ROLE_PREFIX):
            groups.append(group)
    return tuple(groups)


def principal_from_headers(headers: Mapping[str, str]) -> Optional[Principal]:
    """
    The principal that the headers describe, or None when they do not
    identify a user. The header names are lower case.
    """
    subject = headers.get(HEADER_SUBJECT, "").strip()
    username = headers.get(HEADER_USERNAME, "").strip()
    email = headers.get(HEADER_EMAIL, "").strip()
    user = username or email or subject
    if len(user) == 0:
        return None
    return Principal(
        user=user,
        subject=subject,
        email=email,
        groups=groups_from_header(headers.get(HEADER_GROUPS, "")),
    )
