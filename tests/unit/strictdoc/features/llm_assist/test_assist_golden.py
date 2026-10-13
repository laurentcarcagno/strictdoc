import json

import pytest

from strictdoc.features.llm.assist import golden
from strictdoc.features.llm.fake import FakeProvider

CASES = golden.load_cases()


def test_001_the_set_covers_every_command_it_tests():
    commands = {case.command for case in CASES}
    assert commands == {
        "rewrite",
        "verify",
        "comment",
        "translate",
        "fix",
        "split",
    }
    assert len({case.id for case in CASES}) == len(CASES)


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_002_the_reference_answer_of_each_case_passes_its_checks(case):
    result = golden.run_case(golden.reference_provider(case), case)
    assert result.passed, result.failures


def test_003_the_checks_fail_on_bad_answers():
    by_id = {case.id: case for case in CASES}
    # A number is lost, the verb of obligation is missing, a vague word stays.
    bad = FakeProvider(
        [json.dumps({"text": "The software sends telemetry quickly."})]
    )
    result = golden.run_case(bad, by_id["rewrite-en-numbers"])
    assert not result.passed
    assert any("number" in failure for failure in result.failures)
    assert any("obligation" in failure for failure in result.failures)

    # An error on a clean requirement, a quote that is not in the text.
    noisy = FakeProvider(
        [
            json.dumps(
                {
                    "findings": [
                        {
                            "severity": "error",
                            "rule": "R-AMBIG",
                            "quote": "invented words",
                            "message": "Bad.",
                        }
                    ]
                }
            )
        ]
    )
    assert not golden.run_case(noisy, by_id["verify-en-clean"]).passed
    assert not golden.run_case(noisy, by_id["verify-en-vague"]).passed

    # Not JSON, twice: no valid answer.
    broken = FakeProvider(["not json"])
    result = golden.run_case(broken, by_id["rewrite-fr-vague"])
    assert not result.passed and result.failures == ["no valid answer"]


def test_004_a_report_is_written():
    results = golden.run_all(
        FakeProvider([json.dumps({"text": "x"})]), CASES[:2]
    )
    text = golden.report(results, "fake")
    assert text.startswith("# Assistant bar: golden set (fake)")
    assert "| /rewrite |" in text
