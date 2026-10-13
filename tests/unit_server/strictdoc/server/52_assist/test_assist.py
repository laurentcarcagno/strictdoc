import json
from pathlib import Path

import pytest

import strictdoc.features.llm.assist.service as assist_service
from strictdoc.features.llm.config import Fake
from strictdoc.features.llm.fake import FakeProvider
from tests.support.llm_fixture import (
    AUTHOR,
    FL_1,
    FL_2,
    FLIGHT_DOC,
    READER,
    REVIEWER,
    make_client,
    make_llm,
)

TEXT = "The software shall use at most 32 MB."


def _llm(*answers, **kwargs):
    return make_llm(
        providers={
            "local": Fake(
                answers=[
                    json.dumps(a) if not isinstance(a, str) else a
                    for a in answers
                ],
                is_local=True,
            )
        },
        **kwargs,
    )


def _ask(client, command, headers=AUTHOR, text=TEXT, node=FL_1, **extra):
    target = {
        "document_mid": FLIGHT_DOC,
        "node_mid": node,
        "field": "STATEMENT",
        "text": text,
    }
    target.update(extra.pop("target", {}))
    payload = {"v": 1, "scope": "field", "input": command, "target": target}
    payload.update(extra)
    return client.post("/actions/llm/assist", json=payload, headers=headers)


def _flight(root: Path) -> str:
    return (root / "input" / "flight.sdoc").read_text(encoding="utf8")


def _audit(root: Path):
    path = root / "audit" / "llm_audit.jsonl"
    return (
        [json.loads(line) for line in path.read_text().splitlines()]
        if path.exists()
        else []
    )


@pytest.fixture
def provider(monkeypatch):
    """One provider object for the test, to read what it was sent."""
    holder = {}

    def install(*answers):
        holder["provider"] = FakeProvider(
            [a if isinstance(a, str) else json.dumps(a) for a in answers]
        )
        monkeypatch.setattr(
            assist_service,
            "create_provider",
            lambda _name, _llm: holder["provider"],
        )
        return holder["provider"]

    return install


def test_001_help_needs_no_model(tmp_path):
    client = make_client(tmp_path, _llm())
    body = _ask(client, "/help", headers=READER).json()
    assert body["status"] == "ok" and "/rewrite" in body["message"]
    assert _audit(tmp_path) == []


def test_002_rewrite_proposes_a_replacement(tmp_path):
    answer = {
        "text": "The software shall use at most 16 MB.",
        "notes": "Smaller.",
    }
    client = make_client(tmp_path, _llm(answer))
    body = _ask(client, "/rewrite concise").json()
    action = body["actions"][0]
    assert action["op"] == "replace_text" and action["default"] is True
    assert action["old"] == TEXT and action["range"] is None
    assert action["new"] == "The software shall use at most 16 MB."
    assert any("Numbers or identifiers" in w for w in body["warnings"])
    assert body["meta"]["prompt"] == "rewrite@1"
    assert body["meta"]["call_id"]
    # The document is not touched.
    assert "16 MB" not in _flight(tmp_path)
    assert _audit(tmp_path)[-1]["template"] == "rewrite@1"


def test_003_rewrite_a_selection_gives_a_range(tmp_path, provider):
    fake = provider({"text": "at most 32 megabytes"})
    client = make_client(tmp_path, _llm("x"))
    body = _ask(
        client,
        "/rewrite",
        target={"selection": {"text": "at most 32 MB", "from": 23, "to": 36}},
    ).json()
    action = body["actions"][0]
    assert action["range"] == {"from": 23, "to": 36}
    assert action["old"] == "at most 32 MB"
    assert "BEGIN selection" in fake.requests[0].user


def test_004_roles_decide_who_may_run_a_command(tmp_path):
    client = make_client(
        tmp_path, _llm({"text": TEXT + " Ok."}, {"answer": "It limits memory."})
    )
    assert _ask(client, "/rewrite", headers=READER).status_code == 403
    assert _ask(client, "/rewrite", headers=REVIEWER).status_code == 403
    assert _ask(client, "/verify", headers=READER).status_code == 403
    assert _ask(client, "/explain", headers=READER).status_code == 200
    assert _ask(client, "/rewrite", headers=AUTHOR).status_code == 200


