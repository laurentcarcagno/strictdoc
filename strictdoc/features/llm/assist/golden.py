r"""
The golden set of the assistant bar: a few cases per command (French and
English) with rule checks on what the model gives back (not a judge).

CI runs it with a fake provider that answers with the reference answer of each
case (it tests the harness and the checks). A person runs it against a real
model to get a report:

    python -m strictdoc.features.llm.assist.golden \\
        --base-url http://127.0.0.1:11434/v1 --model qwen2.5:3b \\
        [--cases rewrite-fr-vague,verify-en-clean] [--output report.md]

The checks: the answer is valid JSON of the schema (and how many attempts it
took); a rewrite keeps the numbers and the identifiers, keeps the verb of
obligation of its language and has no vague word; a translation is in the
target language; /verify finds the planted defect with a quote that is in the
text and has no error on a clean requirement; /comment gives remarks with quotes
that are in the text; /split gives atomic statements.
"""

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from strictdoc.features.llm.assist.commands import COMMANDS
from strictdoc.features.llm.assist.converters import (
    ConvertContext,
    convert,
    model_schema,
    parse_answer,
)
from strictdoc.features.llm.assist.envelope import parse_request
from strictdoc.features.llm.assist.lint import OBLIGATION, lint
from strictdoc.features.llm.assist.prompting import build_user_prompt
from strictdoc.features.llm.assist.runner import Calls, ask_validated
from strictdoc.features.llm.config import OpenAICompatible
from strictdoc.features.llm.fake import FakeProvider
from strictdoc.features.llm.openai_compatible import OpenAICompatibleProvider
from strictdoc.features.llm.prompts import load_assist_prompt
from strictdoc.features.llm.schema import OutputError
from strictdoc.features.llm.types import LLMError, LLMProvider, LLMRequest

CASES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "golden", "assist_cases.json"
)
_MODAL = {"en": r"\bshall\b", "fr": r"\b(doit|doivent)\b"}
_LANG_WORDS = {
    "en": re.compile(r"\b(the|shall|every|each|any|with)\b", re.IGNORECASE),
    "fr": re.compile(
        r"\b(le|la|les|doit|doivent|toute?|chaque|dont|est)\b", re.IGNORECASE
    ),
}
_TOKENS = re.compile(r"\d+(?:[.,]\d+)?|\b[A-Z][A-Z0-9]*-[A-Z0-9][\w-]*\b")
_VAGUE = re.compile(
    r"and/or|et/ou|\betc\b\.?|as appropriate|if possible|si possible|"
    r"as needed|au besoin|raisonnable|appropriate|rapide|quickly|fast",
    re.IGNORECASE,
)


@dataclass
class AssistCase:
    id: str
    command: str
    arguments: str
    text: str
    reference: Dict[str, Any]
    expect: Dict[str, Any]


@dataclass
class AssistResult:
    case_id: str
    command: str
    passed: bool
    failures: List[str] = field(default_factory=list)
    seconds: float = 0.0
    attempts: int = 0
    error: str = ""


def load_cases(path: str = CASES_PATH) -> List[AssistCase]:
    with open(path, encoding="utf-8") as file_:
        data = json.load(file_)
    return [AssistCase(**item_) for item_ in data]


def build(case: AssistCase) -> "tuple[ConvertContext, LLMRequest]":
    command = COMMANDS[case.command]
    request = parse_request(
        {
            "v": 1,
            "input": f"/{case.command} {case.arguments}",
            "target": {"field": "STATEMENT", "text": case.text},
        }
    )
    context = ConvertContext(
        command=command,
        arguments=case.arguments,
        request=request,
        original=case.text,
    )
    problems = "\n".join(f"- {f_.rule}: {f_.message}" for f_ in lint(case.text))
    user = build_user_prompt(
        command=command,
        arguments=case.arguments,
        field="STATEMENT",
        uid="REQ-1",
        original=case.text,
        whole_text=case.text,
        has_selection=False,
        material="(none)",
        problems=problems or "- improve the clarity",
    )
    llm_request = LLMRequest(
        system=load_assist_prompt(command.prompt).system,
        user=user,
        schema=model_schema(command, context),
    )
    return context, llm_request


def _tokens(text: str) -> "set[str]":
    return set(_TOKENS.findall(text))


