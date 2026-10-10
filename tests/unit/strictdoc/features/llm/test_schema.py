import json

import pytest

from strictdoc.features.llm.fake import FakeProvider
from strictdoc.features.llm.schema import (
    MAX_PROPOSALS,
    OutputError,
    draft_proposals,
    output_schema,
    parse_output,
)
from strictdoc.features.llm.types import LLMError, LLMRequest

METHODS = ["A", "I", "R", "T"]


def _answer(*items):
    return json.dumps({"proposals": list(items)})


GOOD = {
    "title": "Start",
    "statement": "The software shall start within 2 s.",
    "rationale": "Boot time.",
    "verification_method": "T",
    "linked_to": ["SYS-1"],
}


def test_001_a_valid_answer_gives_proposals():
    proposals = parse_output(
        _answer(GOOD), verification_methods=METHODS, known_uids={"SYS-1"}
    )
    assert len(proposals) == 1
    assert proposals[0].title == "Start"
    assert proposals[0].verification_method == "T"
    assert proposals[0].linked_to == ["SYS-1"]


def test_002_a_fenced_answer_or_a_bare_list_is_accepted():
    assert (
        parse_output("```json\n" + _answer(GOOD) + "\n```")[0].title == "Start"
    )
    assert parse_output(json.dumps([GOOD]))[0].title == "Start"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not json", "not JSON"),
        ("{}", 'no "proposals"'),
        ('{"proposals": "x"}', 'no "proposals"'),
        ('{"proposals": []}', "no proposal"),
        ('{"proposals": [1]}', "not an object"),
        (_answer({"statement": "x"}), "'title' is missing"),
        (_answer({"title": "x"}), "'statement' is missing"),
        (_answer({"title": 3, "statement": "x"}), "must be text"),
        (_answer({"title": "t", "statement": "x" * 5000}), "too long"),
        (
            _answer({"title": "t", "statement": "s", "linked_to": "A"}),
            "list of UIDs",
        ),
        (
            _answer({"title": "t", "statement": "s", "linked_to": [1]}),
            "list of UIDs",
        ),
    ],
)
def test_003_a_wrong_shape_is_refused(text, message):
    with pytest.raises(OutputError, match=message):
        parse_output(text)


def test_004_the_verification_method_must_be_one_of_the_project():
    bad = dict(GOOD, verification_method="X")
    with pytest.raises(OutputError, match="not one of A, I, R, T"):
        parse_output(_answer(bad), verification_methods=METHODS)
    missing = {k: v for k, v in GOOD.items() if k != "verification_method"}
    with pytest.raises(OutputError, match="'verification_method' is missing"):
        parse_output(_answer(missing), verification_methods=METHODS)
    # A project without methods accepts none.
    assert parse_output(_answer(missing))[0].verification_method == ""


def test_005_uids_are_checked_against_the_project():
    with pytest.raises(OutputError, match="unknown UID SYS-9"):
        parse_output(
            _answer(dict(GOOD, linked_to=["SYS-1", "SYS-9"])),
            verification_methods=METHODS,
            known_uids={"SYS-1"},
        )
    # Without a list of known UIDs the caller checks.
    assert parse_output(_answer(GOOD), verification_methods=METHODS)


def test_006_too_many_proposals_are_refused():
    with pytest.raises(OutputError, match="More than"):
        parse_output(_answer(*[GOOD] * (MAX_PROPOSALS + 1)))


def test_007_the_schema_lists_the_project_methods():
    schema = output_schema(METHODS)
    item = schema["properties"]["proposals"]["items"]
    assert item["properties"]["verification_method"]["enum"] == METHODS
    assert "verification_method" in item["required"]
    assert (
        "verification_method"
        not in output_schema([])["properties"]["proposals"]["items"][
            "properties"
        ]
    )


REQUEST = LLMRequest(system="s", user="u")


def test_008_a_valid_first_answer_takes_one_call():
    provider = FakeProvider([_answer(GOOD)])
    draft = draft_proposals(provider, REQUEST, verification_methods=METHODS)
    assert draft.attempts == 1 and len(provider.requests) == 1


def test_009_an_invalid_answer_is_asked_again_once_with_the_reason():
    provider = FakeProvider(["I think you should...", _answer(GOOD)])
    draft = draft_proposals(provider, REQUEST, verification_methods=METHODS)
    assert draft.attempts == 2
    assert "refused: The answer is not JSON" in provider.requests[1].user
    assert provider.requests[1].user.startswith("u")


def test_010_two_invalid_answers_are_reported():
    provider = FakeProvider(["nope", "still nope"])
    with pytest.raises(OutputError):
        draft_proposals(provider, REQUEST)
    assert len(provider.requests) == 2


def test_011_a_provider_failure_is_not_retried():
    provider = FakeProvider([LLMError("down")])
    with pytest.raises(LLMError, match="down"):
        draft_proposals(provider, REQUEST)
    assert len(provider.requests) == 1


def test_012_every_call_is_reported_to_the_observer():
    provider = FakeProvider(["nope", _answer(GOOD)])
    calls = []
    draft_proposals(
        provider,
        REQUEST,
        verification_methods=METHODS,
        on_call=lambda _request, _response, error: calls.append(error),
    )
    assert len(calls) == 2 and calls[0] and calls[1] is None
