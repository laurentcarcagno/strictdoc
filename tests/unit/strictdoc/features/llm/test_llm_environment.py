"""
The keys that the program holds itself: LLMConfig.environment (D-26).
"""

from types import SimpleNamespace

import pytest

from strictdoc.features.llm.assist.service import AssistService
from strictdoc.features.llm.config import Anthropic, LLMConfig, OpenAICompatible
from strictdoc.features.llm.providers import create_provider

KEY = "sk-held-by-the-program"


def _get_key(provider: object) -> str:
    return str(provider._key)  # type: ignore[attr-defined]  # noqa: SLF001


def _config(**fields: object) -> LLMConfig:
    return LLMConfig(
        default="local",
        providers={
            "local": OpenAICompatible(
                base_url="http://127.0.0.1:11434/v1",
                model="m",
                is_local=True,
                api_key_env="MY_KEY",
            ),
            "claude": Anthropic(model="c", api_key_env="MY_CLAUDE_KEY"),
        },
        **fields,  # type: ignore[arg-type]
    )


def test_001_without_it_the_key_is_read_from_the_environment_of_the_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MY_KEY", KEY)
    llm = _config()

    provider = create_provider("local", llm, llm.environment)

    assert llm.environment is None
    assert _get_key(provider) == KEY


def test_002_with_it_the_key_comes_from_it_and_not_from_the_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MY_KEY", raising=False)
    monkeypatch.delenv("MY_CLAUDE_KEY", raising=False)
    llm = _config(environment={"MY_KEY": KEY, "MY_CLAUDE_KEY": "sk-claude"})

    local = create_provider("local", llm, llm.environment)
    claude = create_provider("claude", llm, llm.environment)

    assert _get_key(local) == KEY
    assert _get_key(claude) == "sk-claude"


def test_003_a_key_that_is_not_in_it_is_not_taken_from_the_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MY_KEY", "from-the-process")
    llm = _config(environment={})

    provider = create_provider("local", llm, llm.environment)

    assert _get_key(provider) == ""


def test_004_the_keys_are_not_in_the_representation_of_the_configuration() -> (
    None
):
    llm = _config(environment={"MY_KEY": KEY})

    assert KEY not in repr(llm)
    assert KEY not in str(llm)
    assert "environment" not in repr(llm)


def test_005_the_assistant_gives_the_environment_to_its_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MY_KEY", raising=False)
    llm = _config(environment={"MY_KEY": KEY})
    service = SimpleNamespace(llm=llm)

    provider = AssistService.provider(
        service,  # type: ignore[arg-type]
        "local",
    )

    assert _get_key(provider) == KEY
