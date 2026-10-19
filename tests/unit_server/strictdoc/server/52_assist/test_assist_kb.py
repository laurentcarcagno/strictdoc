import json

import pytest

import strictdoc.features.llm.assist.kb_support as kb_support
import strictdoc.features.llm.assist.service as assist_service
from strictdoc.features.llm.config import Fake, OpenAICompatible
from strictdoc.features.llm.fake import FakeProvider
from strictdoc.features.llm.types import LLMResponse, ToolCall
from tests.support.kb_fixture import (
    REQ_TEXT,
    FakeKBClient,
    make_kb_config,
)
from tests.support.llm_fixture import (
    AUTHOR,
    FL_1,
    FLIGHT_DOC,
    READER,
    REVIEWER,
    make_client,
    make_llm,
)

TEXT = "The software shall send the heartbeat."
ANSWER = {"answer": "Every 500 ms (ISIS-SYS-IF-249-CNES ed. 9.0 §3.2)."}


def _ask(client, command, headers=AUTHOR, text=TEXT, **extra):
    payload = {
        "v": 1,
        "scope": "field",
        "input": command,
        "target": {
            "document_mid": FLIGHT_DOC,
            "node_mid": FL_1,
            "field": "STATEMENT",
            "text": text,
        },
    }
    payload.update(extra)
    return client.post("/actions/llm/assist", json=payload, headers=headers)


def _audit(root):
    path = root / "audit" / "llm_audit.jsonl"
    return (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )


@pytest.fixture
def setup(monkeypatch):
    holder = {}

    def install(*answers, kb=None, **llm_kwargs):
        provider = FakeProvider(
            [
                a if isinstance(a, (str, LLMResponse)) else json.dumps(a)
                for a in answers
            ],
            is_local=llm_kwargs.pop("is_local", True),
            name=llm_kwargs.pop("provider_name", "local"),
        )
        fake = kb if kb is not None else FakeKBClient()
        monkeypatch.setattr(
            assist_service, "create_provider", lambda _n, _l: provider
        )
        monkeypatch.setattr(kb_support.KBSupport, "client", lambda self: fake)
        holder.update(provider=provider, kb=fake)
        return provider, fake

    return install


def _llm(**kwargs):
    kb = kwargs.pop("kb", make_kb_config())
    return make_llm(
        kb=kb,
        providers={"local": Fake(answers=["x"], is_local=True)},
        **kwargs,
    )


def _search_then_read():
    return [
        LLMResponse(
            "", tool_calls=(ToolCall("1", "search", {"query": "heartbeat"}),)
        ),
        LLMResponse(
            "",
            tool_calls=(
                ToolCall(
                    "2", "get_requirement", {"req_id": "ISIS-IF-249-0100"}
                ),
            ),
        ),
        "enough",
        ANSWER,
    ]


def test_001_ask_runs_the_tool_loop_and_shows_the_sources(tmp_path, setup):
    provider, kb = setup(*_search_then_read())
    client = make_client(tmp_path, _llm())
    body = _ask(client, "/ask what is the heartbeat period?").json()
    assert body["status"] == "ok", body
    assert "500 ms" in body["message"]
    assert body["meta"]["kb"]["sources"] == [
        "ISIS-SYS-IF-249-CNES ed. 9.0 §3.2"
    ]
    assert body["meta"]["kb"]["calls"] == ["search", "get_requirement"]
    # The last call (the answer) holds the text of the base as data.
    last = provider.requests[-1]
    assert "BEGIN kb" in last.user and "KB-DATA" in last.user
    assert REQ_TEXT in last.user and "Items of kind kb" in last.user
    # The person is passed on with their groups.
    assert kb.calls[0]["user"] == "anna"


def test_002_both_the_loop_and_the_tools_are_in_the_audit(tmp_path, setup):
    setup(*_search_then_read())
    client = make_client(tmp_path, _llm())
    _ask(client, "/ask what is the heartbeat period?")
    entries = _audit(tmp_path)
    tools = [e for e in entries if e.get("kind") == "kb_tool"]
    assert [e["tool"] for e in tools] == ["search", "get_requirement"]
    assert tools[0]["user"] == "anna" and tools[0]["mission"] == "isis"
    assert (
        tools[1]["request_id"] == "srv-2"
        and len(tools[0]["arguments_sha256"]) == 64
    )
    assert "arguments" not in tools[0]
    assert any(e.get("template") == "kb_gather@2" for e in entries)


def test_003_a_command_that_is_not_listed_does_not_read_the_base(
    tmp_path, setup
):
    provider, kb = setup({"findings": [], "message": "ok"})
    client = make_client(tmp_path, _llm(kb=make_kb_config(commands=["ask"])))
    _ask(client, "/verify")
    assert kb.calls == []


def test_004_a_project_without_kb_works_as_before(tmp_path, setup):
    provider, kb = setup(ANSWER)
    client = make_client(
        tmp_path,
        make_llm(providers={"local": Fake(answers=["x"], is_local=True)}),
    )
    body = _ask(client, "/ask hello?").json()
    assert (
        body["status"] == "ok" and "kb" not in body["meta"] and kb.calls == []
    )


