from strictdoc.features.kb.client import KBResult
from strictdoc.features.llm.assist.kb_drift import (
    RULE_CHANGED,
    RULE_EDITION,
    RULE_GONE,
    RULE_UNCHECKED,
    check,
    find_citations,
)

TEXT = "The OBC shall send the heartbeat packet every 500 ms."
FOOTER = (
    "> — ISIS-IF-249-0100, ISIS-SYS-IF-249-CNES ed. 9.0 §3.2 "
    "(kb://isis/ISIS-SYS-IF-249-CNES/9.0/3.2)"
)


def _now(text=TEXT, edition="9.0", **kwargs):
    return KBResult(
        tool="get_requirement",
        ok=True,
        data={"text": text},
        citations=[{"doc_ref": "ISIS-SYS-IF-249-CNES", "edition": edition}],
        **kwargs,
    )


def test_001_a_quote_of_cite_is_found_with_its_text():
    text = f"Before.\n\n> {TEXT}\n{FOOTER}\n\nAfter."
    (citation,) = find_citations(text)
    assert citation.req_id == "ISIS-IF-249-0100"
    assert (citation.mission, citation.edition, citation.section) == (
        "isis",
        "9.0",
        "3.2",
    )
    assert citation.quote == TEXT


def test_002_a_quote_of_several_lines_and_two_quotes():
    text = f"> one\n> two\n{FOOTER}\n\n> {TEXT}\n{FOOTER}"
    first, second = find_citations(text)
    assert first.quote == "one\ntwo" and second.quote == TEXT


def test_003_text_that_is_not_a_quote_is_ignored():
    assert find_citations("A link kb://isis/x/1/2 in a sentence.") == []
    assert find_citations("> — ID, a (kb://isis/only/two)") == []


def test_004_a_quote_that_still_matches_has_no_finding():
    (citation,) = find_citations(f"> {TEXT}\n{FOOTER}")
    assert check(citation, _now(text=TEXT + "  ")) == []


def test_005_the_four_ways_a_quote_drifts():
    (citation,) = find_citations(f"> {TEXT}\n{FOOTER}")
    rules = lambda current: [r_ for _s, r_, _m in check(citation, current)]
    assert rules(KBResult(tool="x", ok=False)) == [RULE_GONE]
    assert rules(_now(edition="10.0")) == [RULE_EDITION]
    assert rules(_now(text="Every 250 ms.")) == [RULE_CHANGED]
    assert rules(_now(text="Every 250 ms.", edition="10.0")) == [
        RULE_EDITION,
        RULE_CHANGED,
    ]
    assert rules(_now(truncated=True)) == [RULE_UNCHECKED]
    assert rules(None) == [RULE_UNCHECKED]
