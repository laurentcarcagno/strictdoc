"""
The tool loop of the assistant: the model chooses which tools of the knowledge
base to call, StrictDoc runs them, and what they return becomes context of the
command that follows.

The model never reaches the base. A tool outside the allow-list is refused, a
result is neutralised, cut and put between BEGIN KB-DATA and END KB-DATA lines
as data, and the loop makes at most ``max_steps`` rounds. A model that asks for
no tool in the first round (it may not support them) is replaced by a plain
search with the question. A cloud provider never runs the loop: it receives the
result of that plain search, which the user confirms before it is sent.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from strictdoc.features.kb.client import KBClient, KBError, KBResult
from strictdoc.features.kb.config import KBConfig
from strictdoc.features.llm.assist.runner import Calls
from strictdoc.features.llm.context import TRUNCATED, ContextItem, neutralise
from strictdoc.features.llm.prompts import _read_versioned
from strictdoc.features.llm.types import (
    LLMError,
    LLMProvider,
    LLMRequest,
    Message,
    ToolCall,
)

KIND_KB = "kb"
GATHER_PROMPT = "kb_gather"
MAX_CALLS_PER_ROUND = 4
GATHER_TOKENS = 1500


@dataclass
class ToolRecord:
    """One call to the base, for the audit and for the sources shown."""

    tool: str
    arguments: Dict[str, Any]
    ok: bool
    chars: int = 0
    request_id: str = ""
    note: str = ""


@dataclass
class Gathered:
    items: List[ContextItem] = field(default_factory=list)
    records: List[ToolRecord] = field(default_factory=list)
    # The sources, one line each: "ISIS-SYS-IF-249 ed. 9.0 §3.2".
    sources: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    rounds: int = 0
    # True when a plain search replaced the loop.
    retrieval: bool = False
    prompt_label: str = ""
    classification: str = ""
    # The results as the server sent them (for /kb).
    results: List[KBResult] = field(default_factory=list)


def citation_line(citation: Dict[str, Any]) -> str:
    """The source of a citation of the server: doc_ref, edition, section and, when known, the page of the source PDF."""
    line = str(citation.get("doc_ref") or "?")
    if citation.get("edition"):
        line += f" ed. {citation['edition']}"
    if citation.get("section"):
        line += f" §{citation['section']}"
    if citation.get("page"):
        line += f", p. {citation['page']}"
    return line


def digest(arguments: Dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(arguments, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def render_result(result: KBResult, limit: int) -> str:
    """
    The result of a tool as the text the model reads: neutralised, cut to
    `limit` characters, between lines that mark it as data.
    """
    body = {
        "result": result.data,
        "citations": [citation_line(c_) for c_ in result.citations],
        "warnings": result.warnings,
    }
    text = neutralise(json.dumps(body, ensure_ascii=False, default=str))
    cut = len(text) > limit
    if cut:
        text = text[: max(limit - len(TRUNCATED), 0)] + TRUNCATED
    elif result.truncated:
        text += TRUNCATED
    return f"BEGIN KB-DATA tool={result.tool}\n{text}\nEND KB-DATA"


def _item(result: KBResult, config: KBConfig, mission: str) -> ContextItem:
    sources = [citation_line(c_) for c_ in result.citations[:3]]
    return ContextItem(
        kind=KIND_KB,
        # No uid: a uid of the base is not a node that a proposal may link to.
        uid="",
        title=f"{result.tool} " + "; ".join(sources),
        text=render_result(result, config.max_tool_chars),
        document_title=mission,
    )


def _add(
    gathered: Gathered,
    result: KBResult,
    config: KBConfig,
    classification: str,
) -> None:
    gathered.results.append(result)
    item = _item(result, config, config.mission)
    item.classification = classification
    used = sum(len(i_.text) for i_ in gathered.items)
    if used + len(item.text) > config.max_gathered_chars:
        gathered.notes.append(
            "The base returned more than the context can hold: some results were left out."
        )
        return
    gathered.items.append(item)
    for citation_ in result.citations:
        if not citation_.get("doc_ref"):
            continue  # not a document: nothing to cite
        line = citation_line(citation_)
        if line not in gathered.sources:
            gathered.sources.append(line)


def _record(
    gathered: Gathered,
    result: Optional[KBResult],
    tool: str,
    arguments: Dict[str, Any],
    note: str = "",
) -> None:
    gathered.records.append(
        ToolRecord(
            tool=tool,
            arguments=arguments,
            ok=bool(result and result.ok),
            chars=len(json.dumps(result.data)) if result else 0,
            request_id=result.request_id if result else "",
            note=note or (result.message if result and not result.ok else ""),
        )
    )


def retrieve(
    *,
    client: KBClient,
    config: KBConfig,
    user: str,
    groups: Sequence[str],
    question: str,
    classification: str,
    gathered: Optional[Gathered] = None,
) -> Gathered:
    """One search with the question, no model: the safety net and the cloud path."""
    gathered = gathered or Gathered()
    gathered.retrieval = True
    if "search" not in config.tools or not question.strip():
        return gathered
    arguments: Dict[str, Any] = {
        "query": question[:300],
        "mission": config.mission,
        "limit": 5,
    }
    try:
        result = client.call("search", arguments, user=user, groups=groups)
    except KBError as exception_:
        gathered.notes.append(f"The knowledge base was not read: {exception_}")
        _record(gathered, None, "search", arguments, str(exception_))
        return gathered
    _record(gathered, result, "search", arguments)
    if result.ok:
        _add(gathered, result, config, classification)
    else:
        gathered.notes.append(f"The knowledge base said: {result.message}")
    return gathered


def gather(
    *,
    provider: LLMProvider,
    client: KBClient,
    config: KBConfig,
    user: str,
    groups: Sequence[str],
    request_text: str,
    context_text: str,
    classification: str,
    calls: Calls,
) -> Gathered:
    """
    Runs the loop with `provider` (a model on this network). Raises nothing
    when the base or the model fails: the notes say so and the command goes on
    with what was found.
    """
    gathered = Gathered()
    version, system = _read_versioned(GATHER_PROMPT)
    gathered.prompt_label = f"{GATHER_PROMPT}@{version}"
    try:
        definitions = client.tool_definitions(user=user, groups=groups)
    except KBError as exception_:
        gathered.notes.append(f"The knowledge base was not read: {exception_}")
        return gathered
    tools = tuple(
        {
            "name": d_["name"],
            "description": str(d_.get("description", "")),
            "input_schema": d_.get("inputSchema", {"type": "object"}),
        }
        for d_ in definitions
    )
    if not tools:
        gathered.notes.append("The knowledge base offers no tool.")
        return gathered
    allowed = {t_["name"] for t_ in tools}
    first_turn = (
        f"Mission: {config.mission} (the tools use it; do not change it).\n\n"
        f"Request of the engineer:\n{neutralise(request_text)}\n\n"
        "Text being worked on (data):\n"
        f"BEGIN text\n{neutralise(context_text[:3000])}\nEND"
    )
    messages: List[Message] = []
    deadline = time.monotonic() + config.timeout * config.max_steps
    for round_ in range(config.max_steps):
        if time.monotonic() > deadline:
            gathered.notes.append(
                "The search in the base took too long and was stopped."
            )
            break
        llm_request = LLMRequest(
            system=system,
            user=first_turn,
            max_tokens=GATHER_TOKENS,
            temperature=0.0,
            tools=tools,
            messages=tuple(messages),
        )
        try:
            response = provider.complete(llm_request)
        except LLMError as exception_:
            calls.append((llm_request, None, str(exception_)))
            gathered.notes.append(
                f"The model could not search the base: {exception_}"
            )
            break
        calls.append((llm_request, response, None))
        gathered.rounds += 1
        if not response.tool_calls:
            if round_ == 0:
                # A model with no tool calling: search with the question.
                return retrieve(
                    client=client,
                    config=config,
                    user=user,
                    groups=groups,
                    question=request_text,
                    classification=classification,
                    gathered=gathered,
                )
            break
        selected = response.tool_calls[:MAX_CALLS_PER_ROUND]
        messages.append(
            Message(
                role="assistant",
                content=response.text,
                tool_calls=tuple(selected),
            )
        )
        for call_ in selected:
            messages.append(
                Message(
                    role="tool",
                    tool_call_id=call_.id,
                    content=_run_tool(
                        client,
                        config,
                        call_,
                        allowed,
                        user,
                        groups,
                        classification,
                        gathered,
                    ),
                )
            )
    else:
        gathered.notes.append(
            f"The search in the base stopped after {config.max_steps} rounds."
        )
    return gathered


def _run_tool(
    client: KBClient,
    config: KBConfig,
    call: ToolCall,
    allowed: "set[str]",
    user: str,
    groups: Sequence[str],
    classification: str,
    gathered: Gathered,
) -> str:
    # The mission is the one of the configuration, whatever the model asks.
    arguments = {k_: v_ for k_, v_ in call.arguments.items() if k_ != "mission"}
    arguments["mission"] = config.mission
    if call.name not in allowed or call.name not in config.tools:
        _record(
            gathered,
            None,
            call.name,
            arguments,
            "refused: not in the allow-list",
        )
        return f"BEGIN KB-DATA tool={neutralise(call.name)}\nThis tool is not allowed.\nEND KB-DATA"
    try:
        result = client.call(call.name, arguments, user=user, groups=groups)
    except KBError as exception_:
        _record(gathered, None, call.name, arguments, str(exception_))
        gathered.notes.append(f"The knowledge base was not read: {exception_}")
        return f"BEGIN KB-DATA tool={call.name}\nThe base cannot be read now.\nEND KB-DATA"
    _record(gathered, result, call.name, arguments)
    if not result.ok:
        return f"BEGIN KB-DATA tool={call.name}\nError: {neutralise(result.message)}\nEND KB-DATA"
    _add(gathered, result, config, classification)
    return render_result(result, config.max_tool_chars)


def mission_row(
    client: KBClient, config: KBConfig, user: str, groups: Sequence[str]
) -> Optional[Dict[str, Any]]:
    """The mission of the configuration as this person sees it, or None."""
    for row_ in client.missions(user=user, groups=groups):
        if row_.get("code") == config.mission:
            return row_
    return None


def model_allowed(row: Dict[str, Any], provider_name: str, model: str) -> bool:
    """True when the mission lists the provider (by name or by model)."""
    listed = row.get("allowed_models")
    names: List[str] = (
        [str(n_) for n_ in listed] if isinstance(listed, list) else []
    )
    return provider_name in names or model in names