def test_005_a_person_who_does_not_see_the_mission_gets_no_base(
    tmp_path, setup
):
    provider, kb = setup(ANSWER, kb=FakeKBClient(missions=[]))
    client = make_client(tmp_path, _llm())
    body = _ask(client, "/ask what is the heartbeat period?").json()
    assert body["status"] == "ok"
    assert any("no mission isis" in w for w in body["warnings"])
    assert kb.calls == []


def test_006_a_base_that_is_down_does_not_stop_the_command(tmp_path, setup):
    setup(ANSWER, kb=FakeKBClient(fail=True))
    client = make_client(tmp_path, _llm())
    body = _ask(client, "/ask what is the heartbeat period?").json()
    assert body["status"] == "ok"
    assert any("was not read" in w for w in body["warnings"])


def test_007_slash_kb_searches_without_a_model(tmp_path, setup):
    provider, kb = setup()
    client = make_client(tmp_path, _llm())
    body = _ask(client, "/kb heartbeat", headers=REVIEWER).json()
    assert body["status"] == "ok", body
    assert (
        "ISIS-SYS-IF-249-CNES" in body["message"]
        and "ISIS-IF-249-0100" in body["message"]
    )
    assert provider.requests == []
    assert body["meta"]["kb"]["sources"]
    assert [
        e["tool"] for e in _audit(tmp_path) if e.get("kind") == "kb_tool"
    ] == ["search"]


def test_008_slash_kb_is_for_reviewers_and_needs_a_base(tmp_path, setup):
    setup()
    client = make_client(tmp_path, _llm())
    assert _ask(client, "/kb heartbeat", headers=READER).status_code == 403
    plain = make_client(tmp_path / "b", make_llm())
    assert _ask(plain, "/kb heartbeat", headers=REVIEWER).status_code == 400
    assert _ask(client, "/kb ", headers=REVIEWER).status_code == 400


def test_009_cite_inserts_the_requirement_word_for_word(tmp_path, setup):
    provider, kb = setup()
    client = make_client(tmp_path, _llm())
    body = _ask(client, "/cite ISIS-IF-249-0100").json()
    assert body["status"] == "ok", body
    action = body["actions"][0]
    assert action["op"] == "replace_text" and action["old"] == ""
    assert action["range"] == {"from": len(TEXT), "to": len(TEXT)}
    assert f"> {REQ_TEXT}" in action["new"]
    assert "kb://isis/ISIS-SYS-IF-249-CNES/9.0/3.2" in action["new"]
    assert provider.requests == []


def test_010_cite_replaces_the_selection(tmp_path, setup):
    setup()
    client = make_client(tmp_path, _llm())
    start = TEXT.index("heartbeat")
    payload = {
        "v": 1,
        "scope": "field",
        "input": "/cite @ISIS-IF-249-0100",
        "target": {
            "document_mid": FLIGHT_DOC,
            "node_mid": FL_1,
            "field": "STATEMENT",
            "text": TEXT,
            "selection": {"text": "heartbeat", "from": start, "to": start + 9},
        },
    }
    body = client.post(
        "/actions/llm/assist", json=payload, headers=AUTHOR
    ).json()
    action = body["actions"][0]
    assert action["old"] == "heartbeat" and action["range"] == {
        "from": start,
        "to": start + 9,
    }


def test_011_cite_refuses_what_it_cannot_quote_whole(tmp_path, setup):
    setup(kb=FakeKBClient(truncated=True))
    client = make_client(tmp_path, _llm())
    assert _ask(client, "/cite ISIS-IF-249-0100").status_code == 409
    setup(kb=FakeKBClient())
    assert _ask(client, "/cite NOPE-1").status_code == 404


def test_012_a_cloud_provider_gets_a_plain_search_and_a_confirmation(
    tmp_path, setup
):
    row = {
        "code": "isis",
        "classification": "interne",
        "allowed_models": ["cloud-model"],
    }
    provider, kb = setup(
        ANSWER, kb=FakeKBClient(missions=[row]), is_local=False
    )
    llm = make_llm(
        kb=make_kb_config(),
        default="cloud",
        allow_cloud=True,
        providers={
            "cloud": OpenAICompatible(
                "https://api.example/v1", "cloud-model", False
            )
        },
    )
    provider.model = "cloud-model"
    client = make_client(tmp_path, llm)
    body = _ask(client, "/ask what is the heartbeat period?").json()
    assert body["status"] == "needs_confirmation", body
    # No model ran the loop: one plain search, and the sources are listed.
    assert [c["tool"] for c in kb.calls] == [
        "search"
    ] and provider.requests == []
    assert body["confirmation"]["kb_sources"] == [
        "ISIS-SYS-IF-249-CNES ed. 9.0 §3.2"
    ]
    assert "BEGIN kb" in body["confirmation"]["prompt"]


