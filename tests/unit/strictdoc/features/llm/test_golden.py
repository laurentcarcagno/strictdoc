import json

import pytest

from strictdoc.features.llm.fake import FakeProvider
from strictdoc.features.llm.golden import (
    check_proposals,
    format_report,
    load_cases,
    run_case,
    run_golden,
)
from strictdoc.features.llm.schema import Proposal

LLM, CASES = load_cases()


def test_001_the_set_has_twenty_cases_in_both_languages():
    assert len(CASES) == 20
    assert {case.language for case in CASES} == {"fr", "en"}
    assert len({case.id for case in CASES}) == 20
    assert sum(case.language == "fr" for case in CASES) == 10


def test_002_the_reference_answers_pass_every_rule():
    results = run_golden(LLM, CASES)
    failing = {r.case_id: r.failures for r in results if not r.passed}
    assert failing == {}
    assert all(result.attempts == 1 for result in results)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_003_each_case_builds_a_prompt_with_its_material_only(case):
    provider = FakeProvider([json.dumps({"proposals": case.reference})])
    run_case(provider, LLM, case)
    prompt = provider.requests[0].user
    for item in case.items:
        assert item.text.split(".")[0][:30] in prompt
    assert case.instruction in prompt


def _case(language="en", **kwargs):
    case = next(c for c in CASES if c.language == language)
    for name, value in kwargs.items():
        setattr(case, name, value)
    return case


def _proposal(statement):
    return Proposal(title="t", statement=statement, verification_method="T")


def test_004_a_statement_without_the_modal_verb_fails():
    case = _case("en")
    failures = check_proposals(case, [_proposal("The software starts fast.")])
    assert any("no 'shall'" in f for f in failures)
    case = _case("fr")
    assert any(
        "no 'shall'" in f
        for f in check_proposals(case, [_proposal("Le logiciel démarre.")])
    )


def test_005_two_requirements_in_one_statement_fail():
    case = _case("en")
    failures = check_proposals(
        case, [_proposal("The software shall boot and it shall log.")]
    )
    assert any("several requirements" in f for f in failures)
    case = _case("fr")
    assert any(
        "several requirements" in f
        for f in check_proposals(
            case, [_proposal("Il doit démarrer et il doit journaliser.")]
        )
    )


@pytest.mark.parametrize(
    "wording", ["and/or", "etc.", "as appropriate", "if possible"]
)
def test_006_vague_wording_fails(wording):
    failures = check_proposals(
        _case("en"), [_proposal(f"The software shall do A {wording}.")]
    )
    assert any("vague wording" in f for f in failures)


def test_007_an_invented_number_fails_and_a_given_one_passes():
    case = next(c for c in CASES if c.id == "en-02")
    ok = _proposal("The software shall enter safe mode below 6.5 V within 1 s.")
    assert check_proposals(case, [ok]) == []
    bad = _proposal(
        "The software shall enter safe mode below 7.5 V within 2 s."
    )
    failures = check_proposals(case, [bad])
    assert any("7.5" in f and "2" in f for f in failures)


def test_008_the_number_of_proposals_is_bounded():
    case = next(c for c in CASES if c.id == "en-02")
    assert any(
        "0 proposal" in f or "expected" in f for f in check_proposals(case, [])
    )
    many = [_proposal("The software shall enter safe mode.")] * 6
    assert any("6 proposal(s)" in f for f in check_proposals(case, many))


def test_009_an_unknown_uid_or_method_is_a_failed_case_not_a_crash():
    case = next(c for c in CASES if c.id == "en-02")
    bad_uid = json.dumps(
        {
            "proposals": [
                {
                    "title": "t",
                    "statement": "The software shall enter safe mode.",
                    "verification_method": "T",
                    "linked_to": ["INVENTED-1"],
                }
            ]
        }
    )
    result = run_case(FakeProvider([bad_uid]), LLM, case)
    assert not result.passed and "unknown UID INVENTED-1" in result.error
    assert result.attempts == 0


def test_010_the_report_is_a_markdown_table():
    results = run_golden(LLM, CASES[:2])
    report = format_report(results, "fake", "m")
    assert "2 of 2 cases pass all the rules." in report
    assert "| fr-01 | pass |" in report
    failing = run_case(FakeProvider(["nope", "nope"]), LLM, CASES[0])
    text = format_report([failing])
    assert "FAIL" in text and "no valid answer" in text
