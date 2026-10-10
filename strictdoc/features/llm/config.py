"""
The project option ``llm``: which providers exist and what the project allows.

Secrets are named, never written: ``api_key_env`` is the NAME of an environment
variable (given to the container by deploy.sh from OpenBao). The address of a
provider comes only from this configuration, never from a request.
"""

import urllib.parse
from dataclasses import dataclass, field
from typing import Dict, List, Union

from strictdoc.helpers.exception import StrictDocException


@dataclass
class OpenAICompatible:
    """A server that speaks the chat-completions protocol (Ollama, OpenAI, ...)."""

    base_url: str
    model: str
    # True for a model that runs on this network: its data do not leave it.
    is_local: bool = False
    api_key_env: str = ""
    timeout: float = 120.0


@dataclass
class Anthropic:
    """The Messages API of Anthropic. Always a cloud provider."""

    model: str
    api_key_env: str
    base_url: str = "https://api.anthropic.com"
    timeout: float = 120.0
    is_local: bool = field(default=False, init=False)


@dataclass
class Fake:
    """A provider that answers from a list (tests and demonstrations only)."""

    answers: List[str]
    model: str = "fake-model"
    is_local: bool = True
    base_url: str = "http://fake.invalid"
    timeout: float = 1.0


ProviderConfig = Union[OpenAICompatible, Anthropic, Fake]


@dataclass
class LLMConfig:
    default: str = "local"
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    # Cloud providers are closed unless the project opens them.
    allow_cloud: bool = False
    # A node or document with one of these classifications never goes to a
    # cloud provider.
    cloud_blocked_classifications: List[str] = field(default_factory=list)
    # Keep the text of the prompts in the audit log (default: only a hash).
    audit_store_prompts: bool = False
    # Tokens per calendar month for the cloud providers; 0 means no limit.
    cloud_token_budget_per_month: int = 0
    # Requests per user and minute.
    rate_limit_per_minute: int = 10
    # The verification methods of the project (for REQ_02: T, A, R, I).
    verification_methods: List[str] = field(default_factory=list)
    # The longest context sent to a model, in characters.
    max_context_chars: int = 12000
    # The field of the requirement that holds the verification method (for
    # REQ_02: VERIFIED_BY). Empty: the method is not stored.
    verification_field: str = ""

    def validate(self) -> None:
        if len(self.providers) == 0:
            raise StrictDocException("config: llm: no provider is declared.")
        if self.default not in self.providers:
            raise StrictDocException(
                f"config: llm: the default provider '{self.default}' is not "
                f"declared ({', '.join(sorted(self.providers))})."
            )
        for name_, provider_ in self.providers.items():
            if not name_.replace("-", "").replace("_", "").isalnum():
                raise StrictDocException(
                    f"config: llm: invalid provider name '{name_}'."
                )
            url = urllib.parse.urlparse(provider_.base_url)
            if url.scheme not in ("http", "https") or not url.hostname:
                raise StrictDocException(
                    f"config: llm: provider '{name_}': base_url must be an "
                    "http or https address."
                )
            if not provider_.model:
                raise StrictDocException(
                    f"config: llm: provider '{name_}' has no model."
                )
            if not provider_.is_local and url.scheme != "https":
                raise StrictDocException(
                    f"config: llm: provider '{name_}' is not local: its "
                    "address must be https."
                )
            if isinstance(provider_, Anthropic) and not provider_.api_key_env:
                raise StrictDocException(
                    f"config: llm: provider '{name_}' needs api_key_env."
                )
        if not self.providers[self.default].is_local and not self.allow_cloud:
            raise StrictDocException(
                f"config: llm: the default provider '{self.default}' is a "
                "cloud provider but allow_cloud is false."
            )
        if self.cloud_token_budget_per_month < 0:
            raise StrictDocException(
                "config: llm: cloud_token_budget_per_month cannot be negative."
            )
        if self.rate_limit_per_minute < 1:
            raise StrictDocException(
                "config: llm: rate_limit_per_minute must be at least 1."
            )

    def is_cloud(self, provider_name: str) -> bool:
        return not self.providers[provider_name].is_local
