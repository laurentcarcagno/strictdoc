"""A provider that answers from a list: for the tests and the CI golden set."""

from typing import Callable, List, Optional, Union

from strictdoc.features.llm.types import (
    LLMError,
    LLMRequest,
    LLMResponse,
)

# An LLMResponse is returned as it is (a turn with tool calls, for example).
Answer = Union[str, Exception, LLMResponse, Callable[[LLMRequest], str]]


class FakeProvider:
    def __init__(
        self,
        answers: Optional[List[Answer]] = None,
        *,
        name: str = "fake",
        model: str = "fake-model",
        is_local: bool = True,
    ) -> None:
        self.name = name
        self.model = model
        self.is_local = is_local
        self._answers: List[Answer] = list(answers or [])
        self.requests: List[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if len(self._answers) == 0:
            raise LLMError("The fake provider has no answer left.")
        answer = (
            self._answers.pop(0) if len(self._answers) > 1 else self._answers[0]
        )
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, LLMResponse):
            return answer
        text = answer(request) if callable(answer) else answer
        return LLMResponse(
            text=text,
            model=self.model,
            input_tokens=len(request.system.split())
            + len(request.user.split()),
            output_tokens=len(text.split()),
        )
