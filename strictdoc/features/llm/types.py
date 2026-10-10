"""Requests, responses and errors of the language model providers."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol


class LLMError(Exception):
    """A provider cannot answer (network, timeout, refusal, bad status)."""


@dataclass(frozen=True)
class LLMRequest:
    system: str
    user: str
    # A JSON schema that the answer must follow. Providers pass it on when
    # they can; the answer is validated in any case.
    schema: Optional[Dict[str, Any]] = None
    max_tokens: int = 2000
    temperature: float = 0.2
    # Seconds before the call is given up.
    timeout: float = 120.0


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str = ""
    # None when the provider does not say.
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class LLMProvider(Protocol):
    name: str
    model: str
    # True when the data stay on the network (a model that runs here).
    is_local: bool

    def complete(self, request: LLMRequest) -> LLMResponse: ...


@dataclass
class CallRecord:
    """What a provider was asked, for the tests and the audit."""

    request: LLMRequest
    response: Optional[LLMResponse] = None
    error: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)
