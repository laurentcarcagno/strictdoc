r"""
The golden set: about 20 cases (French cases in the style of REQ_02, English
cases from a customer-specification excerpt) with rule checks on the answer.

CI runs it with a fake provider that answers with the reference proposals of
each case (it tests the plumbing and the checks). A person runs it against a
real model to get a report:

    python -m strictdoc.features.llm.golden --base-url http://127.0.0.1:11434/v1 \\
        --model qwen2.5:3b [--cases fr-01,en-02] [--output report.md]

The checks (rules, not a judge): the statement says "shall" ("doit" in French),
once; no vague "and/or" or "etc."; a verification method of the project; only
UIDs of the material; no number that the material does not hold; a number of
proposals within the bounds of the case.
"""

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from strictdoc.features.llm.config import LLMConfig, OpenAICompatible
from strictdoc.features.llm.context import ContextItem, build_prompt_from_items
from strictdoc.features.llm.fake import FakeProvider
from strictdoc.features.llm.openai_compatible import OpenAICompatibleProvider
from strictdoc.features.llm.schema import (
    OutputError,
    Proposal,
    draft_proposals,
)
from strictdoc.features.llm.types import LLMError, LLMProvider

CASES_PATH = os.path.join(os.path.dirname(__file__), "golden", "cases.json")
_MODAL = {"en": r"\bshall\b", "fr": r"\b(doit|doivent)\b"}
_VAGUE = re.compile(
    r"and/or|et/ou|\betc\b\.?|as appropriate|if possible|si possible|"
    r"le cas [ée]ch[ée]ant|as needed|au besoin",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


@dataclass
class GoldenCase:
    id: str
    language: str
    pattern: str
    instruction: str
    items: List[ContextItem]
    reference: List[Dict[str, Any]]
    min_proposals: int = 1
    max_proposals: int = 5


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    failures: List[str] = field(default_factory=list)
    seconds: float = 0.0
    attempts: int = 0
    output_tokens: Optional[int] = None
    error: str = ""


def load_cases(path: str = CASES_PATH) -> "tuple[LLMConfig, List[GoldenCase]]":
    with open(path, encoding="utf-8") as file_:
        data = json.load(file_)
    llm = LLMConfig(
        providers={
            "golden": OpenAICompatible(
                base_url="http://127.0.0.1:11434/v1", model="-", is_local=True
            )
        },
        default="golden",
        verification_methods=data["verification_methods"],
    )
    cases = [
        GoldenCase(
            id=case_["id"],
            language=case_["language"],
            pattern=case_["pattern"],
            instruction=case_["instruction"],
            items=[
                ContextItem(
                    kind=item_["kind"],
                    uid=item_["uid"],
                    title=item_.get("title", ""),
                    text=item_["text"],
                )
                for item_ in case_["items"]
            ],
            reference=case_["reference"],
            min_proposals=case_["expect"]["min_proposals"],
            max_proposals=case_["expect"]["max_proposals"],
        )
        for case_ in data["cases"]
    ]
    return llm, cases


def _numbers(text: str) -> set:
    return {match_.replace(",", ".") for match_ in _NUMBER.findall(text)}


def check_proposals(
    case: GoldenCase, proposals: Sequence[Proposal]
) -> List[str]:
    """The rules that the proposals break, as readable lines."""
    failures: List[str] = []
    if not (case.min_proposals <= len(proposals) <= case.max_proposals):
        failures.append(
            f"{len(proposals)} proposal(s), expected {case.min_proposals} to "
            f"{case.max_proposals}"
        )
    modal = re.compile(_MODAL[case.language], re.IGNORECASE)
    # What the model may repeat: the text, and the UIDs and titles it cites.
    material = " ".join(
        f"{item_.uid} {item_.title} {item_.text}" for item_ in case.items
    )
    allowed_numbers = _numbers(material + " " + case.instruction)
    for number_, proposal_ in enumerate(proposals, start=1):
        text = proposal_.statement
        modals = len(modal.findall(text))
        if modals == 0:
            failures.append(f"#{number_}: no 'shall'/'doit' in the statement")
        elif modals > 1:
            failures.append(
                f"#{number_}: several requirements in one statement"
            )
        vague = _VAGUE.search(text)
        if vague:
            failures.append(f"#{number_}: vague wording '{vague.group(0)}'")
        invented = sorted(_numbers(text) - allowed_numbers)
        if invented:
            failures.append(
                f"#{number_}: number(s) not in the material: {', '.join(invented)}"
            )
    return failures


def run_case(
    provider: LLMProvider, llm: LLMConfig, case: GoldenCase
) -> CaseResult:
    built = build_prompt_from_items(
        items=case.items,
        llm=llm,
        instruction=case.instruction,
        pattern=case.pattern,
    )
    started = time.monotonic()
    try:
        draft = draft_proposals(
            provider,
            built.request,
            verification_methods=llm.verification_methods,
            known_uids=set(built.node_uids),
        )
    except (LLMError, OutputError) as exception_:
        return CaseResult(
            case_id=case.id,
            passed=False,
            failures=["no valid answer"],
            seconds=time.monotonic() - started,
            error=str(exception_),
        )
    failures = check_proposals(case, draft.proposals)
    return CaseResult(
        case_id=case.id,
        passed=len(failures) == 0,
        failures=failures,
        seconds=time.monotonic() - started,
        attempts=draft.attempts,
        output_tokens=draft.response.output_tokens,
    )


def fake_provider_for(case: GoldenCase) -> FakeProvider:
    """A provider that answers with the reference proposals of the case."""
    return FakeProvider([json.dumps({"proposals": case.reference})])


def run_golden(
    llm: LLMConfig,
    cases: Sequence[GoldenCase],
    provider: Optional[LLMProvider] = None,
) -> List[CaseResult]:
    return [
        run_case(provider or fake_provider_for(case_), llm, case_)
        for case_ in cases
    ]


def format_report(
    results: Sequence[CaseResult], provider: str = "fake", model: str = ""
) -> str:
    passed = sum(1 for result_ in results if result_.passed)
    lines = [
        f"# Golden set report: {provider} {model}".rstrip(),
        "",
        f"{passed} of {len(results)} cases pass all the rules.",
        "",
        "| Case | Result | Seconds | Calls | Output tokens | Problems |",
        "|---|---|---|---|---|---|",
    ]
    for result_ in results:
        problems = "; ".join(result_.failures)
        if result_.error:
            problems += f" ({result_.error[:120]})"
        lines.append(
            f"| {result_.case_id} | {'pass' if result_.passed else 'FAIL'} "
            f"| {result_.seconds:.1f} | {result_.attempts} "
            f"| {result_.output_tokens if result_.output_tokens is not None else ''} "
            f"| {problems} |"
        )
    total = sum(result_.seconds for result_ in results)
    lines += ["", f"Total time: {total:.0f} s."]
    return "\n".join(lines) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="strictdoc.features.llm.golden")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--cases", help="comma separated case ids")
    parser.add_argument("--output")
    parser.add_argument("--timeout", type=float, default=300.0)
    arguments = parser.parse_args(argv)
    llm, cases = load_cases()
    if arguments.cases:
        wanted = set(arguments.cases.split(","))
        cases = [case_ for case_ in cases if case_.id in wanted]
    # The runner is a developer tool for models that run on this network.
    provider = OpenAICompatibleProvider(
        "golden",
        OpenAICompatible(
            base_url=arguments.base_url,
            model=arguments.model,
            is_local=True,
            timeout=arguments.timeout,
        ),
    )
    results = run_golden(llm, cases, provider)
    report = format_report(results, "golden", arguments.model)
    if arguments.output:
        with open(arguments.output, "w", encoding="utf-8") as file_:
            file_.write(report)
    sys.stdout.write(report)
    return 0 if all(result_.passed for result_ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
