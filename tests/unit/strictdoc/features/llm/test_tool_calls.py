import json

from strictdoc.features.llm.anthropic import AnthropicProvider
from strictdoc.features.llm.config import Anthropic, OpenAICompatible
from strictdoc.features.llm.openai_compatible import (
    OpenAICompatibleProvider,
    _message,
)
from strictdoc.features.llm.types import LLMRequest, Message, ToolCall

TOOLS = (
    {"name": "search", "description": "d", "input_schema": {"type": "object"}},
)


def test_001_openai_reads_the_tool_calls_and_empty_text_is_fine():
    provider = OpenAICompatibleProvider(
        "local", OpenAICompatible("http://x/v1", "m", True)
    )
    raw = json.dumps(
        {
            "model": "m",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c1",
                                "type": "function",
                                "function": {
                                    "name": "search",
                                    "arguments": '{"query": "a"}',
                                },
                            },
                            {
                                "id": "c2",
                                "type": "function",
                                "function": {"name": "bad", "arguments": "[1]"},
                            },
                        ],
                    }
                }
            ],
        }
    ).encode()
    response = provider._parse(raw)
    assert response.tool_calls == (ToolCall("c1", "search", {"query": "a"}),)


def test_002_openai_sends_tools_and_the_turns():
    sent = {}

    def post(**kwargs):
        sent.update(kwargs["body"])
        return json.dumps(
            {"choices": [{"message": {"content": "ok"}}]}
        ).encode()

    import strictdoc.features.llm.openai_compatible as module

    original = module.post_json
    module.post_json = post
    try:
        provider = OpenAICompatibleProvider(
            "local", OpenAICompatible("http://x/v1", "m", True)
        )
        provider.complete(
            LLMRequest(
                system="s",
                user="u",
                tools=TOOLS,
                messages=(
                    Message(
                        "assistant",
                        tool_calls=(ToolCall("c1", "search", {"q": 1}),),
                    ),
                    Message("tool", "result", tool_call_id="c1"),
                ),
            )
        )
    finally:
        module.post_json = original
    assert sent["tools"][0]["function"]["name"] == "search"
    assert "response_format" not in sent
    roles = [m["role"] for m in sent["messages"]]
    assert roles == ["system", "user", "assistant", "tool"]
    assert (
        sent["messages"][2]["tool_calls"][0]["function"]["arguments"]
        == '{"q": 1}'
    )
    assert sent["messages"][3]["tool_call_id"] == "c1"
    assert _message(Message("tool", "x", tool_call_id="c"))["content"] == "x"


def test_003_anthropic_reads_tool_use_and_groups_the_results():
    provider = AnthropicProvider("cloud", Anthropic("m", "K"), {"K": "key"})
    raw = json.dumps(
        {
            "model": "m",
            "content": [
                {"type": "text", "text": "Let me look."},
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "search",
                    "input": {"query": "a"},
                },
            ],
        }
    ).encode()
    response = provider._parse(raw, with_tools=True)
    assert (
        response.text == "Let me look."
        and response.tool_calls[0].name == "search"
    )
    from strictdoc.features.llm.anthropic import _messages

    turns = _messages(
        (
            Message(
                "assistant",
                "x",
                (ToolCall("t1", "search", {}), ToolCall("t2", "search", {})),
            ),
            Message("tool", "r1", tool_call_id="t1"),
            Message("tool", "r2", tool_call_id="t2"),
        )
    )
    assert [t["role"] for t in turns] == ["assistant", "user"]
    assert [b["tool_use_id"] for b in turns[1]["content"]] == ["t1", "t2"]


def test_004_without_tools_nothing_changes():
    provider = OpenAICompatibleProvider(
        "local", OpenAICompatible("http://x/v1", "m", True)
    )
    response = provider._parse(
        json.dumps({"choices": [{"message": {"content": "hi"}}]}).encode()
    )
    assert response.text == "hi" and response.tool_calls == ()
