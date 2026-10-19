"""
The option ``kb`` of the assistant: which knowledge base it reads and how.

The address comes only from this configuration, never from a request. The
secret of the service account is named, not written: ``secret_env`` is the NAME
of an environment variable that deploy.sh fills from OpenBao.
"""

import urllib.parse
from dataclasses import dataclass, field
from typing import List, Tuple

from strictdoc.helpers.exception import StrictDocException

# The tools of the knowledge base that only read. A configuration cannot name
# another one.
READ_ONLY_TOOLS: Tuple[str, ...] = (
    "list_missions",
    "search",
    "get_requirement",
    "get_requirement_batch",
    "list_documents",
    "statistics",
    "trace",
    "get_section",
    "get_interface",
    "diff_versions",
    "coverage",
    "glossary",
    "wiki_page",
    "wiki_search",
    "find_references",
)

DEFAULT_TOOLS: Tuple[str, ...] = (
    "search",
    "get_requirement",
    "get_requirement_batch",
    "list_documents",
    "statistics",
    "trace",
    "get_section",
    "get_interface",
    "glossary",
    "wiki_search",
    "find_references",
)

# The commands that look in the base before they ask the model to write.
DEFAULT_COMMANDS: Tuple[str, ...] = ("ask", "req", "verify")

_LOOPBACK = ("127.0.0.1", "localhost", "::1")
# The names that the relays of deploy.sh give on the internal network: the
# base (http, the relay leads to the server) and the token endpoint of Keycloak.
INTERNAL_HOST = "kb.internal"
INTERNAL_TOKEN_HOST = "keycloak-admin"


@dataclass
class KBConfig:
    url: str
    mission: str
    # The address of the token endpoint of Keycloak.
    token_url: str
    client_id: str = "strictdoc-kb"
    secret_env: str = "KB_CLIENT_SECRET"
    # The environment variable that holds the path of the CA bundle.
    ca_bundle_env: str = "KB_CA_BUNDLE"
    tools: List[str] = field(default_factory=lambda: list(DEFAULT_TOOLS))
    commands: List[str] = field(default_factory=lambda: list(DEFAULT_COMMANDS))
    # Rounds of the model in one command, characters kept of one result, and
    # seconds for one call to the base.
    max_steps: int = 6
    max_tool_chars: int = 6000
    timeout: float = 15.0
    # The text that the loop adds to the prompt, in characters.
    max_gathered_chars: int = 9000

    def validate(self) -> None:
        for name_, address, internal_host in (
            ("url", self.url, INTERNAL_HOST),
            ("token_url", self.token_url, INTERNAL_TOKEN_HOST),
        ):
            parsed = urllib.parse.urlparse(address)
            if not parsed.hostname:
                raise StrictDocException(
                    f"config: llm: kb: {name_} must be an address."
                )
            plain_allowed = parsed.scheme == "http" and (
                parsed.hostname in _LOOPBACK or parsed.hostname == internal_host
            )
            if parsed.scheme != "https" and not plain_allowed:
                raise StrictDocException(
                    f"config: llm: kb: {name_} must be https or "
                    f"http://{internal_host}."
                )
        if not self.mission.strip():
            raise StrictDocException("config: llm: kb: mission is empty.")
        if not self.secret_env or not self.client_id:
            raise StrictDocException(
                "config: llm: kb: client_id and secret_env are needed."
            )
        unknown = sorted(set(self.tools) - set(READ_ONLY_TOOLS))
        if unknown:
            raise StrictDocException(
                "config: llm: kb: tools that read nothing or do not exist: "
                + ", ".join(unknown)
                + "."
            )
        if not self.tools:
            raise StrictDocException("config: llm: kb: no tool is allowed.")
        if not 1 <= self.max_steps <= 12:
            raise StrictDocException(
                "config: llm: kb: max_steps is between 1 and 12."
            )
        if self.max_tool_chars < 500 or self.max_gathered_chars < 500:
            raise StrictDocException(
                "config: llm: kb: the limits in characters are too small."
            )
        if self.timeout <= 0:
            raise StrictDocException("config: llm: kb: timeout is positive.")
