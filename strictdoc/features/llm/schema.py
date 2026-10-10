"""
What the model has to answer: proposals of requirements, as JSON, and the
validation of that answer. The answer of a model is never trusted: it is
parsed, checked against the schema, and the UIDs it names are checked against
the project by the caller.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Collection, Dict, List, Optional

from strictdoc.features.llm.types import (
    LLMError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
)

MAX_PROPOSALS = 10
MAX_TEXT = 4000
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


class OutputError(ValueError):
    """The answer of the model is not what was asked."""


@dataclass
class Proposal:
    title: str
    statement: str
    rationale: str = ""
    verification_method: str = ""
    linked_to: List[str] = field(default_factory=list)


def output_schema(verification_methods: Collection[str]) -> Dict[str, Any]:
    """The JSON schema of the answer; the methods are the project's."""
    properties: Dict[str, Any] = {
        "title": {"type": "string"},
        "statement": {"type": "string"},
        "rationale": {"type": "string"},
        "linked_to": {"type": "array", "items": {"type": "string"}},
    }
    required = ["title", "statement"]
    if verification_methods:
        properties["verification_method"] = {
            "type": "string",
            "enum": sorted(verification_methods),
        }
        required.append("verification_method")
    return {
        "type": "object",
        "properties": {
            "proposals": {
                "type": "array",
                "maxItems": MAX_PROPOSALS,
                "items": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            }
        },
        "required": ["proposals"],
    }


def parse_output(
    text: str,
    *,
    verification_methods: Collection[str] = (),
    known_uids: Optional[Collection[str]] = None,
) -> List[Proposal]:
    """
    The proposals of an answer. Raises OutputError for text that is not JSON,
    a wrong shape, a missing or oversized field, a verification method that
    the project does not have, or (when `known_uids` is given) a UID that does
    not exist.
    """
    cleaned = text.strip()
    fence = _FENCE.match(cleaned)
    if fence is not None:
        cleaned = fence.group(1)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exception_:
        raise OutputError(f"The answer is not JSON: {exception_}") from (
            exception_
        )
    if isinstance(data, list):
        data = {"proposals": data}
    if not isinstance(data, dict) or not isinstance(
        data.get("proposals"), list
    ):
        raise OutputError('The answer has no "proposals" list.')
    items = data["proposals"]
    if len(items) == 0:
        raise OutputError("The answer holds no proposal.")
    if len(items) > MAX_PROPOSALS:
        raise OutputError(f"More than {MAX_PROPOSALS} proposals.")
    proposals = [
        _proposal(item_, number_, verification_methods, known_uids)
        for number_, item_ in enumerate(items, start=1)
    ]
    return proposals


def _text(item: Dict[str, Any], key: str, number: int, required: bool) -> str:
    value = item.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise OutputError(f"Proposal {number}: '{key}' must be text.")
    value = value.strip()
    if required and len(value) == 0:
        raise OutputError(f"Proposal {number}: '{key}' is missing.")
    if len(value) > MAX_TEXT:
        raise OutputError(f"Proposal {number}: '{key}' is too long.")
    return value


def _proposal(
    item: Any,
    number: int,
    verification_methods: Collection[str],
    known_uids: Optional[Collection[str]],
) -> Proposal:
    if not isinstance(item, dict):
        raise OutputError(f"Proposal {number} is not an object.")
    method = _text(
        item, "verification_method", number, bool(verification_methods)
    )
    if verification_methods and method not in verification_methods:
        raise OutputError(
            f"Proposal {number}: verification method '{method}' is not one "
            f"of {', '.join(sorted(verification_methods))}."
        )
    linked = item.get("linked_to", [])
    if linked is None:
        linked = []
    if not isinstance(linked, list) or not all(
        isinstance(uid_, str) for uid_ in linked
    ):
        raise OutputError(
            f"Proposal {number}: 'linked_to' must be a list of UIDs."
        )
    linked = [uid_.strip() for uid_ in linked if uid_.strip()]
    if known_uids is not None:
        unknown = [uid_ for uid_ in linked if uid_ not in known_uids]
        if unknown:
            raise OutputError(
                f"Proposal {number}: unknown UID {', '.join(unknown)}."
            )
    return Proposal(
        title=_text(item, "title", number, True),
        statement=_text(item, "statement", number, True),
        rationale=_text(item, "rationale", number, False),
        verification_method=method,
        linked_to=linked,
    )


@dataclass
class Draft:
    proposals: List[Proposal]
    response: LLMResponse
    # How many calls it took (2 when the first answer was invalid).
    attempts: int = 1


def draft_proposals(
    provider: LLMProvider,
    request: LLMRequest,
    *,
    verification_methods: Collection[str] = (),
    known_uids: Optional[Collection[str]] = None,
    on_call: Optional[
        Callable[[LLMRequest, Optional[LLMResponse], Optional[str]], None]
    ] = None,
) -> Draft:
    """
    Asks the provider and validates the answer. An invalid answer is asked
    again once, with the reason; a second invalid answer is reported.
    Raises LLMError (the provider failed) or OutputError.
    """
    attempt_request = request
    last_error = ""
    for attempt in (1, 2):
        try:
            response = provider.complete(attempt_request)
        except LLMError as exception_:
            if on_call is not None:
                on_call(attempt_request, None, str(exception_))
            raise
        try:
            proposals = parse_output(
                response.text,
                verification_methods=verification_methods,
                known_uids=known_uids,
            )
        except OutputError as exception_:
            last_error = str(exception_)
            if on_call is not None:
                on_call(attempt_request, response, last_error)
            attempt_request = LLMRequest(
                system=request.system,
                user=(
                    request.user
                    + "\n\nYour previous answer was refused: "
                    + last_error
                    + "\nAnswer again with valid JSON only."
                ),
                schema=request.schema,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                timeout=request.timeout,
            )
            continue
        if on_call is not None:
            on_call(attempt_request, response, None)
        return Draft(proposals=proposals, response=response, attempts=attempt)
    raise OutputError(last_error)
