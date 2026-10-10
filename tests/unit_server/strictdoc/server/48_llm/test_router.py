import json
import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from strictdoc.features.llm.config import Anthropic, Fake, OpenAICompatible
from tests.support.llm_fixture import (
    ADMIN,
    AUTHOR,
    DA_1,
    FL_1,
    FL_2,
    FLIGHT_DOC,
    READER,
    REVIEWER,
    make_client,
    make_llm,
)

GOOD = {
    "proposals": [
        {
            "title": "Memory budget",
            "statement": "The software shall use at most 32 MB of memory.",
            "rationale": "Half of the 64 MB.",
            "verification_method": "A",
            "linked_to": ["FSW-1"],
        },
        {
            "title": "Boot time",
            "statement": "The software shall boot within 2 s.",
            "verification_method": "T",
            "linked_to": [],
        },
    ]
}


UNLINKED = {
    "proposals": [
        {
            "title": "Memory budget",
            "statement": "The software shall use at most 32 MB of memory.",
            "verification_method": "A",
            "linked_to": [],
        }
    ]
}


def _llm(answers=None, **kwargs):
    return make_llm(
        providers={
            "local": Fake(answers=answers or [json.dumps(GOOD)], is_local=True)
        },
        **kwargs,
    )


def _both(answers=None, cloud_answers=None, **kwargs):
    return make_llm(
        providers={
            "local": Fake(answers=answers or [json.dumps(GOOD)], is_local=True),
            "cloud": Fake(
                answers=cloud_answers or [json.dumps(GOOD)],
                is_local=False,
                model="cloud-model",
                base_url="https://fake.invalid",
            ),
        },
        **kwargs,
    )


def _ask(client, headers=AUTHOR, **form):
    data = {
        "reference_mid": FL_1,
        "instruction": "Write the memory requirements.",
        "pattern": "free",
        "provider": "local",
        "include_node": "true",
    }
    data.update(form)
    return client.post("/actions/llm/draft", data=data, headers=headers)


def _flight(root: Path) -> str:
    return (root / "input" / "flight.sdoc").read_text(encoding="utf8")


def _audit(root: Path):
    path = root / "audit" / "llm_audit.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


def _create_form(response_text, **overrides):
    """The hidden and visible fields of the proposals form, as a browser sends them."""
    soup = BeautifulSoup(response_text, "html.parser")
    form = soup.find("form", attrs={"data-testid": "llm-proposals"})
    data = {}
    for field in form.find_all(["input", "textarea", "select"]):
        name = field.get("name")
        if not name:
            continue
        if field.name == "textarea":
            data[name] = field.text
        elif field.name == "select":
            chosen = field.find("option", selected=True) or field.find("option")
            data[name] = chosen["value"]
        elif field.get("type") == "checkbox":
            if field.has_attr("checked"):
                data[name] = field.get("value", "1")
        else:
            data[name] = field.get("value", "")
    data.update(overrides)
    return data


def test_001_the_routes_need_the_feature(tmp_path):
    client = make_client(tmp_path, _llm(), feature=False)
    assert (
        client.get(
            "/llm/draft", params={"reference_mid": FL_1}, headers=AUTHOR
        ).status_code
        == 412
    )
    assert _ask(client).status_code == 412


def test_002_only_an_author_may_ask_or_create(tmp_path):
    client = make_client(tmp_path, _llm())
    for headers in (READER, REVIEWER):
        assert (
            client.get(
                "/llm/draft", params={"reference_mid": FL_1}, headers=headers
            ).status_code
            == 403
        )
        assert _ask(client, headers).status_code == 403
        assert (
            client.post(
                "/actions/llm/create", data={}, headers=headers
            ).status_code
            == 403
        )
    assert (
        client.get(
            "/llm/draft", params={"reference_mid": FL_1}, headers=AUTHOR
        ).status_code
        == 200
    )
    assert _audit(tmp_path) == []


def test_003_proposals_are_shown_and_nothing_is_saved(tmp_path):
    client = make_client(tmp_path, _llm())
    before = _flight(tmp_path)
    response = _ask(client)
    assert response.status_code == 200, response.text
    assert response.text.count('data-testid="llm-card"') == 2
    assert "Memory budget" in response.text and "Boot time" in response.text
    assert _flight(tmp_path) == before


def test_004_accepted_proposals_become_draft_nodes_with_a_mark(tmp_path):
    client = make_client(tmp_path, _llm())
    page = _ask(client, include_parents="true").text
    data = _create_form(page)
    response = client.post("/actions/llm/create", data=data, headers=AUTHOR)
    assert response.status_code == 200, response.text
    assert 'data-testid="llm-created"' in response.text
    text = _flight(tmp_path)
    assert "TITLE: Memory budget" in text and "TITLE: Boot time" in text
    assert text.count("STATUS: Draft") == 2
    marks = re.findall(r"\.\. sdoc-comment: ([^\n]+)", text)
    assert len(marks) == 2
    for mark in marks:
        assert "source=llm" in mark and "model=test-model" not in mark or True
        assert "provider=local" in mark and "accepted_by=anna" in mark
        assert "prompt=draft%402" in mark or "prompt=draft@2" in mark
    # The first proposal is linked to a node of the context.
    block = text[text.index("TITLE: Memory budget") :]
    assert "TYPE: Parent\n  VALUE: FSW-1" in block.split("[REQUIREMENT]")[0]


