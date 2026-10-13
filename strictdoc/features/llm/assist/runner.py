"""One call to a model whose answer is validated, with one repair retry."""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from strictdoc.features.llm.schema import OutputError
from strictdoc.features.llm.types import (
    LLMError,
    LLMProvider,
    LLMRequest,
    LLMResponse,
)

Calls = List[Tuple[LLMRequest, Optional[LLMResponse], Optional[str]]]


@dataclass
class Answer:
    data: Dict[str, Any]
    response: LLMResponse
    attempts: int


def ask_validated(
    provider: LLMProvider,
    request: LLMRequest,
    parse: Callable[[str], Dict[str, Any]],
    calls: Calls,
) -> Answer:
    """
    Asks the provider and parses the answer. An answer that does not parse is
    asked again once with the reason; a second failure is raised. Every call
    is appended to `calls` (request, response, error) for the audit.
    Raises LLMError (the provider failed) or OutputError.
    """
    attempt_request = request
    last_error = ""
    for attempt in (1, 2):
        try:
            response = provider.complete(attempt_request)
        except LLMError as exception_:
            calls.append((attempt_request, None, str(exception_)))
            raise
        try:
            data = parse(response.text)
        except OutputError as exception_:
            last_error = str(exception_)
            calls.append((attempt_request, response, last_error))
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
        calls.append((attempt_request, response, None))
        return Answer(data=data, response=response, attempts=attempt)
    raise OutputError(last_error)