def test_013_a_cloud_provider_the_mission_does_not_list_gets_no_base(
    tmp_path, setup
):
    provider, kb = setup(ANSWER, is_local=False)
    llm = make_llm(
        kb=make_kb_config(),
        default="cloud",
        allow_cloud=True,
        providers={
            "cloud": OpenAICompatible(
                "https://api.example/v1", "other-model", False
            )
        },
    )
    provider.model = "other-model"
    client = make_client(tmp_path, llm)
    body = _ask(client, "/ask what is the heartbeat period?").json()
    assert kb.calls == []
    assert body["status"] == "needs_confirmation"
    assert "BEGIN kb" not in body["confirmation"]["prompt"]


def test_014_a_blocked_classification_of_the_mission_never_goes_to_the_cloud(
    tmp_path, setup
):
    row = {
        "code": "isis",
        "classification": "restricted",
        "allowed_models": ["cloud-model"],
    }
    provider, kb = setup(
        ANSWER, kb=FakeKBClient(missions=[row]), is_local=False
    )
    llm = make_llm(
        kb=make_kb_config(),
        default="cloud",
        allow_cloud=True,
        cloud_blocked_classifications=["Restricted"],
        providers={
            "cloud": OpenAICompatible(
                "https://api.example/v1", "cloud-model", False
            )
        },
    )
    provider.model = "cloud-model"
    client = make_client(tmp_path, llm)
    response = _ask(
        client, "/ask what is the heartbeat period?", cloud_confirmed=True
    )
    assert response.status_code == 403
    assert provider.requests == []


def test_015_the_catalogue_lists_kb_and_cite(tmp_path, setup):
    setup()
    client = make_client(tmp_path, _llm())
    body = _ask(client, "/help", headers=READER).json()
    assert "/kb" in body["message"] and "/cite" in body["message"]


# -- /kbcheck: the quotes of the base in a document ---------------------------------


def _doc(client, command, headers=REVIEWER):
    return client.post(
        "/actions/llm/assist",
        json={
            "v": 1,
            "scope": "document",
            "input": command,
            "target": {"document_mid": FLIGHT_DOC},
        },
        headers=headers,
    )


def _quote(req_id, text, edition="9.0"):
    return (
        f"> {text}\n"
        f"> — {req_id}, ISIS-SYS-IF-249-CNES ed. {edition} §3.2 "
        f"(kb://isis/ISIS-SYS-IF-249-CNES/{edition}/3.2)"
    )


def _flight_with(monkeypatch, comment):
    from tests.support import llm_fixture

    monkeypatch.setattr(
        llm_fixture,
        "FLIGHT",
        llm_fixture.FLIGHT.replace(
            "The software shall use at most 32 MB.\n<<<",
            "The software shall use at most 32 MB.\n<<<\nCOMMENT: >>>\n"
            + comment
            + "\n<<<",
            1,
        ),
    )


def test_016_kbcheck_compares_each_quote_with_the_base(
    tmp_path, setup, monkeypatch
):
    comment = "\n\n".join(
        [
            _quote("ISIS-IF-249-0100", REQ_TEXT),
            _quote("ISIS-IF-249-0200", "An older wording.", edition="8.0"),
            _quote("NOPE-1", "Gone."),
        ]
    )
    _flight_with(monkeypatch, comment)
    provider, kb = setup()
    client = make_client(tmp_path, _llm())
    body = _doc(client, "/kbcheck").json()
    assert body["status"] == "ok", body
    assert body["message"] == "3 quote(s) checked, 3 problems."
    rules = sorted(
        (f["rule"], f["message"].split(":")[0]) for f in body["findings"]
    )
    assert rules == [
        ("R-KB-CHANGED", "FSW-1"),
        ("R-KB-EDITION", "FSW-1"),
        ("R-KB-GONE", "FSW-1"),
    ]
    assert provider.requests == []
    assert [c["tool"] for c in kb.calls] == ["get_requirement"] * 3
    assert {c["user"] for c in kb.calls} == {"rita"}
    audited = [e for e in _audit(tmp_path) if e.get("kind") == "kb_tool"]
    assert len(audited) == 3


def test_017_kbcheck_reports_a_document_without_quotes(tmp_path, setup):
    setup()
    client = make_client(tmp_path, _llm())
    body = _doc(client, "/kbcheck").json()
    assert body["status"] == "ok" and not body["findings"]
    assert "quotes nothing" in body["message"]


def test_018_kbcheck_needs_the_mission_and_the_role(tmp_path, setup):
    setup(kb=FakeKBClient(missions=[]))
    client = make_client(tmp_path, _llm())
    assert _doc(client, "/kbcheck", headers=READER).status_code == 403
    # A reviewer outside the group is refused only when a quote has to be read.
    plain = _doc(client, "/kb heartbeat")
    assert plain.status_code == 403


def test_019_kb_also_works_from_the_document_bar(tmp_path, setup):
    setup()
    client = make_client(tmp_path, _llm())
    body = _doc(client, "/kb heartbeat").json()
    assert body["status"] == "ok" and "ISIS-IF-249-0100" in body["message"]
