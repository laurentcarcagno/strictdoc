import json

import pytest

from strictdoc.features.llm.anthropic import AnthropicProvider
from strictdoc.features.llm.config import Anthropic
from strictdoc.features.llm.types import LLMError, LLMRequest
from tests.unit.strictdoc.features.llm.test_openai_compatible import (
    _json,
    _Server,
    server,  # noqa: F401  (a pytest fixture)
)


def _message(handler):
    _json(
        handler,
        200,
        {
            "model": "claude-test",
            "content": [
                {"type": "text", "text": "thinking aloud"},
                {
                    "type": "tool_use",
                    "name": "submit_proposals",
                    "input": {"proposals": [{"title": "t", "statement": "s"}]},
                },
            ],
            "usage": {"input_tokens": 20, "output_tokens": 8},
        },
    )


def _provider(srv, key="sk-secret"):
    return AnthropicProvider(
        "claude",
        Anthropic(model="claude-test", api_key_env="K", base_url=srv.url),
        environment={"K": key} if key else {},
    )


def test_001_the_request_uses_the_messages_api_and_a_forced_tool(server):  # noqa: F811
    srv = server(_message)
    schema = {"type": "object", "properties": {"proposals": {"type": "array"}}}
    response = _provider(srv).complete(
        LLMRequest(system="sys", user="usr", schema=schema, max_tokens=99)
    )
    path, raw_headers, body = srv.requests[0]
    headers = {k.lower(): v for k, v in raw_headers.items()}
    assert path == "/v1/messages"
    assert headers["x-api-key"] == "sk-secret"
    assert headers["anthropic-version"] == "2023-06-01"
    assert "authorization" not in headers
    assert body["model"] == "claude-test" and body["max_tokens"] == 99
    assert body["system"] == "sys"
    assert body["messages"] == [{"role": "user", "content": "usr"}]
    assert body["tools"][0]["input_schema"] == schema
    assert body["tool_choice"] == {"type": "tool", "name": "submit_proposals"}
    assert json.loads(response.text) == {
        "proposals": [{"title": "t", "statement": "s"}]
    }
    assert (response.input_tokens, response.output_tokens) == (20, 8)


def test_002_without_a_schema_the_text_block_is_the_answer(server):  # noqa: F811
    srv = server(
        lambda handler: _json(
            handler,
            200,
            {"content": [{"type": "text", "text": "hello"}], "usage": {}},
        )
    )
    response = _provider(srv).complete(LLMRequest(system="s", user="u"))
    assert response.text == "hello"
    assert "tools" not in srv.requests[0][2]


def test_003_a_missing_key_is_reported_without_a_call(server):  # noqa: F811
    srv = server(_message)
    with pytest.raises(LLMError, match="K"):
        _provider(srv, key="").complete(LLMRequest(system="s", user="u"))
    assert srv.requests == []


def test_004_an_error_never_echoes_the_key(server):  # noqa: F811
    srv = server(
        lambda handler: _json(handler, 401, {"error": "bad sk-secret"})
    )
    with pytest.raises(LLMError) as raised:
        _provider(srv).complete(LLMRequest(system="s", user="u"))
    assert "HTTP 401" in str(raised.value) and "sk-secret" not in str(
        raised.value
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"content": "x"},
        {"content": []},
        {"content": [{"type": "text", "text": ""}]},
    ],
)
def test_005_an_answer_without_text_is_reported(server, payload):  # noqa: F811
    srv = server(lambda handler: _json(handler, 200, payload))
    with pytest.raises(LLMError):
        _provider(srv).complete(LLMRequest(system="s", user="u"))


def test_006_it_is_a_cloud_provider():
    assert AnthropicProvider.is_local is False
    assert _Server  # the helper module is shared with the other client tests
