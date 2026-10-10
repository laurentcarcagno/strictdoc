"""
The four roles and the mapping from groups to roles.

A role includes the ones below it: reader, reviewer, author, administrator.
"""

from typing import Dict, List, Mapping, Optional, Sequence

ROLE_READER = "reader"
ROLE_REVIEWER = "reviewer"
ROLE_AUTHOR = "author"
ROLE_ADMINISTRATOR = "administrator"

# From the lowest to the highest.
ROLES = (ROLE_READER, ROLE_REVIEWER, ROLE_AUTHOR, ROLE_ADMINISTRATOR)


def role_rank(role: str) -> int:
    return ROLES.index(role)


def role_allows(role: Optional[str], required: str) -> bool:
    """True if a user with this role may do what the required role may."""
    return role is not None and role_rank(role) >= role_rank(required)


def validate_roles(
    mapping: Mapping[str, Sequence[str]],
) -> Dict[str, List[str]]:
    """
    The role mapping as a clean dictionary. Raises ValueError when a key is
    not a role, a value is not a list of group names, or a group is given
    to more than one role.
    """
    clean: Dict[str, List[str]] = {}
    seen: Dict[str, str] = {}
    for role_, groups_ in mapping.items():
        if role_ not in ROLES:
            raise ValueError(
                f"'{role_}' is not a role. Use one of {', '.join(ROLES)}."
            )
        if isinstance(groups_, str) or not all(
            isinstance(group_, str) and len(group_) > 0 for group_ in groups_
        ):
            raise ValueError(
                f"The groups of '{role_}' must be a list of names."
            )
        for group_ in groups_:
            if group_ in seen and seen[group_] != role_:
                raise ValueError(
                    f"The group '{group_}' is given to both '{seen[group_]}' "
                    f"and '{role_}'."
                )
            seen[group_] = role_
        clean[role_] = list(groups_)
    return clean


def resolve_role(
    groups: Sequence[str], mapping: Mapping[str, Sequence[str]]
) -> Optional[str]:
    """The highest role that one of the groups gives, or None."""
    best: Optional[str] = None
    for role_ in ROLES:
        if any(group_ in mapping.get(role_, ()) for group_ in groups):
            best = role_
    return best
