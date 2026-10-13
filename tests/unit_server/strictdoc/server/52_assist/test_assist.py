import json
import time
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


def test_017_split_keeps_the_first_part_and_adds_the_others_in_order(tmp_path):
    answer = {
        "items": [
            {
                "title": "Memory",
                "statement": "The software shall use at most 32 MB.",
            },
            {
                "title": "Boot",
                "statement": "The software shall boot within 2 s.",
            },
            {"title": "Log", "statement": "The software shall log each boot."},
        ]
    }
    client = make_client(tmp_path, _llm(answer))
    body = _ask(client, "/split").json()
    ops = [a["op"] for a in body["actions"]]
    assert ops == ["replace_text", "insert_node", "insert_node"]
    assert body["actions"][0]["old"] == TEXT
    ids = [a["id"] for a in body["actions"] if a["op"] == "insert_node"]
    response = client.post(
        "/actions/llm/apply",
        json={"call_id": body["meta"]["call_id"], "action_ids": ids},
        headers=AUTHOR,
    )
    assert response.json()["errors"] == []
    text = _flight(tmp_path)
    # Both nodes were created after FSW-1, the second after the first.
    assert text.index("Boot\n") < text.index("Log\n") < text.index("FSW-2")


def test_018_an_atomic_requirement_is_left_alone(tmp_path):
    client = make_client(tmp_path, _llm({"items": [{"statement": TEXT}]}))
    body = _ask(client, "/split").json()
    assert body["actions"] == []
    assert "already atomic" in body["message"]


def test_019_fix_uses_the_findings_of_the_last_verify(tmp_path, provider):
    verify = {
        "findings": [
            {
                "severity": "warning",
                "rule": "R-VERIFIABLE",
                "quote": "at most 32 MB",
                "message": "Which memory?",
                "suggestion": "Name the memory.",
            }
        ]
    }
    fake = provider(
        verify,
        {
            "text": "The software shall use at most 32 MB of RAM.",
            "notes": "Named.",
        },
    )
    client = make_client(tmp_path, _llm("x"))
    _ask(client, "/verify")
    body = _ask(client, "/fix keep it short").json()
    assert body["actions"][0]["new"].endswith("of RAM.")
    user = fake.requests[1].user
    assert "R-VERIFIABLE: Which memory?" in user
    assert "Notes of the user: keep it short" in user


def test_020_trace_proposes_parents_among_the_mentions(tmp_path):
    answer = {"links": [{"uid": "DA-2", "reason": "Same boot time."}]}
    client = make_client(tmp_path, _llm(answer))
    body = _ask(
        client,
        "/trace @DA-1 @DA-2",
        node=FL_2,
        text="The software shall boot within 2 s.",
    ).json()
    action = body["actions"][0]
    assert (action["op"], action["uid"], action["node"]) == (
        "add_relation",
        "DA-2",
        FL_2,
    )
    response = client.post(
        "/actions/llm/apply",
        json={"call_id": body["meta"]["call_id"], "action_ids": [action["id"]]},
        headers=AUTHOR,
    )
    assert response.json()["errors"] == []
    flight = _flight(tmp_path)
    assert flight.count("VALUE: DA-2") == 1

    # No mention, nothing to link to; a UID outside the mentions is refused.
    assert _ask(client, "/trace").status_code == 400
    bad = make_client(tmp_path / "bad", _llm({"links": [{"uid": "DA-1"}]}))
    refused = _ask(bad, "/trace @DA-2")
    assert (
        refused.status_code == 502 and "unknown UID" in refused.json()["detail"]
    )


def test_021_trace_does_not_offer_a_parent_it_already_has(tmp_path):
    # FSW-1 already has DA-1 as parent: it is not a candidate.
    client = make_client(tmp_path, _llm({"links": [{"uid": "DA-1"}]}))
    response = _ask(client, "/trace @DA-1")
    assert response.status_code == 502


def test_022_test_proposes_cases_and_an_optional_comment(tmp_path):
    answer = {
        "verification_method": "T",
        "cases": [
            {
                "name": "Nominal",
                "given": "A 64 MB board",
                "when": "The software runs",
                "then": "It uses at most 32 MB",
            }
        ],
    }
    client = make_client(tmp_path, _llm(answer))
    body = _ask(client, "/test", headers=REVIEWER).json()
    assert "**Verification method:** T" in body["message"]
    assert "Nominal" in body["message"]
    assert body["actions"][0]["op"] == "add_comment"
    assert body["actions"][0]["default"] is False