def check(
    case: AssistCase, context: ConvertContext, data: Dict[str, Any]
) -> List[str]:
    """The failures of the rules on one answer."""
    failures: List[str] = []
    expect = case.expect
    conversion = convert(context, data)
    new_texts: List[str] = []
    for action_ in conversion.actions:
        if action_.op == "replace_text":
            new_texts.append(action_.data["new"])
        elif action_.op == "insert_node":
            new_texts.append(action_.data["node"]["fields"]["STATEMENT"])
    if case.command in ("rewrite", "translate", "fix") and not new_texts:
        new_texts = [case.text]  # "no change" is an answer
    joined = "\n".join(new_texts)
    if expect.get("preserve") and any(
        "Numbers or identifiers" in w_ for w_ in conversion.warnings
    ):
        failures.append("a number or an identifier was lost")
    if expect.get("preserve_all"):
        if not _tokens(case.text) <= _tokens(joined):
            failures.append("a number was lost")
    modal = expect.get("modal")
    if modal and new_texts:
        for text_ in new_texts:
            if re.search(_MODAL[modal], text_, re.IGNORECASE) is None:
                failures.append(
                    f"no verb of obligation ({modal}) in: {text_[:60]}"
                )
    if expect.get("no_vague") and _VAGUE.search(joined):
        failures.append("a vague word is still there")
    lang = expect.get("lang")
    if lang and not _LANG_WORDS[lang].search(joined):
        failures.append(f"the text is not in {lang}")
    if expect.get("atomic"):
        for text_ in new_texts:
            if len(OBLIGATION.findall(text_)) > 1:
                failures.append("several obligations remain")
    if case.command == "verify":
        model_findings = [
            f_ for f_ in conversion.findings if f_.source == "model"
        ]
        # What the user sees is the model and the checks together.
        rules = {f_.rule for f_ in conversion.findings}
        wanted = expect.get("rules_any")
        if wanted and not rules & set(wanted):
            failures.append(
                f"none of {', '.join(wanted)} reported (got {sorted(rules) or 'nothing'})"
            )
        if expect.get("clean") and any(
            f_.severity == "error" for f_ in model_findings
        ):
            failures.append("an error was reported on a clean requirement")
        if expect.get("quotes") and any(
            "not in the text" in w_ for w_ in conversion.warnings
        ):
            failures.append("a quote is not in the text")
    if case.command == "comment":
        count = len(conversion.actions) + len(conversion.findings)
        if count < expect.get("min", 1):
            failures.append("no remark")
        if expect.get("quotes") and any(
            "not in the text" in w_ for w_ in conversion.warnings
        ):
            failures.append("a quote is not in the text")
    if case.command == "split":
        count = len(data.get("items", []))
        if not expect.get("min", 1) <= count <= expect.get("max", 6):
            failures.append(f"{count} items")
    return failures


def run_case(provider: LLMProvider, case: AssistCase) -> AssistResult:
    context, request = build(case)
    started = time.monotonic()
    calls: Calls = []
    try:
        answer = ask_validated(
            provider,
            request,
            lambda text: parse_answer(context, text),
            calls,
        )
    except (LLMError, OutputError) as exception_:
        return AssistResult(
            case.id,
            case.command,
            False,
            ["no valid answer"],
            time.monotonic() - started,
            len(calls),
            str(exception_),
        )
    try:
        failures = check(case, context, answer.data)
    except OutputError as exception_:
        failures = [str(exception_)]
    return AssistResult(
        case.id,
        case.command,
        not failures,
        failures,
        time.monotonic() - started,
        answer.attempts,
    )


def run_all(
    provider: LLMProvider, cases: Sequence[AssistCase]
) -> List[AssistResult]:
    return [run_case(provider, case_) for case_ in cases]


def reference_provider(case: AssistCase) -> FakeProvider:
    return FakeProvider([json.dumps(case.reference)])


def report(results: Sequence[AssistResult], model: str) -> str:
    lines = [f"# Assistant bar: golden set ({model})", ""]
    by_command: Dict[str, List[AssistResult]] = {}
    for result_ in results:
        by_command.setdefault(result_.command, []).append(result_)
    lines.append("| Command | Passed | Retries needed | Seconds |")
    lines.append("|---|---|---|---|")
    for command_, items_ in by_command.items():
        passed = sum(item_.passed for item_ in items_)
        retries = sum(item_.attempts > 1 for item_ in items_)
        seconds = sum(item_.seconds for item_ in items_)
        lines.append(
            f"| /{command_} | {passed} of {len(items_)} | {retries} | {seconds:.0f} |"
        )
    total = sum(result_.passed for result_ in results)
    lines += ["", f"**Total: {total} of {len(results)}**", ""]
    for result_ in results:
        if not result_.passed:
            lines.append(
                f"- `{result_.case_id}`: "
                + "; ".join(result_.failures)
                + (f" ({result_.error})" if result_.error else "")
            )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--cases", default="")
    parser.add_argument("--commands", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    cases = load_cases()
    if args.cases:
        wanted = set(args.cases.split(","))
        cases = [case_ for case_ in cases if case_.id in wanted]
    if args.commands:
        wanted_commands = set(args.commands.split(","))
        cases = [case_ for case_ in cases if case_.command in wanted_commands]
    provider = OpenAICompatibleProvider(
        "golden",
        OpenAICompatible(
            base_url=args.base_url,
            model=args.model,
            is_local=True,
            timeout=300.0,
        ),
    )
    results = run_all(provider, cases)
    text = report(results, args.model)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as file_:
            file_.write(text + "\n")
    print(text)  # noqa: T201
    return 0 if all(result_.passed for result_ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
