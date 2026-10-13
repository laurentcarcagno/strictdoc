"""
The JSON exchange of the assistant bar: what the browser sends, what the
server answers, and the typed operations the browser (or /actions/llm/apply)
carries out. The versions are in the field "v".

The answer of a model is never sent to the browser as it is: converters.py
turns it into operations that this module checks first.
"""

import re
import secrets
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

VERSION = 1

OP_REPLACE_TEXT = "replace_text"
OP_INSERT_NODE = "insert_node"
OP_ADD_COMMENT = "add_comment"
OP_MESSAGE = "message"
OPS = (OP_REPLACE_TEXT, OP_INSERT_NODE, OP_ADD_COMMENT, OP_MESSAGE)

SEVERITIES = ("error", "warning", "info")
MAX_INPUT = 4000
MAX_FIELD_TEXT = 60000
MAX_MENTIONS = 20
_RAW_HTML = re.compile(r"</?[a-zA-Z][^>\n]{0,200}>")


class EnvelopeError(ValueError):
    """The request of the browser is not valid."""


@dataclass
class Selection:
    text: str
    start: int
    end: int


@dataclass
class Target:
    document_mid: str = ""
    node_mid: str = ""
    # In the form of a new node: the node it will follow (or the document).
    reference_mid: str = ""
    field: str = ""
    text: str = ""
    selection: Optional[Selection] = None


@dataclass
class AssistRequest:
    scope: str
    input: str
    target: Target
    provider: str = ""
    cloud_confirmed: bool = False


def _string(data: Dict[str, Any], key: str, limit: int) -> str:
    value = data.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise EnvelopeError(f"'{key}' must be text.")
    if len(value) > limit:
        raise EnvelopeError(f"'{key}' is too long.")
    return value


def parse_request(data: Any) -> AssistRequest:
    """The request of the browser as an object. Raises EnvelopeError."""
    if not isinstance(data, dict):
        raise EnvelopeError("The request must be a JSON object.")
    if data.get("v") != VERSION:
        raise EnvelopeError(f"Unsupported version (expected {VERSION}).")
    scope = _string(data, "scope", 20) or "field"
    if scope not in ("field", "document"):
        raise EnvelopeError("'scope' is 'field' or 'document'.")
    raw_target = data.get("target") or {}
    if not isinstance(raw_target, dict):
        raise EnvelopeError("'target' must be an object.")
    selection: Optional[Selection] = None
    raw_selection = raw_target.get("selection")
    if isinstance(raw_selection, dict):
        start, end = raw_selection.get("from"), raw_selection.get("to")
        text = _string(raw_selection, "text", MAX_FIELD_TEXT)
        if (
            isinstance(start, int)
            and isinstance(end, int)
            and not isinstance(start, bool)
            and not isinstance(end, bool)
            and 0 <= start < end
            and len(text) > 0
        ):
            selection = Selection(text=text, start=start, end=end)
    target = Target(
        document_mid=_string(raw_target, "document_mid", 64),
        node_mid=_string(raw_target, "node_mid", 64),
        reference_mid=_string(raw_target, "reference_mid", 64),
        field=_string(raw_target, "field", 64),
        text=_string(raw_target, "text", MAX_FIELD_TEXT),
        selection=selection,
    )
    if selection is not None and (
        target.text[selection.start : selection.end] != selection.text
    ):
        # The browser and the server do not see the same text: ignore the
        # selection rather than rewrite the wrong words.
        target.selection = None
    return AssistRequest(
        scope=scope,
        input=_string(data, "input", MAX_INPUT),
        target=target,
        provider=_string(data, "provider", 64),
        cloud_confirmed=data.get("cloud_confirmed") is True,
    )


def new_id(prefix: str = "a") -> str:
    return prefix + secrets.token_hex(3)


@dataclass
class Action:
    op: str
    label: str
    # Ticked when the box is first shown.
    default: bool = True
    data: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=new_id)

    def to_json(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "op": self.op,
            "label": self.label,
            "default": self.default,
            **self.data,
        }


@dataclass
class Finding:
    severity: str
    rule: str
    quote: str
    message: str
    suggestion: str = ""
    # "lint" (no model) or "model".
    source: str = "model"
    id: str = field(default_factory=lambda: new_id("f"))

    def to_json(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity,
            "rule": self.rule,
            "quote": self.quote,
            "message": self.message,
            "suggestion": self.suggestion,
            "source": self.source,
        }


@dataclass
class AssistResult:
    command: str
    status: str = "ok"
    message: str = ""
    actions: List[Action] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)
    # Set when a cloud provider needs the confirmation of what is sent.
    confirmation: Optional[Dict[str, Any]] = None

    def to_json(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "v": VERSION,
            "status": self.status,
            "command": self.command,
            "message": self.message,
            "actions": [action_.to_json() for action_ in self.actions],
            "findings": [finding_.to_json() for finding_ in self.findings],
            "warnings": list(self.warnings),
            "meta": dict(self.meta),
        }
        if self.confirmation is not None:
            data["confirmation"] = self.confirmation
        return data


def clean_markdown(text: str, warnings: List[str]) -> str:
    """The text of a model with raw HTML tags removed (a warning says so)."""
    cleaned = _RAW_HTML.sub("", text)
    if cleaned != text:
        warnings.append("Raw HTML tags were removed from the proposal.")
    return cleaned.strip()


REQUEST_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["v", "input"],
    "properties": {
        "v": {"const": VERSION},
        "scope": {"enum": ["field", "document"]},
        "input": {"type": "string", "maxLength": MAX_INPUT},
        "target": {
            "type": "object",
            "properties": {
                "document_mid": {"type": "string"},
                "node_mid": {"type": "string"},
                "reference_mid": {"type": "string"},
                "field": {"type": "string"},
                "text": {"type": "string", "maxLength": MAX_FIELD_TEXT},
                "selection": {
                    "type": ["object", "null"],
                    "properties": {
                        "text": {"type": "string"},
                        "from": {"type": "integer", "minimum": 0},
                        "to": {"type": "integer", "minimum": 1},
                    },
                },
            },
        },
        "provider": {"type": "string"},
        "cloud_confirmed": {"type": "boolean"},
    },
}

RESULT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["v", "status", "command", "actions", "findings"],
    "properties": {
        "v": {"const": VERSION},
        "status": {"enum": ["ok", "error", "needs_confirmation"]},
        "command": {"type": "string"},
        "message": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "op", "label", "default"],
                "properties": {"op": {"enum": list(OPS)}},
            },
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "severity", "rule", "message"],
                "properties": {"severity": {"enum": list(SEVERITIES)}},
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
        "meta": {"type": "object"},
    },
}
