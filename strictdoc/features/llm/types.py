"""Requests, responses and errors of the language model providers."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, Tuple


class LLMError(Exception):
    """A provider cannot answer (network, timeout, refusal, bad status)."""


@dataclass(frozen=True)
class ToolCall:
    """A tool that the model asks to run."""

    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass(frozen=True)
class Message:
    """
    A turn that follows the first user prompt, for a conversation with tools.
    role: "assistant" (text and the tools it asked for) or "tool" (the result
    of the tool `tool_call_id`).
    """

    role: str
    content: str = ""
    tool_calls: Tuple[ToolCall, ...] = ()
    tool_call_id: str = ""


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
    # Tools the model may ask for: {"name", "description", "input_schema"}.
    # None: the model answers in one turn, as before.
    tools: Optional[Tuple[Dict[str, Any], ...]] = None
    # The turns after the user prompt (only with tools).
    messages: Tuple[Message, ...] = ()


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str = ""
    tool_calls: Tuple[ToolCall, ...] = ()
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
