import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from strictdoc.features.llm.config import OpenAICompatible
from strictdoc.features.llm.openai_compatible import OpenAICompatibleProvider
from strictdoc.features.llm.types import LLMError, LLMRequest


class _Server:
    def __init__(self, handler):
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                outer.requests.append(
                    (
                        self.path,
                        dict(self.headers),
                        json.loads(self.rfile.read(length)),
                    )
                )
                handler(self)

            def log_message(self, *args):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, daemon=True
        )
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _json(handler, status, payload):
    body = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _ok(handler):
    _json(
        handler,
        200,
        {
            "model": "m1",
            "choices": [{"message": {"role": "assistant", "content": "hello"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3},
        },
    )


@pytest.fixture
def server():
    servers = []

    def make(handler=_ok):
        server = _Server(handler)
        servers.append(server)
        return server

    yield make
    for server_ in servers:
        server_.close()


def _provider(server, **kwargs):
    return OpenAICompatibleProvider(
        "local",
        OpenAICompatible(
            base_url=server.url + "/v1", model="m1", is_local=True, **kwargs
        ),
        environment={"KEY": "sekret"},
    )


def test_001_the_request_follows_the_chat_completions_protocol(server):
    srv = server()
    provider = _provider(srv)
    schema = {"type": "object"}
    response = provider.complete(
        LLMRequest(
            system="sys",
            user="usr",
            schema=schema,
            max_tokens=50,
            temperature=0.1,
        )
    )
    path, _, body = srv.requests[0]
    assert path == "/v1/chat/completions"
    assert body["model"] == "m1"
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]
    assert body["max_tokens"] == 50 and body["temperature"] == 0.1
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == schema
    assert response.text == "hello" and response.model == "m1"
    assert (response.input_tokens, response.output_tokens) == (12, 3)


def test_002_without_a_schema_no_response_format_is_sent(server):
    srv = server()
    _provider(srv).complete(LLMRequest(system="s", user="u"))
    assert "response_format" not in srv.requests[0][2]


def test_003_the_key_is_sent_only_when_the_config_names_one(server):
    srv = server()
    _provider(srv).complete(LLMRequest(system="s", user="u"))
    assert "Authorization" not in srv.requests[0][1]
    srv2 = server()
    _provider(srv2, api_key_env="KEY").complete(
        LLMRequest(system="s", user="u")
    )
    assert srv2.requests[0][1]["Authorization"] == "Bearer sekret"


def test_004_a_named_key_that_is_not_set_is_reported_without_a_call(server):
    srv = server()
    provider = OpenAICompatibleProvider(
        "cloud",
        OpenAICompatible(base_url=srv.url, model="m", api_key_env="NOPE"),
        environment={},
    )
    with pytest.raises(LLMError, match="NOPE"):
        provider.complete(LLMRequest(system="s", user="u"))
    assert srv.requests == []


def test_005_an_error_status_is_reported_and_never_echoes_the_key(server):
    def refuse(handler):
        _json(handler, 401, {"error": "bad key sekret"})

    srv = server(refuse)
    provider = _provider(srv, api_key_env="KEY")
    with pytest.raises(LLMError) as raised:
        provider.complete(LLMRequest(system="s", user="u"))
    assert "HTTP 401" in str(raised.value)
    assert "sekret" not in str(raised.value)


def test_006_a_redirect_is_not_followed(server):
    target = server()

    def redirect(handler):
        handler.send_response(307)
        handler.send_header("Location", target.url + "/steal")
        handler.send_header("Content-Length", "0")
        handler.end_headers()

    srv = server(redirect)
    with pytest.raises(LLMError, match="HTTP 307"):
        _provider(srv, api_key_env="KEY").complete(
            LLMRequest(system="s", user="u")
        )
    assert target.requests == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": ""}}]},
    ],
)
def test_007_an_answer_that_is_not_a_completion_is_reported(server, payload):
    srv = server(lambda handler: _json(handler, 200, payload))
    with pytest.raises(LLMError, match="chat completion|no text"):
        _provider(srv).complete(LLMRequest(system="s", user="u"))


def test_008_a_slow_server_gives_a_timeout_error(server):
    def slow(handler):
        time.sleep(1.5)
        _ok(handler)

    srv = server(slow)
    with pytest.raises(LLMError, match="cannot be reached"):
        _provider(srv).complete(LLMRequest(system="s", user="u", timeout=0.3))


def test_009_a_server_that_is_down_gives_an_error():
    provider = OpenAICompatibleProvider(
        "local",
        OpenAICompatible(
            base_url="http://127.0.0.1:9/v1", model="m", is_local=True
        ),
        environment={},
    )
    with pytest.raises(LLMError, match="cannot be reached"):
        provider.complete(LLMRequest(system="s", user="u", timeout=2))


def test_010_the_token_counts_are_optional(server):
    srv = server(
        lambda handler: _json(
            handler, 200, {"choices": [{"message": {"content": "x"}}]}
        )
    )
    response = _provider(srv).complete(LLMRequest(system="s", user="u"))
    assert response.input_tokens is None and response.output_tokens is None
