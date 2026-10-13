"""
The commands of the assistant bar: one registry that feeds the help, the
autocomplete, the checks of the server and the user guide.

A command is typed in the bar as "/name arguments". A text with no command is
a question (/ask): it changes nothing.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from strictdoc.features.llm.assist.envelope import AssistResult
from strictdoc.features.roles.roles import (
    ROLE_AUTHOR,
    ROLE_READER,
    ROLE_REVIEWER,
)

SCOPE_FIELD = "field"
SCOPE_DOCUMENT = "document"

# What a command gives back.
KIND_EDIT = "edit"  # replace_text
KIND_FINDINGS = "findings"  # findings and add_comment actions
KIND_COMMENTS = "comments"  # add_comment actions
KIND_NODES = "nodes"  # insert_node actions
KIND_ANSWER = "answer"  # a message
KIND_LOCAL = "local"  # answered by the server, no model
KIND_SPLIT = "split"  # replace_text and insert_node actions
KIND_TEST = "test"  # a message and an optional comment
KIND_LINKS = "links"  # add_relation actions
KIND_DRIFT = "drift"  # findings only
KIND_JOB = "job"  # a long job on a whole document: write, review, trace
KIND_CONSISTENCY = "consistency"  # findings with no text of their own


@dataclass(frozen=True)
class Command:
    name: str
    scopes: Tuple[str, ...]
    usage: str
    summary: str
    # The lowest project role. "reviewer" means: an author, a project reviewer,
    # or a reviewer that the document names (see features/reviewers).
    role: str
    kind: str
    # The prompt file (prompts/<prompt>.md); empty for a local command.
    prompt: str = ""


COMMANDS: Dict[str, Command] = {
    command_.name: command_
    for command_ in (
        Command(
            "rewrite",
            (SCOPE_FIELD,),
            "/rewrite [clearer|concise|formal|ears] [notes]",
            "Rewrites the text (or the selection) and shows the difference.",
            ROLE_AUTHOR,
            KIND_EDIT,
            "rewrite",
        ),
        Command(
            "ears",
            (SCOPE_FIELD,),
            "/ears [notes]",
            "Rewrites the text in the EARS form that fits (same as /rewrite ears).",
            ROLE_AUTHOR,
            KIND_EDIT,
            "rewrite",
        ),
        Command(
            "verify",
            (SCOPE_FIELD,),
            "/verify [focus]",
            "Checks syntax, clarity and quality; lists the problems and changes nothing.",
            ROLE_REVIEWER,
            KIND_FINDINGS,
            "verify",
        ),
        Command(
            "comment",
            (SCOPE_FIELD,),
            "/comment [focus]",
            "Writes the remarks of a reviewer; the ones you tick become comments.",
            ROLE_REVIEWER,
            KIND_COMMENTS,
            "comment",
        ),
        Command(
            "translate",
            (SCOPE_FIELD,),
            "/translate <language>",
            "Translates the text (or the selection), keeping UIDs, units and terms.",
            ROLE_AUTHOR,
            KIND_EDIT,
            "translate",
        ),
        Command(
            "req",
            (SCOPE_FIELD,),
            "/req <request> [@REQ-1 @icd1 ...]",
            "Writes new requirements (as Draft) from your request and the mentions.",
            ROLE_AUTHOR,
            KIND_NODES,
            "req",
        ),
        Command(
            "split",
            (SCOPE_FIELD,),
            "/split",
            "Splits a compound requirement into atomic ones (the others as Draft).",
            ROLE_AUTHOR,
            KIND_SPLIT,
            "split",
        ),
        Command(
            "fix",
            (SCOPE_FIELD,),
            "/fix [notes]",
            "Rewrites the text to solve the points of the last /verify.",
            ROLE_AUTHOR,
            KIND_EDIT,
            "fix",
        ),
        Command(
            "test",
            (SCOPE_FIELD,),
            "/test",
            "Proposes a verification method and acceptance cases.",
            ROLE_REVIEWER,
            KIND_TEST,
            "test",
        ),
        Command(
            "trace",
            (SCOPE_FIELD, SCOPE_DOCUMENT),
            "/trace @REQ-1 @DA1 ...",
            "Proposes parents among the mentioned requirements and sections (of the whole document in the document bar).",
            ROLE_AUTHOR,
            KIND_LINKS,
            "trace",
        ),
        Command(
            "retranslate",
            (SCOPE_FIELD,),
            "/retranslate <language>",
            "Translates and translates back, and lists where the meaning drifted.",
            ROLE_REVIEWER,
            KIND_DRIFT,
            "retranslate",
        ),
        Command(
            "write",
            (SCOPE_DOCUMENT,),
            "/write <what to write, from @sources>",
            "Plans and writes the requirements of a document from the sources you mention (as Draft).",
            ROLE_AUTHOR,
            KIND_JOB,
            "write_topic",
        ),
        Command(
            "review",
            (SCOPE_DOCUMENT,),
            "/review [focus]",
            "Reads every requirement and proposes comments to tick.",
            ROLE_REVIEWER,
            KIND_JOB,
            "review",
        ),
        Command(
            "summarize",
            (SCOPE_DOCUMENT,),
            "/summarize [@section]",
            "Summarises the document, or the sections you mention.",
            ROLE_READER,
            KIND_ANSWER,
            "summarize",
        ),
        Command(
            "consistency",
            (SCOPE_DOCUMENT,),
            "/consistency [@documents]",
            "Looks for contradictions, duplicates and term clashes.",
            ROLE_REVIEWER,
            KIND_CONSISTENCY,
            "consistency",
        ),
        Command(
            "explain",
            (SCOPE_FIELD,),
            "/explain",
            "Explains the text in plain words.",
            ROLE_READER,
            KIND_ANSWER,
            "explain",
        ),
        Command(
            "ask",
            (SCOPE_FIELD, SCOPE_DOCUMENT),
            "/ask <question> [@mentions]",
            "Answers a question about the text and the mentions; changes nothing.",
            ROLE_READER,
            KIND_ANSWER,
            "ask",
        ),
        Command(
            "help",
            (SCOPE_FIELD, SCOPE_DOCUMENT),
            "/help",
            "Lists the commands.",
            ROLE_READER,
            KIND_LOCAL,
        ),
    )
}

# A command that is another one with its argument filled in.
ALIASES: Dict[str, Tuple[str, str]] = {"ears": ("rewrite", "ears")}

DEFAULT_COMMAND = "ask"


@dataclass(frozen=True)
class ParsedInput:
    command: str
    arguments: str
    # True when the user wrote no command: the text is a question.
    implicit: bool = False


class CommandError(ValueError):
    """The input is not a command that exists."""


def parse_input(text: str) -> ParsedInput:
    """
    "/rewrite ears keep the numbers" -> rewrite, "ears keep the numbers".
    Raises CommandError for an unknown command or an empty input.
    """
    stripped = text.strip()
    if len(stripped) == 0:
        raise CommandError("Type a command (/help lists them) or a question.")
    if not stripped.startswith("/"):
        return ParsedInput(DEFAULT_COMMAND, stripped, implicit=True)
    name, _, arguments = stripped[1:].partition(" ")
    name = name.lower()
    if name not in COMMANDS:
        known = ", ".join("/" + name_ for name_ in sorted(COMMANDS))
        raise CommandError(f"Unknown command /{name}. Known: {known}.")
    return ParsedInput(name, arguments.strip())


def effective(parsed: ParsedInput) -> ParsedInput:
    """The command that really runs (an alias is replaced), with its arguments."""
    alias = ALIASES.get(parsed.command)
    if alias is None:
        return parsed
    command, style = alias
    return ParsedInput(command, (style + " " + parsed.arguments).strip())


def catalogue(scope: Optional[str] = None) -> List[Dict[str, str]]:
    """The commands for the autocomplete of the browser."""
    return [
        {
            "name": command_.name,
            "usage": command_.usage,
            "summary": command_.summary,
            "role": command_.role,
        }
        for command_ in COMMANDS.values()
        if scope is None or scope in command_.scopes
    ]


def help_result(command: Command) -> AssistResult:
    lines = ["**Commands**", ""]
    for entry_ in catalogue(None):
        lines.append(f"- `{entry_['usage']}`: {entry_['summary']}")
    lines += [
        "",
        (
            "Type `@` to mention a requirement (`@REQ-12`), a document "
            "(`@icd1`), a section of an input document (`@DA1 §5.2`) or the "
            "selection (`@selection`)."
        ),
    ]
    return AssistResult(command=command.name, message="\n".join(lines))