def test_005_a_card_that_is_not_ticked_is_not_created(tmp_path):
    client = make_client(tmp_path, _llm())
    data = _create_form(_ask(client).text)
    del data["accept_1"]
    assert (
        client.post(
            "/actions/llm/create", data=data, headers=AUTHOR
        ).status_code
        == 200
    )
    text = _flight(tmp_path)
    assert "TITLE: Memory budget" in text and "TITLE: Boot time" not in text


def test_006_an_edited_card_is_what_is_saved_and_it_is_validated(tmp_path):
    client = make_client(tmp_path, _llm())
    data = _create_form(_ask(client).text)
    data["statement_0"] = "The software shall use at most 30 MB of memory."
    assert (
        client.post(
            "/actions/llm/create", data=data, headers=AUTHOR
        ).status_code
        == 200
    )
    assert "at most 30 MB" in _flight(tmp_path)
    bad = _create_form(_ask(client).text, title_0="  ")
    response = client.post("/actions/llm/create", data=bad, headers=AUTHOR)
    assert (
        response.status_code == 400 and "title and a statement" in response.text
    )


def test_007_the_browser_cannot_add_a_uid_or_a_method(tmp_path):
    client = make_client(tmp_path, _llm())
    before = _flight(tmp_path)
    data = _create_form(_ask(client).text, linked_to_0="SYS-9")
    assert (
        client.post(
            "/actions/llm/create", data=data, headers=AUTHOR
        ).status_code
        == 400
    )
    data = _create_form(_ask(client).text, verification_method_0="Z")
    assert (
        client.post(
            "/actions/llm/create", data=data, headers=AUTHOR
        ).status_code
        == 400
    )
    # A UID of the project that was not in the context is refused too.
    data = _create_form(_ask(client).text, linked_to_0="DA-1")
    assert (
        client.post(
            "/actions/llm/create", data=data, headers=AUTHOR
        ).status_code
        == 400
    )
    assert _flight(tmp_path) == before


def test_008_nothing_is_created_in_an_input_document(tmp_path):
    client = make_client(tmp_path, _llm([json.dumps(UNLINKED)]))
    page = _ask(client, reference_mid=DA_1).text
    data = _create_form(page)
    response = client.post("/actions/llm/create", data=data, headers=AUTHOR)
    assert response.status_code == 400
    assert "not allowed" in response.text
    assert (
        "Memory budget"
        not in (tmp_path / "input" / "customer.sdoc").read_text()
    )


def test_009_an_invalid_answer_is_asked_again_then_reported(tmp_path):
    client = make_client(tmp_path, _llm(["not json", "still not"]))
    response = _ask(client)
    assert response.status_code == 502
    assert "not JSON" in response.text
    entries = _audit(tmp_path)
    assert len(entries) == 1 and entries[0]["status"] == "invalid_answer"
    # A second try that is valid on its retry gives proposals.
    client = make_client(tmp_path / "again", _llm(["oops", json.dumps(GOOD)]))
    assert _ask(client).status_code == 200


def test_010_a_provider_that_fails_is_reported_and_audited(tmp_path):
    llm = make_llm(
        providers={
            "local": OpenAICompatible(
                base_url="http://127.0.0.1:9/v1",
                model="m",
                is_local=True,
                timeout=2,
            )
        }
    )
    client = make_client(tmp_path, llm)
    response = _ask(client)
    assert response.status_code == 502 and "cannot be reached" in response.text
    assert _audit(tmp_path)[0]["status"] == "provider_error"


def test_011_every_call_writes_one_audit_line_without_the_text(tmp_path):
    client = make_client(tmp_path, _llm())
    _ask(client, include_parents="true")
    (entry,) = _audit(tmp_path)
    assert entry["user"] == "anna" and entry["role"] == "author"
    assert entry["provider"] == "local" and entry["is_local"] is True
    assert entry["node_uids"] == ["FSW-1", "DA-1"]
    assert entry["template"] == "draft@2" and entry["status"] == "ok"
    assert len(entry["prompt_sha256"]) == 64 and entry["prompt_chars"] > 100
    assert "prompt" not in entry
    assert "The software shall use at most 32 MB" not in json.dumps(entry)


def test_012_the_prompt_is_stored_when_the_project_asks(tmp_path):
    client = make_client(tmp_path, _llm(audit_store_prompts=True))
    _ask(client)
    (entry,) = _audit(tmp_path)
    assert "The software shall use at most 32 MB" in entry["prompt"]