def test_005_verify_lists_findings_and_comment_actions(tmp_path):
    answer = {
        "verdict": "warn",
        "findings": [
            {
                "severity": "warning",
                "rule": "R-VERIFIABLE",
                "quote": "at most 32 MB",
                "message": "Which memory?",
                "suggestion": "Name the memory.",
            }
        ],
    }
    client = make_client(tmp_path, _llm(answer))
    body = _ask(client, "/verify", headers=REVIEWER).json()
    assert [f["rule"] for f in body["findings"]] == ["R-VERIFIABLE"]
    actions = body["actions"]
    assert actions[0]["op"] == "add_comment"
    assert actions[0]["anchor"] == {"text": "at most 32 MB", "n": 1}
    assert actions[0]["node"] == FL_1


def test_006_ticked_comments_are_added_without_any_signature(tmp_path):
    answer = {
        "comments": [
            {"severity": "warning", "quote": "32 MB", "body": "Which memory?"},
            {"severity": "info", "quote": "", "body": "Fine otherwise."},
        ]
    }
    client = make_client(tmp_path, _llm(answer))
    body = _ask(client, "/comment", headers=REVIEWER).json()
    ids = [a["id"] for a in body["actions"]]
    assert [a["default"] for a in body["actions"]] == [True, False]
    response = client.post(
        "/actions/llm/apply",
        json={"call_id": body["meta"]["call_id"], "action_ids": ids[:1]},
        headers=REVIEWER,
    )
    assert response.json() == {"applied": ids[:1], "errors": []}
    text = _flight(tmp_path)
    assert "Which memory?" in text and "Fine otherwise." not in text
    assert "author=rita" in text or "rita" in text
    # No mark of the assistant in the comment.
    assert "llm" not in text.lower().split("which memory?")[0][-300:]
    assert "source=llm" not in text and "model=" not in text


def test_007_apply_refuses_unknown_actions_and_other_users(tmp_path):
    client = make_client(
        tmp_path, _llm({"comments": [{"body": "A remark.", "quote": ""}]})
    )
    body = _ask(client, "/comment", headers=REVIEWER).json()
    call_id = body["meta"]["call_id"]
    wrong_user = client.post(
        "/actions/llm/apply",
        json={"call_id": call_id, "action_ids": [body["actions"][0]["id"]]},
        headers=AUTHOR,
    )
    assert wrong_user.status_code == 404
    unknown = client.post(
        "/actions/llm/apply",
        json={"call_id": call_id, "action_ids": ["nope"]},
        headers=REVIEWER,
    )
    assert unknown.status_code == 400
    # What somebody else asked is not found, whatever the role.
    assert (
        client.post(
            "/actions/llm/apply",
            json={"call_id": call_id, "action_ids": []},
            headers=READER,
        ).status_code
        == 404
    )
    assert "A remark." not in _flight(tmp_path)


def test_008_req_proposes_nodes_that_apply_creates_as_draft(tmp_path):
    proposals = {
        "proposals": [
            {
                "title": "Memory budget",
                "statement": "The software shall use at most 32 MB of memory.",
                "rationale": "Half of 64 MB.",
                "verification_method": "A",
                "linked_to": ["FSW-1"],
            }
        ]
    }
    client = make_client(tmp_path, _llm(proposals))
    body = _ask(client, "/req memory budget @FSW-1", text="").json()
    action = body["actions"][0]
    assert action["op"] == "insert_node"
    assert action["position"] == {"where": "after", "ref": FL_1}
    response = client.post(
        "/actions/llm/apply",
        json={"call_id": body["meta"]["call_id"], "action_ids": [action["id"]]},
        headers=AUTHOR,
    )
    assert response.json()["errors"] == []
    text = _flight(tmp_path)
    assert "Memory budget" in text and "STATUS: Draft" in text


def test_009_an_unknown_uid_in_linked_to_is_refused(tmp_path):
    bad = {
        "proposals": [
            {
                "title": "X",
                "statement": "The software shall do X.",
                "verification_method": "T",
                "linked_to": ["NOPE-1"],
            }
        ]
    }
    client = make_client(tmp_path, _llm(bad))
    response = _ask(client, "/req x @FSW-1", text="")
    assert response.status_code == 502
    assert "unknown UID" in response.json()["detail"]
    assert _audit(tmp_path)[-1]["status"] == "invalid_answer"


def test_010_an_invalid_answer_is_asked_again_once(tmp_path, provider):
    fake = provider("not json", {"text": "The software shall boot."})
    client = make_client(tmp_path, _llm("x"))
    body = _ask(client, "/rewrite", text="Boot.").json()
    assert body["meta"]["attempts"] == 2
    assert "Your previous answer was refused" in fake.requests[1].user


