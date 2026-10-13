"""
Checks that need no model: the obligation verb, vague words, unresolved TBD,
several obligations in one statement, a passive form with no actor. They run
first in /verify and /comment, so that the command is useful when the model is
weak or down. Every finding quotes the exact words of the text.
"""

import re
from dataclasses import dataclass
from typing import List

OBLIGATION = re.compile(r"\b(shall|doit|doivent)\b", re.IGNORECASE)
_VAGUE = (
    "as appropriate",
    "as needed",
    "if possible",
    "and/or",
    "user-friendly",
    "state-of-the-art",
    "appropriate",
    "adequate",
    "sufficient",
    "reasonable",
    "quickly",
    "fast",
    "easy",
    "flexible",
    "optimal",
    "minimize",
    "maximize",
    "etc.",
    "si possible",
    "et/ou",
    "approprié",
    "appropriée",
    "adéquat",
    "suffisant",
    "raisonnable",
    "rapidement",
    "rapide",
    "facile",
    "convivial",
    "optimal",
    "minimiser",
    "maximiser",
)
_VAGUE_PATTERN = re.compile(
    "|".join(
        (
            r"(?<![\w])" + re.escape(word_) + r"(?![\w])"
            if word_[-1].isalnum()
            else r"(?<![\w])" + re.escape(word_)
        )
        for word_ in sorted(_VAGUE, key=len, reverse=True)
    ),
    re.IGNORECASE,
)
_TBD = re.compile(r"\b(TBD|TBC|TBS)\b|à définir|à confirmer")
_PASSIVE = re.compile(
    r"\b(shall be|doit être|doivent être)\s+\w+(ed|és?|ées?|ie?s?|it)\b(?!\s+by\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LintFinding:
    severity: str
    rule: str
    quote: str
    message: str
    suggestion: str


def lint(text: str) -> List[LintFinding]:
    """The findings of the deterministic checks on a statement."""
    findings: List[LintFinding] = []
    body = text.strip()
    if len(body) == 0:
        return findings
    obligations = list(OBLIGATION.finditer(body))
    if len(obligations) == 0:
        findings.append(
            LintFinding(
                "error",
                "R-SHALL",
                "",
                "The statement has no verb of obligation.",
                'Use "shall" ("doit" or "doivent" in French) with one subject.',
            )
        )
    elif len(obligations) > 1:
        findings.append(
            LintFinding(
                "warning",
                "R-ATOMIC",
                obligations[1].group(0),
                f"The statement holds {len(obligations)} obligations.",
                "Split it into one requirement per obligation.",
            )
        )
    seen = set()
    for match_ in _VAGUE_PATTERN.finditer(body):
        word = match_.group(0)
        if word.lower() in seen:
            continue
        seen.add(word.lower())
        findings.append(
            LintFinding(
                "warning",
                "R-AMBIG",
                word,
                f'"{word}" is vague and cannot be verified.',
                "Say the condition, the value and the unit.",
            )
        )
    for match_ in _TBD.finditer(body):
        findings.append(
            LintFinding(
                "warning",
                "R-TBD",
                match_.group(0),
                "An open value is left in the statement.",
                "Resolve it, or keep a rationale that says who decides and when.",
            )
        )
    passive = _PASSIVE.search(body)
    if passive is not None:
        findings.append(
            LintFinding(
                "info",
                "R-ACTOR",
                passive.group(0),
                "A passive form hides the actor.",
                "Name who or what performs the action.",
            )
        )
    return findings
