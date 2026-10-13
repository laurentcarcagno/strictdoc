"""
From the answer of a model to the operations of the envelope.

Each command has a small schema for the model (prompts/*.md). The parser of a
command checks that answer and raises OutputError for what is not acceptable
(the runner then asks once more, with the reason); the converter makes the
operations, dropping with a warning what cannot be trusted (a quote that is not
in the text, raw HTML, a number that disappeared).
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Collection, Dict, List, Optional

from strictdoc.features.llm.assist.commands import (
    COMMANDS,
    KIND_COMMENTS,
    KIND_CONSISTENCY,
    KIND_DRIFT,
    KIND_EDIT,
    KIND_FINDINGS,
    KIND_LINKS,
    KIND_NODES,
    KIND_SPLIT,
    KIND_TEST,
    Command,
)
from strictdoc.features.llm.assist.envelope import (
    OP_ADD_COMMENT,
    OP_ADD_RELATION,
    OP_INSERT_NODE,
    OP_REPLACE_TEXT,
    SEVERITIES,
    Action,
    AssistRequest,
    Finding,
    clean_markdown,
)
from strictdoc.features.llm.assist.lint import lint
from strictdoc.features.llm.schema import (
    OutputError,
    output_schema,
    parse_output,
)

MAX_FINDINGS = 8
MAX_SPLIT = 6
MAX_BODY = 1500
RULES = (
    "R-SHALL",
    "R-ATOMIC",
    "R-AMBIG",
    "R-VERIFIABLE",
    "R-ACTOR",
    "R-DESIGN",
    "R-TERM",
    "R-TBD",
    "R-COMPLETE",
    "R-NEG",
    "R-LANG",
    "R-RELEVANT",
    "R-DRIFT",
    "R-CONSISTENCY",
)
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_UID = re.compile(r"\b[A-Z][A-Z0-9]*-[A-Z0-9][\w-]*\b")


@dataclass
class Conversion:
    message: str = ""
    actions: List[Action] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ConvertContext:
    command: Command
    arguments: str
    request: AssistRequest
    # The statement of the node, for the findings and the comments.
    node_mid: str = ""
    # Where /req puts the new nodes: the mid of the node they follow, or of the
    # document when the reference is not a node ("" when it is not known).
    insert_ref: str = ""
    insert_after: bool = True
    # The node can take comments (it is saved and its grammar has COMMENT).
    can_add_comments: bool = False
    verification_methods: Collection[str] = ()
    known_uids: Optional[Collection[str]] = None
    # What the edit applies to: the selection, or the whole field.
    original: str = ""
    start: Optional[int] = None
    end: Optional[int] = None


def parse_json(text: str) -> Any:
    cleaned = text.strip()
    fence = _FENCE.match(cleaned)
    if fence is not None:
        cleaned = fence.group(1)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exception_:
        raise OutputError(f"The answer is not JSON: {exception_}") from (
            exception_
        )


def _object(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise OutputError("The answer must be a JSON object.")
    return data


def _text(data: Dict[str, Any], key: str, required: bool = True) -> str:
    value = data.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise OutputError(f"'{key}' must be text.")
    value = value.strip()
    if required and len(value) == 0:
        raise OutputError(f"'{key}' is missing.")
    if len(value) > 60000:
        raise OutputError(f"'{key}' is too long.")
    return value


# -- schemas for the providers that take one ----------------------------------


COMMANDS_BY_NAME = COMMANDS


def model_schema(command: Command, context: ConvertContext) -> Dict[str, Any]:
    if command.name == "rewrite":
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["text"],
        }
    if command.name == "fix":
        return model_schema(COMMANDS_BY_NAME["rewrite"], context)
    if command.name == "split":
        return {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "maxItems": MAX_SPLIT,
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "statement": {"type": "string"},
                        },
                        "required": ["statement"],
                    },
                }
            },
            "required": ["items"],
        }
    if command.name == "test":
        return {
            "type": "object",
            "properties": {
                "verification_method": {"type": "string"},
                "cases": {
                    "type": "array",
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "given": {"type": "string"},
                            "when": {"type": "string"},
                            "then": {"type": "string"},
                        },
                        "required": ["then"],
                    },
                },
            },
            "required": ["cases"],
        }
    if command.name == "trace":
        return {
            "type": "object",
            "properties": {
                "links": {
                    "type": "array",
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "properties": {
                            "uid": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["uid"],
                    },
                }
            },
            "required": ["links"],
        }
    if command.name == "retranslate":
        return {
            "type": "object",
            "properties": {
                "translation": {"type": "string"},
                "back": {"type": "string"},
                "differences": {
                    "type": "array",
                    "maxItems": MAX_FINDINGS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "original": {"type": "string"},
                            "back": {"type": "string"},
                            "message": {"type": "string"},
                        },
                        "required": ["message"],
                    },
                },
            },
            "required": ["translation", "differences"],
        }
    if command.name == "translate":
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }
    if command.name in ("verify", "consistency"):
        return {
            "type": "object",
            "properties": {
                "verdict": {"enum": ["pass", "warn", "fail"]},
                "findings": {
                    "type": "array",
                    "maxItems": MAX_FINDINGS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "severity": {"enum": list(SEVERITIES)},
                            "rule": {"type": "string"},
                            "quote": {"type": "string"},
                            "message": {"type": "string"},
                            "suggestion": {"type": "string"},
                        },
                        "required": ["severity", "rule", "message"],
                    },
                },
            },
            "required": ["findings"],
        }
    if command.name == "comment":
        return {
            "type": "object",
            "properties": {
                "comments": {
                    "type": "array",
                    "maxItems": 6,
                    "items": {
                        "type": "object",
                        "properties": {
                            "severity": {"enum": list(SEVERITIES)},
                            "quote": {"type": "string"},
                            "body": {"type": "string"},
                        },
                        "required": ["body"],
                    },
                }
            },
            "required": ["comments"],
        }
    if command.name == "req":
        return output_schema(context.verification_methods)
    return {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }


# -- parsers: the answer of the model, validated ------------------------------


def parse_answer(context: ConvertContext, text: str) -> Dict[str, Any]:
    """The answer of the model as a dictionary. Raises OutputError."""
    name = context.command.name
    if name == "req":
        proposals = parse_output(
            text,
            verification_methods=context.verification_methods,
            known_uids=context.known_uids,
        )
        return {"proposals": proposals}
    data = _object(parse_json(text))
    if name in ("rewrite", "translate", "fix"):
        _text(data, "text")
    elif name == "split":
        items = data.get("items")
        if not isinstance(items, list) or len(items) == 0:
            raise OutputError('The answer has no "items" list.')
        if len(items) > MAX_SPLIT:
            raise OutputError(f"More than {MAX_SPLIT} items.")
        for number_, item_ in enumerate(items, start=1):
            if not isinstance(item_, dict):
                raise OutputError(f"Item {number_} is not an object.")
            _text(item_, "statement")
            _text(item_, "title", required=False)
    elif name == "test":
        cases = data.get("cases")
        if not isinstance(cases, list):
            raise OutputError('The answer has no "cases" list.')
        for number_, item_ in enumerate(cases, start=1):
            if not isinstance(item_, dict):
                raise OutputError(f"Case {number_} is not an object.")
            _text(item_, "then")
    elif name == "trace":
        links = data.get("links")
        if not isinstance(links, list):
            raise OutputError('The answer has no "links" list.')
        known = context.known_uids
        for number_, item_ in enumerate(links, start=1):
            if not isinstance(item_, dict):
                raise OutputError(f"Link {number_} is not an object.")
            uid = _text(item_, "uid")
            if known is not None and uid not in known:
                raise OutputError(
                    f"Link {number_}: unknown UID {uid}. Use only the UIDs "
                    "of the material."
                )
    elif name == "retranslate":
        _text(data, "translation")
        differences = data.get("differences")
        if not isinstance(differences, list):
            raise OutputError('The answer has no "differences" list.')
        for number_, item_ in enumerate(differences, start=1):
            if not isinstance(item_, dict):
                raise OutputError(f"Difference {number_} is not an object.")
            _text(item_, "message")
    elif name in ("verify", "consistency"):
        findings = data.get("findings")
        if not isinstance(findings, list):
            raise OutputError('The answer has no "findings" list.')
        for number_, item_ in enumerate(findings, start=1):
            if not isinstance(item_, dict):
                raise OutputError(f"Finding {number_} is not an object.")
            _text(item_, "message")
    elif name == "comment":
        comments = data.get("comments")
        if not isinstance(comments, list):
            raise OutputError('The answer has no "comments" list.')
        for number_, item_ in enumerate(comments, start=1):
            if not isinstance(item_, dict):
                raise OutputError(f"Comment {number_} is not an object.")
            _text(item_, "body")
    else:
        _text(data, "answer")
    return data


# -- converters ----------------------------------------------------------------


def convert(context: ConvertContext, data: Dict[str, Any]) -> Conversion:
    """The operations that the answer stands for."""
    command = context.command
    if command.kind == KIND_EDIT:
        return _convert_edit(context, data)
    if command.kind == KIND_FINDINGS:
        return _convert_verify(context, data)
    if command.kind == KIND_COMMENTS:
        return _convert_comments(context, data)
    if command.kind == KIND_NODES:
        return _convert_nodes(context, data)
    if command.kind == KIND_CONSISTENCY:
        return _convert_consistency(data)
    if command.kind == KIND_SPLIT:
        return _convert_split(context, data)
    if command.kind == KIND_TEST:
        return _convert_test(context, data)
    if command.kind == KIND_LINKS:
        return _convert_links(context, data)
    if command.kind == KIND_DRIFT:
        return _convert_drift(context, data)
    conversion = Conversion()
    conversion.message = clean_markdown(
        str(data.get("answer", "")), conversion.warnings
    )
    return conversion


def _tokens(text: str) -> "set[str]":
    return set(_NUMBER.findall(text)) | set(_UID.findall(text))


def _convert_edit(context: ConvertContext, data: Dict[str, Any]) -> Conversion:
    conversion = Conversion()
    new = clean_markdown(str(data.get("text", "")), conversion.warnings)
    original = context.original
    if len(new) > max(2000, 4 * len(original)):
        raise OutputError("The proposed text is far longer than the original.")
    notes = str(data.get("notes", "") or "").strip()[:300]
    if new.strip() == original.strip():
        conversion.message = "No change proposed."
        return conversion
    missing = sorted(_tokens(original) - _tokens(new))
    if missing:
        conversion.warnings.append(
            "Numbers or identifiers of the original are not in the proposal: "
            + ", ".join(missing[:8])
            + ". Check before applying."
        )
    where = "selection" if context.start is not None else "text"
    verb = {"translate": "Translate", "fix": "Fix"}.get(
        context.command.name, "Rewrite"
    )
    conversion.message = notes or f"{verb} of the {where}."
    conversion.actions.append(
        Action(
            op=OP_REPLACE_TEXT,
            label=f"{verb} the {where}",
            data={
                "field": context.request.target.field,
                "range": (
                    {"from": context.start, "to": context.end}
                    if context.start is not None
                    else None
                ),
                "old": original,
                "new": new,
            },
        )
    )
    return conversion


def _anchored(
    quote: str, text: str, warnings: List[str]
) -> Optional[Dict[str, Any]]:
    if not quote:
        return None
    if quote in text:
        return {"text": quote[:200], "n": 1}
    warnings.append(f'The words "{quote[:40]}" are not in the text: no anchor.')
    return None


def _severity(value: Any) -> str:
    return value if value in SEVERITIES else "warning"


def _comment_action(
    context: ConvertContext,
    finding_id: str,
    severity: str,
    body: str,
    anchor: Optional[Dict[str, Any]],
) -> Action:
    return Action(
        op=OP_ADD_COMMENT,
        label="Add as a comment",
        default=severity != "info",
        data={
            "node": context.node_mid,
            "body": body[:MAX_BODY],
            "anchor": anchor,
            "severity": severity,
            "finding": finding_id,
        },
    )


def _convert_verify(
    context: ConvertContext, data: Dict[str, Any]
) -> Conversion:
    conversion = Conversion()
    text = context.request.target.text
    for item_ in data.get("findings", [])[:MAX_FINDINGS]:
        rule = item_.get("rule")
        conversion.findings.append(
            Finding(
                severity=_severity(item_.get("severity")),
                rule=rule if rule in RULES else "R-OTHER",
                quote=str(item_.get("quote") or "").strip(),
                message=_text(item_, "message"),
                suggestion=_text(item_, "suggestion", required=False),
            )
        )
    seen = {(f_.rule, f_.quote.lower()) for f_ in conversion.findings}
    for lint_ in lint(text):
        if (lint_.rule, lint_.quote.lower()) in seen:
            continue
        conversion.findings.append(
            Finding(
                severity=lint_.severity,
                rule=lint_.rule,
                quote=lint_.quote,
                message=lint_.message,
                suggestion=lint_.suggestion,
                source="lint",
            )
        )
    order = {name_: number_ for number_, name_ in enumerate(SEVERITIES)}
    conversion.findings.sort(key=lambda finding_: order[finding_.severity])
    for finding_ in conversion.findings:
        anchor = _anchored(finding_.quote, text, conversion.warnings)
        if anchor is None:
            finding_.quote = ""
        if context.can_add_comments:
            body = finding_.message + (
                f" Suggestion: {finding_.suggestion}"
                if finding_.suggestion
                else ""
            )
            conversion.actions.append(
                _comment_action(
                    context, finding_.id, finding_.severity, body, anchor
                )
            )
    count = len(conversion.findings)
    conversion.message = (
        "No problem found."
        if count == 0
        else f"{count} point{'s' if count > 1 else ''} to look at."
    )
    if count and not context.can_add_comments and context.node_mid == "":
        conversion.warnings.append(
            "Save the requirement first to turn the findings into comments."
        )
    return conversion


def _convert_comments(
    context: ConvertContext, data: Dict[str, Any]
) -> Conversion:
    conversion = Conversion()
    text = context.request.target.text
    for item_ in data.get("comments", [])[:6]:
        body = _text(item_, "body")
        severity = _severity(item_.get("severity"))
        anchor = _anchored(
            str(item_.get("quote") or "").strip(), text, conversion.warnings
        )
        if context.can_add_comments:
            conversion.actions.append(
                _comment_action(context, "", severity, body, anchor)
            )
        else:
            conversion.findings.append(
                Finding(severity, "", "", clean_markdown(body, []))
            )
    count = len(conversion.actions) + len(conversion.findings)
    conversion.message = (
        "No remark."
        if count == 0
        else f"{count} remark{'s' if count > 1 else ''} to tick."
    )
    if not context.can_add_comments and count:
        conversion.warnings.append(
            "Save the requirement first to add these remarks as comments."
        )
    return conversion


def _convert_nodes(context: ConvertContext, data: Dict[str, Any]) -> Conversion:
    conversion = Conversion()
    reference = context.insert_ref
    where = "after" if context.insert_after else "last_child"
    for proposal_ in data["proposals"]:
        conversion.actions.append(
            Action(
                op=OP_INSERT_NODE,
                label=proposal_.title,
                data={
                    "position": {"where": where, "ref": reference},
                    "node": {
                        "type": "REQUIREMENT",
                        "status": "Draft",
                        "fields": {
                            "TITLE": proposal_.title,
                            "STATEMENT": clean_markdown(
                                proposal_.statement, conversion.warnings
                            ),
                            "RATIONALE": proposal_.rationale,
                            "VERIFICATION_METHOD": proposal_.verification_method,
                        },
                        "linked_to": list(proposal_.linked_to),
                    },
                },
            )
        )
    count = len(conversion.actions)
    conversion.message = (
        f"{count} requirement{'s' if count > 1 else ''} proposed."
    )
    return conversion


def _convert_consistency(data: Dict[str, Any]) -> Conversion:
    conversion = Conversion()
    for item_ in data.get("findings", [])[:MAX_FINDINGS]:
        conversion.findings.append(
            Finding(
                severity=_severity(item_.get("severity")),
                rule="R-CONSISTENCY",
                quote="",
                message=_text(item_, "message"),
                suggestion=_text(item_, "suggestion", required=False),
            )
        )
    count = len(conversion.findings)
    conversion.message = (
        "No inconsistency found."
        if count == 0
        else f"{count} inconsistenc{'ies' if count > 1 else 'y'}."
    )
    return conversion


def _convert_split(context: ConvertContext, data: Dict[str, Any]) -> Conversion:
    conversion = Conversion()
    items = data["items"]
    whole = context.request.target.text
    if len(items) == 1:
        conversion.message = "The requirement is already atomic."
        return conversion
    first = clean_markdown(str(items[0]["statement"]), conversion.warnings)
    conversion.actions.append(
        Action(
            op=OP_REPLACE_TEXT,
            label="Keep the first part here",
            data={
                "field": context.request.target.field,
                "range": None,
                "old": whole,
                "new": first,
            },
        )
    )
    for item_ in items[1:]:
        statement = clean_markdown(str(item_["statement"]), conversion.warnings)
        title = str(item_.get("title") or "").strip() or statement[:60]
        conversion.actions.append(
            Action(
                op=OP_INSERT_NODE,
                label=title,
                data={
                    "position": {
                        "where": "after"
                        if context.insert_after
                        else "last_child",
                        "ref": context.insert_ref,
                    },
                    "node": {
                        "type": "REQUIREMENT",
                        "status": "Draft",
                        "fields": {
                            "TITLE": title,
                            "STATEMENT": statement,
                            "RATIONALE": "",
                            "VERIFICATION_METHOD": "",
                        },
                        "linked_to": [],
                    },
                },
            )
        )
    conversion.message = (
        f"Split into {len(items)} requirements: the first stays here, "
        f"{len(items) - 1} more are added after it as Draft."
    )
    if not context.insert_ref:
        conversion.warnings.append(
            "There is no place for the new requirements: nothing to insert."
        )
        conversion.actions = conversion.actions[:1]
    return conversion


def _convert_test(context: ConvertContext, data: Dict[str, Any]) -> Conversion:
    conversion = Conversion()
    method = str(data.get("verification_method") or "").strip()
    lines: List[str] = []
    if method:
        lines.append(f"**Verification method:** {method}")
    for number_, case_ in enumerate(data["cases"], start=1):
        name = str(case_.get("name") or f"Case {number_}").strip()
        lines.append(f"- **{name}**")
        for key_, label_ in (
            ("given", "Given"),
            ("when", "When"),
            ("then", "Then"),
        ):
            value = str(case_.get(key_) or "").strip()
            if value:
                lines.append(f"  {label_}: {value}")
    text = clean_markdown("\n".join(lines), conversion.warnings)
    conversion.message = text or "No case proposed."
    if context.can_add_comments and data["cases"]:
        conversion.actions.append(
            _comment_action(
                context,
                "",
                "info",
                "Proposed verification:\n" + text,
                None,
            )
        )
        conversion.actions[-1].label = "Add the cases as a comment"
        conversion.actions[-1].default = False
    return conversion


def _convert_links(context: ConvertContext, data: Dict[str, Any]) -> Conversion:
    conversion = Conversion()
    seen = set()
    for item_ in data["links"]:
        uid = str(item_["uid"]).strip()
        if uid in seen:
            continue
        seen.add(uid)
        reason = str(item_.get("reason") or "").strip()
        conversion.actions.append(
            Action(
                op=OP_ADD_RELATION,
                label=f"Parent: {uid}",
                data={
                    "node": context.node_mid,
                    "uid": uid,
                    "role": None,
                    "reason": reason[:300],
                },
            )
        )
    if not context.node_mid and conversion.actions:
        conversion.warnings.append(
            "Save the requirement first to add parents to it."
        )
        conversion.actions = []
    count = len(conversion.actions)
    conversion.message = (
        "No parent found among the mentions."
        if count == 0
        else f"{count} possible parent{'s' if count > 1 else ''}."
    )
    return conversion


def _convert_drift(context: ConvertContext, data: Dict[str, Any]) -> Conversion:
    conversion = Conversion()
    translation = clean_markdown(
        str(data.get("translation", "")), conversion.warnings
    )
    for item_ in data.get("differences", [])[:MAX_FINDINGS]:
        quote = str(item_.get("original") or "").strip()
        conversion.findings.append(
            Finding(
                severity="warning",
                rule="R-DRIFT",
                quote=quote if quote in context.request.target.text else "",
                message=_text(item_, "message"),
                suggestion=str(item_.get("back") or "").strip()[:300],
            )
        )
    count = len(conversion.findings)
    head = (
        "The meaning is kept."
        if count == 0
        else f"{count} difference{'s' if count > 1 else ''} of meaning."
    )
    conversion.message = f"{head}\n\n**Translation:** {translation}"
    return conversion


Parser = Callable[[ConvertContext, str], Dict[str, Any]]


# -- the answers of the document jobs -------------------------------------------


def parse_review(text: str, batch_uids: Collection[str]) -> Dict[str, Any]:
    """The comments of a batch of requirements. Raises OutputError."""
    data = _object(parse_json(text))
    comments = data.get("comments")
    if not isinstance(comments, list):
        raise OutputError('The answer has no "comments" list.')
    for number_, item_ in enumerate(comments, start=1):
        if not isinstance(item_, dict):
            raise OutputError(f"Comment {number_} is not an object.")
        uid = _text(item_, "node")
        if uid not in batch_uids:
            raise OutputError(
                f"Comment {number_}: {uid} is not one of the requirements "
                "of the batch."
            )
        _text(item_, "body")
    return data


def parse_trace_batch(
    text: str, batch_uids: Collection[str], candidate_uids: Collection[str]
) -> Dict[str, Any]:
    """The links of a batch of requirements. Raises OutputError."""
    data = _object(parse_json(text))
    links = data.get("links")
    if not isinstance(links, list):
        raise OutputError('The answer has no "links" list.')
    for number_, item_ in enumerate(links, start=1):
        if not isinstance(item_, dict):
            raise OutputError(f"Link {number_} is not an object.")
        node = _text(item_, "node")
        uid = _text(item_, "uid")
        if node not in batch_uids:
            raise OutputError(f"Link {number_}: {node} is not in the batch.")
        if uid not in candidate_uids:
            raise OutputError(
                f"Link {number_}: unknown UID {uid}. Use only the UIDs of "
                "the material."
            )
    return data


def parse_topics(text: str) -> List[Dict[str, str]]:
    """The topics of the plan of /write. Raises OutputError."""
    data = _object(parse_json(text))
    topics = data.get("topics")
    if not isinstance(topics, list) or len(topics) == 0:
        raise OutputError('The answer has no "topics" list.')
    result: List[Dict[str, str]] = []
    for number_, item_ in enumerate(topics[:12], start=1):
        if not isinstance(item_, dict):
            raise OutputError(f"Topic {number_} is not an object.")
        result.append(
            {
                "title": _text(item_, "title"),
                "scope": _text(item_, "scope", required=False),
            }
        )
    return result


def parse_translation_batch(
    text: str, wanted: Dict[str, Collection[str]]
) -> Dict[str, Any]:
    """
    The translated texts of a batch: {"nodes": {ref: {field: text}}}. `wanted`
    gives the fields of each ref of the batch. Raises OutputError.
    """
    data = _object(parse_json(text))
    nodes = data.get("nodes")
    if not isinstance(nodes, list) or len(nodes) == 0:
        raise OutputError('The answer has no "nodes" list.')
    result: Dict[str, Dict[str, str]] = {}
    for number_, item_ in enumerate(nodes, start=1):
        if not isinstance(item_, dict):
            raise OutputError(f"Node {number_} is not an object.")
        ref = _text(item_, "ref")
        if ref not in wanted:
            raise OutputError(
                f"Node {number_}: the ref {ref} is not in the batch. Keep "
                "the refs you were given."
            )
        fields = item_.get("fields")
        if not isinstance(fields, dict):
            raise OutputError(f"Node {ref} has no fields.")
        cleaned: Dict[str, str] = {}
        for name_, value_ in fields.items():
            if name_ not in wanted[ref]:
                raise OutputError(
                    f"Node {ref}: the field {name_} was not given. Keep the "
                    "field names."
                )
            if not isinstance(value_, str) or not value_.strip():
                raise OutputError(f"Node {ref}: {name_} must be text.")
            cleaned[name_] = value_
        result[ref] = cleaned
    return {"nodes": result}


def parse_glossary(text: str, batch_uids: Collection[str]) -> Dict[str, Any]:
    """The terms of a batch of requirements. Raises OutputError."""
    data = _object(parse_json(text))
    terms = data.get("terms")
    if not isinstance(terms, list):
        raise OutputError('The answer has no "terms" list.')
    cleaned: List[Dict[str, str]] = []
    for number_, item_ in enumerate(terms[:15], start=1):
        if not isinstance(item_, dict):
            raise OutputError(f"Term {number_} is not an object.")
        term = _text(item_, "term")
        definition = _text(item_, "definition")
        uid = _text(item_, "uid", required=False)
        cleaned.append(
            {
                "term": term[:80],
                "definition": definition[:400],
                "uid": uid if uid in batch_uids else "",
            }
        )
    return {"terms": cleaned}
