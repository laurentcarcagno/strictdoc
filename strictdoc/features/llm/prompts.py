"""
The versioned prompt templates (prompts/*.md) and their reading.

A template file starts with "version: N" and has sections introduced by a
line "---NAME---": the system prompt and one pattern per kind of requirement.
The version is recorded on every node that a draft creates.
"""

import os
import re
from dataclasses import dataclass
from typing import Dict

PROMPT_DIR = os.path.join(os.path.dirname(__file__), "prompts")
_SECTION = re.compile(r"^---([A-Za-z0-9:_-]+)---\s*$", re.MULTILINE)
TEMPLATE_NAME = "draft"
PATTERNS = (
    "free",
    "ubiquitous",
    "event-driven",
    "state-driven",
    "unwanted-behaviour",
    "optional-feature",
)


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    version: int
    system: str
    patterns: Dict[str, str]

    @property
    def label(self) -> str:
        return f"{self.name}@{self.version}"


def load_template(name: str = TEMPLATE_NAME) -> PromptTemplate:
    path = os.path.join(PROMPT_DIR, f"{name}.md")
    with open(path, encoding="utf-8") as file_:
        text = file_.read()
    first_line, _, rest = text.partition("\n")
    match = re.fullmatch(r"version:\s*(\d+)", first_line.strip())
    if match is None:
        raise ValueError(f"{path}: the first line must be 'version: N'.")
    parts = _SECTION.split(rest)
    # The split alternates: text before, then (name, body) pairs.
    sections = {
        parts[index_].strip(): parts[index_ + 1].strip()
        for index_ in range(1, len(parts) - 1, 2)
    }
    if "SYSTEM" not in sections:
        raise ValueError(f"{path}: no SYSTEM section.")
    patterns = {
        key_.partition(":")[2]: value_
        for key_, value_ in sections.items()
        if key_.startswith("PATTERN:")
    }
    missing = [name_ for name_ in PATTERNS if name_ not in patterns]
    if missing:
        raise ValueError(f"{path}: no pattern for {', '.join(missing)}.")
    return PromptTemplate(
        name=name,
        version=int(match.group(1)),
        system=sections["SYSTEM"],
        patterns=patterns,
    )


@dataclass(frozen=True)
class AssistPrompt:
    """The system prompt of one command of the assistant bar."""

    name: str
    version: int
    system: str

    @property
    def label(self) -> str:
        return f"{self.name}@{self.version}"


def _read_versioned(name: str) -> "tuple[int, str]":
    path = os.path.join(PROMPT_DIR, f"{name}.md")
    with open(path, encoding="utf-8") as file_:
        text = file_.read()
    first_line, _, rest = text.partition("\n")
    match = re.fullmatch(r"version:\s*(\d+)", first_line.strip())
    if match is None:
        raise ValueError(f"{path}: the first line must be 'version: N'.")
    return int(match.group(1)), rest.strip()


def load_assist_prompt(name: str) -> AssistPrompt:
    """
    The prompt of a command: the shared part (common.md) followed by the
    part of the command (<name>.md). The version recorded is the one of the
    command file.
    """
    _, common = _read_versioned("common")
    version, body = _read_versioned(name)
    return AssistPrompt(
        name=name, version=version, system=common + "\n\n" + body
    )
