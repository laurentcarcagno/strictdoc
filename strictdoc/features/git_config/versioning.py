"""
Version tags of a document: A1, A2 (drafts), A (major), B1, ...

A tag is letters followed by an optional number. One letter goes from A to Z;
after Z come ZA ... ZZ, then ZZA ..., so a tag never repeats and the order is
(length of the letters, letters, number). A major tag (no number) is above the
drafts of its letter. Tags that do not follow the format are ignored.
"""

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

TAG_PATTERN = re.compile(r"^([A-Z]+)([1-9][0-9]*)?$")


class InvalidVersionTag(ValueError):
    pass


class NoMajorVersionToTag(ValueError):
    pass


@dataclass(frozen=True)
class VersionTag:
    letters: str
    number: Optional[int]

    @property
    def name(self) -> str:
        if self.number is None:
            return self.letters
        return f"{self.letters}{self.number}"

    @property
    def sort_key(self) -> Tuple[int, str, int]:
        # A major is above its drafts.
        number = self.number if self.number is not None else 10**9
        return (len(self.letters), self.letters, number)


def parse_version_tag(tag: str) -> VersionTag:
    match = TAG_PATTERN.match(tag)
    if match is None:
        raise InvalidVersionTag(f"Not a version tag: {tag!r}")
    number = match.group(2)
    return VersionTag(match.group(1), int(number) if number else None)


def next_letters(letters: str) -> str:
    """A -> B, Y -> Z, Z -> ZA, ZY -> ZZ, ZZ -> ZZA."""
    if letters[-1] == "Z":
        return letters + "A"
    return letters[:-1] + chr(ord(letters[-1]) + 1)


def _valid_tags(tags: Iterable[str]) -> List[VersionTag]:
    valid = []
    for tag in tags:
        try:
            valid.append(parse_version_tag(tag))
        except InvalidVersionTag:
            continue
    return valid


def _latest(tags: Iterable[str]) -> Optional[VersionTag]:
    valid = _valid_tags(tags)
    if len(valid) == 0:
        return None
    return max(valid, key=lambda tag: tag.sort_key)


def next_intermediate_tag(tags: Iterable[str]) -> str:
    latest = _latest(tags)
    if latest is None:
        return "A1"
    if latest.number is None:
        return f"{next_letters(latest.letters)}1"
    return f"{latest.letters}{latest.number + 1}"


def next_major_tag(tags: Iterable[str]) -> str:
    latest = _latest(tags)
    if latest is None or latest.number is None:
        raise NoMajorVersionToTag(
            "A major version needs an intermediate version to freeze."
        )
    return latest.letters


def latest_valid_tag(tags: Iterable[str]) -> str:
    """The latest version tag, or an empty string if there is none."""
    latest = _latest(tags)
    return "" if latest is None else latest.name