def test_023_retranslate_lists_the_drift_as_findings(tmp_path):
    answer = {
        "translation": "The software must use 32 MB.",
        "back": "The software may use 32 MB.",
        "differences": [
            {
                "original": "at most 32 MB",
                "back": "may use 32 MB",
                "message": "An upper limit became a permission.",
            }
        ],
    }
    client = make_client(tmp_path, _llm(answer))
    body = _ask(client, "/retranslate en", headers=REVIEWER).json()
    assert [f["rule"] for f in body["findings"]] == ["R-DRIFT"]
    assert body["findings"][0]["quote"] == "at most 32 MB"
    assert "**Translation:**" in body["message"]
    assert _ask(client, "/retranslate", headers=REVIEWER).status_code == 400


# -- the document bar ----------------------------------------------------------


def _doc(client, command, headers=AUTHOR, **extra):
    payload = {
        "v": 1,
        "scope": "document",
        "input": command,
        "target": {"document_mid": FLIGHT_DOC},
    }
    payload.update(extra)
    return client.post("/actions/llm/assist", json=payload, headers=headers)


def _wait(client, job_id, headers=AUTHOR, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/actions/llm/jobs/{job_id}", headers=headers).json()
        if body["status"] != "running":
            return body
        time.sleep(0.05)
    raise AssertionError("The job did not end.")


def test_024_summarize_and_ask_use_the_document_when_nothing_is_mentioned(
    tmp_path, provider
):
    fake = provider({"answer": "Three requirements."})
    client = make_client(tmp_path, _llm("x"))
    body = _doc(client, "/summarize", headers=READER).json()
    assert body["message"] == "Three requirements."
    assert "uid=FSW-1" in fake.requests[0].user
    assert "uid=FSW-3" in fake.requests[0].user
    assert (
        _doc(client, "/ask what is booting?", headers=READER).status_code == 200
    )
    assert _doc(client, "/ask", headers=READER).status_code == 400


def test_025_consistency_lists_findings_for_reviewers(tmp_path):
    answer = {
        "findings": [
            {
                "severity": "error",
                "rule": "R-CONSISTENCY",
                "quote": "",
                "message": "FSW-1 and FSW-7 give different limits.",
                "suggestion": "Align them.",
            }
        ]
    }
    client = make_client(tmp_path, _llm(answer))
    body = _doc(client, "/consistency", headers=REVIEWER).json()
    assert [f["rule"] for f in body["findings"]] == ["R-CONSISTENCY"]
    assert body["actions"] == []
    assert _doc(client, "/consistency", headers=READER).status_code == 403


def test_026_review_is_a_job_that_finds_comments_to_apply(tmp_path):
    answer = {
        "comments": [
            {
                "node": "FSW-1",
                "severity": "warning",
                "quote": "32 MB",
                "body": "Which memory?",
            },
            {
                "node": "FSW-3",
                "severity": "info",
                "quote": "",
                "body": "Say the unit of every.",
            },
        ]
    }
    client = make_client(tmp_path, _llm(answer))
    started = _doc(client, "/review testability", headers=REVIEWER).json()
    assert started["status"] == "running"
    job_id = started["meta"]["job"]["id"]
    done = _wait(client, job_id, REVIEWER)
    assert done["status"] == "ok"
    assert done["meta"]["job"]["done"] == done["meta"]["job"]["total"] == 1
    assert [a["node_uid"] for a in done["actions"]] == ["FSW-1", "FSW-3"]
    assert [a["default"] for a in done["actions"]] == [True, False]
    assert "2 remarks on 3 requirements" in done["message"]
    # Someone else does not see the job; the owner applies the ticked remarks.
    assert (
        client.get(f"/actions/llm/jobs/{job_id}", headers=AUTHOR).status_code
        == 404
    )
    response = client.post(
        "/actions/llm/apply",
        json={"call_id": job_id, "action_ids": [done["actions"][0]["id"]]},
        headers=REVIEWER,
    )
    assert response.json()["errors"] == []
    text = _flight(tmp_path)
    assert "Which memory?" in text and "Say the unit" not in text
    assert "source=llm" not in text


def test_027_one_job_at_a_time_and_a_job_can_be_cancelled(tmp_path):
    def slow(_request):
        time.sleep(0.4)
        return json.dumps({"comments": []})

    llm = make_llm(
        providers={
            "local": Fake(answers=[json.dumps({"comments": []})], is_local=True)
        }
    )
    client = make_client(tmp_path, llm)
    # A provider that answers slowly: patch the fake answers through the config.
    llm.providers["local"].answers = [slow]
    first = _doc(client, "/review", headers=REVIEWER).json()
    again = _doc(client, "/review", headers=REVIEWER)
    assert again.status_code == 429
    job_id = first["meta"]["job"]["id"]
    assert (
        client.delete(f"/actions/llm/jobs/{job_id}", headers=AUTHOR).status_code
        == 404
    )
    assert (
        client.delete(
            f"/actions/llm/jobs/{job_id}", headers=REVIEWER
        ).status_code
        == 200
    )
    assert _wait(client, job_id, REVIEWER)["status"] in ("cancelled", "ok")


def test_028_write_plans_then_writes_each_topic(tmp_path, provider):
    outline = {
        "topics": [
            {"title": "Memory", "scope": "from DA-1"},
            {"title": "Boot", "scope": "from DA-2"},
        ]
    }

    def topic(title, statement):
        return {
            "proposals": [
                {
                    "title": title,
                    "statement": statement,
                    "verification_method": "T",
                    "linked_to": ["DA-1"],
                }
            ]
        }

    fake = provider(
        outline,
        topic("Memory budget", "The software shall use at most 32 MB."),
        topic("Boot time", "The software shall boot within 2 s."),
    )
    client = make_client(tmp_path, _llm("x"))
    started = _doc(
        client,
        "/write software requirements based on @DA-1 and @DA-2",
        headers=AUTHOR,
    ).json()
    done = _wait(client, started["meta"]["job"]["id"])
    assert done["status"] == "ok", done
    assert [a["op"] for a in done["actions"]] == ["insert_node", "insert_node"]
    assert done["actions"][0]["position"] == {
        "where": "last_child",
        "ref": FLIGHT_DOC,
    }
    assert "Already written: Memory budget" in fake.requests[2].user
    assert "uid=DA-1" in fake.requests[1].user

    ids = [a["id"] for a in done["actions"]]
    response = client.post(
        "/actions/llm/apply",
        json={"call_id": started["meta"]["job"]["id"], "action_ids": ids},
        headers=AUTHOR,
    )
    assert response.json()["errors"] == []
    text = _flight(tmp_path)
    assert text.index("Memory budget") < text.index("Boot time")
    assert text.count("STATUS: Draft") == 2


def test_029_trace_proposes_parents_for_the_requirements_that_have_none(
    tmp_path,
):
    answer = {
        "links": [{"node": "FSW-2", "uid": "DA-2", "reason": "Same boot time."}]
    }
    client = make_client(tmp_path, _llm(answer))
    started = _doc(client, "/trace @DA-1 @DA-2").json()
    done = _wait(client, started["meta"]["job"]["id"])
    assert [a["label"] for a in done["actions"]] == ["FSW-2 → DA-2"]
    # FSW-1 has a parent already: only FSW-2 and FSW-3 were in the batch.
    assert "2 requirements that have no parent" in done["message"]
    response = client.post(
        "/actions/llm/apply",
        json={
            "call_id": started["meta"]["job"]["id"],
            "action_ids": [done["actions"][0]["id"]],
        },
        headers=AUTHOR,
    )
    assert response.json()["errors"] == []
    assert _flight(tmp_path).count("VALUE: DA-2") == 1
    assert _doc(client, "/trace").status_code == 400


def test_030_the_document_bar_checks_roles_and_scope(tmp_path):
    client = make_client(tmp_path, _llm({"comments": []}))
    for command in ("/review", "/write x", "/trace @DA-1"):
        assert _doc(client, command, headers=READER).status_code == 403
    assert _doc(client, "/rewrite").status_code == 400
    missing = client.post(
        "/actions/llm/assist",
        json={"v": 1, "scope": "document", "input": "/summarize", "target": {}},
        headers=AUTHOR,
    )
    assert missing.status_code == 404
    assert (
        client.get("/actions/llm/jobs/nothing", headers=AUTHOR).status_code
        == 404
    )