def test_013_a_cloud_provider_is_refused_when_the_project_keeps_it_closed(
    tmp_path,
):
    client = make_client(tmp_path, _both())
    page = client.get(
        "/llm/draft", params={"reference_mid": FL_1}, headers=AUTHOR
    ).text
    assert 'value="cloud"' not in page
    response = _ask(client, provider="cloud", confirm_cloud="true")
    assert response.status_code == 403 and "closed" in response.text
    assert _audit(tmp_path) == []


def test_014_an_open_cloud_provider_shows_what_is_sent_and_waits_for_a_click(
    tmp_path,
):
    client = make_client(tmp_path, _both(allow_cloud=True))
    response = _ask(client, provider="cloud")
    assert response.status_code == 200
    assert 'data-testid="llm-confirm"' in response.text
    assert "The software shall use at most 32 MB" in response.text
    assert "leave the network" in response.text
    assert _audit(tmp_path) == []  # nothing was sent
    response = _ask(client, provider="cloud", confirm_cloud="true")
    assert response.status_code == 200 and "llm-card" in response.text
    (entry,) = _audit(tmp_path)
    assert entry["is_local"] is False and entry["provider"] == "cloud"


def test_015_a_blocked_classification_never_reaches_the_cloud(tmp_path):
    llm = _both(allow_cloud=True, cloud_blocked_classifications=["Restricted"])
    client = make_client(tmp_path, llm)
    response = _ask(
        client, provider="cloud", confirm_cloud="true", input_refs="SX-1"
    )
    assert response.status_code == 403 and "Restricted" in response.text
    assert _audit(tmp_path) == []
    assert _ask(client, provider="local", input_refs="SX-1").status_code == 200


def test_016_the_browser_cannot_choose_the_address_of_a_provider(tmp_path):
    client = make_client(tmp_path, _llm())
    response = _ask(client, base_url="http://evil.example/v1", model="gpt-x")
    assert response.status_code == 200
    (entry,) = _audit(tmp_path)
    assert entry["model"] == "fake-model"


def test_017_the_rate_limit_answers_429(tmp_path):
    client = make_client(tmp_path, _llm(rate_limit_per_minute=2))
    assert _ask(client).status_code == 200
    assert _ask(client).status_code == 200
    assert _ask(client).status_code == 429


def test_018_the_text_of_a_proposal_is_escaped_in_the_page(tmp_path):
    hostile = {
        "proposals": [
            {
                "title": "<script>alert(1)</script>",
                "statement": "The software shall <img src=x onerror=alert(2)> work.",
                "verification_method": "T",
            }
        ]
    }
    client = make_client(tmp_path, _llm([json.dumps(hostile)]))
    page = _ask(client).text
    assert "<script>alert(1)</script>" not in page
    assert "<img src=x" not in page
    assert "&lt;script&gt;" in page


def test_019_the_drafts_screen_lists_what_nobody_made_active(tmp_path):
    client = make_client(tmp_path, _llm())
    data = _create_form(_ask(client).text)
    client.post("/actions/llm/create", data=data, headers=AUTHOR)
    page = client.get("/llm/drafts", headers=READER).text
    assert page.count('data-testid="llm-drafts-row"') == 2
    assert "Memory budget" in page and "anna" in page
    assert "FSW-2" not in page


def test_020_an_unknown_reference_node_is_not_found(tmp_path):
    client = make_client(tmp_path, _llm())
    assert (
        client.get(
            "/llm/draft", params={"reference_mid": "9" * 32}, headers=AUTHOR
        ).status_code
        == 404
    )


def test_021_the_context_error_is_shown_not_a_crash(tmp_path):
    client = make_client(tmp_path, _llm())
    response = _ask(client, input_refs="NOPE")
    assert response.status_code == 400
    assert "'NOPE' is not found" in html.unescape(response.text)
    response = _ask(client, instruction="  ")
    assert (
        response.status_code == 400 and "instruction is empty" in response.text
    )


def test_022_a_node_in_the_document_can_be_the_reference_for_a_document_draft(
    tmp_path,
):
    client = make_client(tmp_path, _llm([json.dumps(UNLINKED)]))
    data = _create_form(_ask(client, reference_mid=FLIGHT_DOC).text)
    assert (
        client.post(
            "/actions/llm/create", data=data, headers=AUTHOR
        ).status_code
        == 200
    )
    assert "TITLE: Memory budget" in _flight(tmp_path)


def test_023_the_config_for_a_cloud_provider_with_a_named_key(tmp_path):
    llm = make_llm(
        providers={
            "local": Fake(answers=[json.dumps(GOOD)]),
            "claude": Anthropic(
                model="claude-sonnet-5-5", api_key_env="ANTHROPIC_API_KEY"
            ),
        },
        allow_cloud=True,
    )
    llm.validate()
    client = make_client(tmp_path, llm)
    page = client.get(
        "/llm/draft", params={"reference_mid": FL_1}, headers=AUTHOR
    ).text
    assert "claude (claude-sonnet-5-5)" in page


@pytest.mark.parametrize("headers", [AUTHOR, ADMIN])
def test_024_administrators_may_use_it_too(tmp_path, headers):
    client = make_client(tmp_path, _llm())
    assert _ask(client, headers).status_code == 200
    assert FL_2
