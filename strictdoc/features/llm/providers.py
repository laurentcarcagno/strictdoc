"""The provider of a configured name."""

from typing import Dict, Optional

from strictdoc.features.llm.anthropic import AnthropicProvider
from strictdoc.features.llm.config import (
    Anthropic,
    Fake,
    LLMConfig,
    OpenAICompatible,
)
from strictdoc.features.llm.fake import FakeProvider
from strictdoc.features.llm.openai_compatible import OpenAICompatibleProvider
from strictdoc.features.llm.types import LLMProvider


def create_provider(
    name: str,
    llm: LLMConfig,
    environment: Optional[Dict[str, str]] = None,
) -> LLMProvider:
    """The provider `name` of the configuration. KeyError: it is not declared."""
    config = llm.providers[name]
    if isinstance(config, OpenAICompatible):
        return OpenAICompatibleProvider(name, config, environment)
    if isinstance(config, Anthropic):
        return AnthropicProvider(name, config, environment)
    if isinstance(config, Fake):
        return FakeProvider(
            list(config.answers),
            name=name,
            model=config.model,
            is_local=config.is_local,
        )
    raise TypeError(f"Unknown provider configuration for '{name}'.")
