import json
import time
import urllib.parse

import pytest

from strictdoc.features.kb.client import KBClient, KBError
from tests.support.kb_fixture import CITATION, make_kb_config


class Server:
    """Records the requests and answers like the token endpoint and the MCP server."""

    def __init__(self, expires_in=3600, is_error=False, status_error=None):
        self.requests = []
        self.expires_in = expires_in
        self.is_error = is_error
        self.status_error = status_error

    def __call__(self, request, timeout):
        self.requests.append(request)
        if request.full_url.endswith("/token"):
            return json.dumps(
                {
                    "access_token": f"tok{len(self.requests)}",
                    "expires_in": self.expires_in,
                }
            ).encode()
        if self.status_error:
            raise KBError(f"The base answered HTTP {self.status_error}.")
        message = json.loads(request.data)
        if message["method"] == "tools/list":
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "tools": [
                            {"name": "search"},
                            {"name": "get_requirement"},
                            {"name": "secret_tool"},
                        ]
                    },
                }
            ).encode()
        body = (
            {
                "content_kind": "error",
                "request_id": "r9",
                "message": "no such requirement",
            }
            if self.is_error
            else {
                "content_kind": "documentary-data",
                "request_id": "r9",
                "citations": [CITATION],
                "warnings": ["draft edition"],
                "truncated": False,
                "result": {"text": "The OBC shall boot."},
            }
        )
        return json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(body)}],
                    "isError": self.is_error,
                },
            }
        ).encode()


def _client(server, **kwargs):
    return KBClient(
        make_kb_config(**kwargs),
        environment={"KB_CLIENT_SECRET": "s3cret"},
        opener=server,
    )


def _calls(server):
    return [r for r in server.requests if not r.full_url.endswith("/token")]


def test_001_a_call_carries_the_token_and_the_person():
    server = Server()
    result = _client(server).call(
        "get_requirement",
        {"req_id": "X-1"},
        user="anna",
        groups=["kb-isis", "t-authors"],
    )
    assert result.ok and result.data["text"] == "The OBC shall boot."
    assert result.request_id == "r9" and result.warnings == ["draft edition"]
    assert result.citations[0]["doc_ref"] == CITATION["doc_ref"]
    request = _calls(server)[0]
    assert request.full_url == "http://kb.internal/mcp"
    headers = {k.lower(): v for k, v in request.header_items()}
    assert headers["authorization"] == "Bearer tok1"
    assert headers["x-on-behalf-of"] == "anna"
    assert headers["x-on-behalf-of-groups"] == "kb-isis,t-authors"
    token_request = server.requests[0]
    form = urllib.parse.parse_qs(token_request.data.decode())
    assert form["grant_type"] == ["client_credentials"]
    assert form["client_id"] == ["strictdoc-kb"] and form["client_secret"] == [
        "s3cret"
    ]


def test_002_the_token_is_kept_until_it_expires():
    server = Server()
    clock = [0.0]
    client = KBClient(
        make_kb_config(),
        environment={"KB_CLIENT_SECRET": "x"},
        opener=server,
        clock=lambda: clock[0],
    )
    for _ in range(3):
        client.call("search", {"query": "a"}, user="anna", groups=[])
    assert sum(r.full_url.endswith("/token") for r in server.requests) == 1
    clock[0] = 4000.0
    client.call("search", {"query": "a"}, user="anna", groups=[])
    assert sum(r.full_url.endswith("/token") for r in server.requests) == 2


def test_003_a_tool_outside_the_allow_list_is_never_sent():
    server = Server()
    with pytest.raises(KBError, match="not allowed"):
        _client(server, tools=["search"]).call(
            "get_requirement", {"req_id": "X"}, user="anna", groups=[]
        )
    assert _calls(server) == []


def test_004_the_list_of_tools_is_limited_to_the_allow_list():
    names = [
        t["name"]
        for t in _client(
            Server(), tools=["search", "get_requirement"]
        ).tool_definitions(user="anna", groups=[])
    ]
    assert names == ["search", "get_requirement"]


def test_005_an_error_of_the_tool_is_a_result_not_an_exception():
    result = _client(Server(is_error=True)).call(
        "get_requirement", {"req_id": "X"}, user="anna", groups=[]
    )
    assert not result.ok and "no such requirement" in result.message


def test_006_the_secret_is_needed():
    client = KBClient(make_kb_config(), environment={}, opener=Server())
    with pytest.raises(KBError, match="KB_CLIENT_SECRET"):
        client.call("search", {"query": "a"}, user="anna", groups=[])


def test_007_a_refusal_of_the_server_is_an_error():
    with pytest.raises(KBError, match="403"):
        _client(Server(status_error=403)).call(
            "search", {}, user="anna", groups=[]
        )


def test_008_missions_are_read_even_if_the_tool_is_not_in_the_list():
    class Missions(Server):
        def __call__(self, request, timeout):
            if (
                request.full_url.endswith("/mcp")
                and json.loads(request.data)["params"]["name"]
                == "list_missions"
            ):
                self.requests.append(request)
                body = {
                    "request_id": "r",
                    "result": {"missions": [{"code": "isis"}]},
                }
                return json.dumps(
                    {
                        "result": {
                            "content": [
                                {"type": "text", "text": json.dumps(body)}
                            ]
                        }
                    }
                ).encode()
            return super().__call__(request, timeout)

    rows = _client(Missions(), tools=["search"]).missions(
        user="anna", groups=["kb-isis"]
    )
    assert rows == [{"code": "isis"}]
    assert time  # the module is used by the clock default
