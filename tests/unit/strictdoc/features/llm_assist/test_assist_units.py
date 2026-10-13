import json

import pytest

from strictdoc.features.llm.assist.commands import (
    COMMANDS,
    CommandError,
    catalogue,
    effective,
    parse_input,
)
from strictdoc.features.llm.assist.converters import (
    ConvertContext,
    convert,
    parse_answer,
)
from strictdoc.features.llm.assist.envelope import (
    EnvelopeError,
    parse_request,
)
from strictdoc.features.llm.assist.lint import lint
from strictdoc.features.llm.assist.mentions import find_mentions
from strictdoc.features.llm.prompts import load_assist_prompt
from strictdoc.features.llm.schema import OutputError


def _request(**target):
    return parse_request(
        {"v": 1, "scope": "field", "input": "/verify", "target": target}
    )


def test_001_a_command_is_parsed():
    parsed = parse_input("/rewrite ears keep the numbers")
    assert (parsed.command, parsed.arguments) == (
        "rewrite",
        "ears keep the numbers",
    )
    assert not parsed.implicit


def test_002_text_without_a_command_is_a_question():
    parsed = parse_input("What does REQ-1 mean?")
    assert (parsed.command, parsed.implicit) == ("ask", True)


def test_003_an_unknown_command_or_empty_input_is_refused():
    with pytest.raises(CommandError, match="Unknown command /nope"):
        parse_input("/nope x")
    with pytest.raises(CommandError):
        parse_input("   ")


def test_004_an_alias_is_replaced_by_its_command():
    effective_ = effective(parse_input("/ears keep it short"))
    assert (effective_.command, effective_.arguments) == (
        "rewrite",
        "ears keep it short",
    )


def test_005_every_command_has_a_prompt_and_a_catalogue_entry():
    for command in COMMANDS.values():
        if command.prompt:
            assert load_assist_prompt(command.prompt).version >= 1
    assert {entry["name"] for entry in catalogue("field")} >= {
        "rewrite",
        "verify",
        "comment",
        "req",
    }
    assert "req" not in {e["name"] for e in catalogue("document")}


def test_006_mentions_are_found():
    text = (
        "Write requirements from @DA1 §5.14.1, @icd1 and @REQ-12. "
        "Mail a@b.org is not a mention. Again @icd1, then @selection."
    )
    assert find_mentions(text) == [
        "DA1 §5.14.1",
        "icd1",
        "REQ-12",
        "selection",
    ]


def test_007_lint_finds_what_needs_no_model():
    findings = {
        (f.rule, f.quote)
        for f in lint(
            "The software shall be fast and shall log events as needed. TBD."
        )
    }
    assert ("R-AMBIG", "fast") in findings
    assert ("R-AMBIG", "as needed") in findings
    assert ("R-TBD", "TBD") in findings
    assert any(rule == "R-ATOMIC" for rule, _ in findings)
    assert [f.rule for f in lint("The software processes frames.")] == [
        "R-SHALL"
    ]
    assert lint("Le logiciel doit répondre en 2 s.") == []


def test_008_a_request_is_validated():
    request = _request(
        text="abcdef", selection={"text": "cd", "from": 2, "to": 4}
    )
    assert request.target.selection is not None
    # The browser and the server disagree on the text: no selection.
    wrong = _request(
        text="abcdef", selection={"text": "XX", "from": 2, "to": 4}
    )
    assert wrong.target.selection is None
    with pytest.raises(EnvelopeError):
        parse_request({"v": 2, "input": "x"})
    with pytest.raises(EnvelopeError):
        parse_request({"v": 1, "input": "x" * 5000})
    with pytest.raises(EnvelopeError):
        parse_request([])


def _context(name, text="The software shall be fast.", **kwargs):
    request = parse_request(
        {
            "v": 1,
            "input": "/" + name,
            "target": {"field": "STATEMENT", "text": text},
        }
    )
    return ConvertContext(
        command=COMMANDS[name],
        arguments="",
        request=request,
        original=text,
        **kwargs,
    )


def test_009_an_edit_becomes_a_replace_text():
    context = _context("rewrite", "The software shall boot in 2 s.")
    data = parse_answer(
        context,
        json.dumps({"text": "The software shall boot in 2 s.", "notes": "n"}),
    )
    assert convert(context, data).actions == []

    data = parse_answer(
        context, json.dumps({"text": "The software shall boot in 3 s.<b>x</b>"})
    )
    conversion = convert(context, data)
    action = conversion.actions[0]
    assert action.op == "replace_text"
    assert action.data["old"] == "The software shall boot in 2 s."
    assert action.data["new"] == "The software shall boot in 3 s.x"
    assert action.data["range"] is None
    assert any("Numbers or identifiers" in w for w in conversion.warnings)
    assert any("HTML" in w for w in conversion.warnings)


def test_010_a_bad_answer_is_refused_with_a_reason():
    context = _context("rewrite")
    for answer in ("not json", "[]", json.dumps({"text": ""}), '{"x": 1}'):
        with pytest.raises(OutputError):
            parse_answer(context, answer)
    with pytest.raises(OutputError, match="far longer"):
        convert(context, {"text": "x" * 30000})


def test_011_findings_are_checked_and_merged_with_the_lint():
    context = _context("verify", node_mid="n" * 32, can_add_comments=True)
    data = parse_answer(
        context,
        json.dumps(
            {
                "verdict": "warn",
                "findings": [
                    {
                        "severity": "bogus",
                        "rule": "R-INVENTED",
                        "quote": "not in the text",
                        "message": "A message.",
                    },
                    {
                        "severity": "error",
                        "rule": "R-AMBIG",
                        "quote": "fast",
                        "message": "Vague.",
                        "suggestion": "Give a value.",
                    },
                ],
            }
        ),
    )
    conversion = convert(context, data)
    rules = [(f.severity, f.rule, f.source) for f in conversion.findings]
    assert rules[0] == ("error", "R-AMBIG", "model")
    assert ("warning", "R-OTHER", "model") in rules
    # "fast" is also found by the lint: it is not listed twice.
    assert len([f for f in conversion.findings if f.quote == "fast"]) == 1
    assert any("not in the text" in w for w in conversion.warnings)
    assert all(a.op == "add_comment" for a in conversion.actions)
    assert len(conversion.actions) == len(conversion.findings)
    assert "Suggestion: Give a value." in conversion.actions[0].data["body"]


def test_012_without_a_saved_node_there_are_no_comment_actions():
    context = _context("verify")
    conversion = convert(context, parse_answer(context, '{"findings": []}'))
    assert conversion.actions == []
    assert any(f.rule == "R-AMBIG" for f in conversion.findings)
    assert any("Save the requirement first" in w for w in conversion.warnings)