def test_011_a_mention_is_resolved_by_the_server_and_neutralised(
    tmp_path, provider
):
    fake = provider({"answer": "It lasts 2 s."})
    client = make_client(tmp_path, _llm("x"))
    body = _ask(client, "/ask what is the boot time? @DA-2 @FSW-3").json()
    assert body["message"] == "It lasts 2 s."
    user = fake.requests[0].user
    assert "uid=DA-2" in user and "uid=FSW-3" in user
    # The text of a document cannot close a block or open another one.
    lines = user.splitlines()
    assert sum(line.startswith("BEGIN ") for line in lines) == sum(
        line.strip() == "END" for line in lines
    )


def test_012_an_unknown_mention_is_a_clear_error(tmp_path):
    client = make_client(tmp_path, _llm({"answer": "x"}))
    response = _ask(client, "/ask what? @NOPE-9")
    assert response.status_code == 400
    assert "@NOPE-9" in response.json()["detail"]


def test_013_a_cloud_provider_needs_the_policy_and_a_confirmation(tmp_path):
    answer = {"answer": "ok"}
    llm = make_llm(
        providers={
            "local": Fake(answers=[json.dumps(answer)], is_local=True),
            "cloud": Fake(
                answers=[json.dumps(answer)],
                is_local=False,
                model="cloud-model",
                base_url="https://fake.invalid",
            ),
        },
        allow_cloud=True,
    )
    client = make_client(tmp_path, llm)
    first = _ask(client, "/ask hello", provider="cloud").json()
    assert first["status"] == "needs_confirmation"
    assert first["confirmation"]["model"] == "cloud-model"
    assert "hello" in first["confirmation"]["prompt"]
    second = _ask(
        client, "/ask hello", provider="cloud", cloud_confirmed=True
    ).json()
    assert second["status"] == "ok"

    closed = make_client(
        tmp_path / "closed",
        make_llm(providers=llm.providers, allow_cloud=False),
    )
    assert _ask(closed, "/ask hello", provider="cloud").status_code == 403


def test_014_the_lists_for_the_bar(tmp_path):
    client = make_client(tmp_path, _llm({"answer": "x"}))
    commands = client.get(
        "/llm/assist/commands?scope=field", headers=READER
    ).json()
    names = {c["name"] for c in commands["commands"]}
    assert {"rewrite", "verify", "comment", "req", "ask"} <= names
    assert commands["default_provider"] == "local"
    found = client.get(
        "/llm/assist/mentions?q=FSW&selection=true", headers=READER
    ).json()["mentions"]
    assert {m["token"] for m in found} >= {"FSW-1", "FSW-2"}
    selection = client.get(
        "/llm/assist/mentions?q=sel&selection=true", headers=READER
    ).json()["mentions"]
    assert selection[0]["token"] == "selection"
    assert (
        client.get("/llm/assist/mentions?q=sel", headers=READER).json()[
            "mentions"
        ]
        == []
    )


def test_015_bad_requests_are_400(tmp_path):
    client = make_client(tmp_path, _llm({"answer": "x"}))
    assert (
        client.post(
            "/actions/llm/assist", json={"v": 9, "input": "x"}, headers=AUTHOR
        ).status_code
        == 400
    )
    assert _ask(client, "/nope").status_code == 400
    assert _ask(client, "/rewrite", text="").status_code == 400
    assert _ask(client, "/translate").status_code == 400
    assert _ask(client, "/rewrite", node="0" * 32).status_code == 404
    off = make_client(tmp_path / "off", _llm({"answer": "x"}), feature=False)
    assert _ask(off, "/help").status_code == 412


def test_016_req_in_the_form_of_a_new_node_goes_after_its_reference(tmp_path):
    proposals = {
        "proposals": [
            {
                "title": "New one",
                "statement": "The software shall do the new thing.",
                "verification_method": "T",
                "linked_to": [],
            }
        ]
    }
    client = make_client(tmp_path, _llm(proposals))
    # A node that is not saved yet: no node_mid, the node it follows instead.
    body = _ask(
        client,
        "/req the new thing",
        node="",
        text="",
        target={"reference_mid": FL_2},
    ).json()
    assert body["actions"][0]["position"] == {"where": "after", "ref": FL_2}
    # Without any reference: the end of the document.
    again = _ask(client, "/req the new thing", node="", text="").json()
    assert again["actions"][0]["position"] == {
        "where": "last_child",
        "ref": FLIGHT_DOC,
    }
    applied = client.post(
        "/actions/llm/apply",
        json={
            "call_id": again["meta"]["call_id"],
            "action_ids": [again["actions"][0]["id"]],
        },
        headers=AUTHOR,
    ).json()
    assert applied["errors"] == []
    assert "New one" in _flight(tmp_path)
