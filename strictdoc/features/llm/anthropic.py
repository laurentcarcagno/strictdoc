"""
A client for the Messages API of Anthropic. The answer is forced through a
tool whose input schema is the output schema, so the model answers with
structured data. Standard library only; the key comes from the environment
variable that the configuration names.
"""

import json
import os
from typing import Any, Dict, Optional

from strictdoc.features.llm.config import Anthropic
from strictdoc.features.llm.http import post_json
from strictdoc.features.llm.openai_compatible import _integer
from strictdoc.features.llm.types import LLMError, LLMRequest, LLMResponse

API_VERSION = "2023-06-01"
TOOL_NAME = "submit_proposals"


class AnthropicProvider:
    is_local = False

    def __init__(
        self,
        name: str,
        config: Anthropic,
        environment: Optional[Dict[str, str]] = None,
    ) -> None:
        self.name = name
        self.model = config.model
        self._url = config.base_url.rstrip("/") + "/v1/messages"
        self._timeout = config.timeout
        env = environment if environment is not None else dict(os.environ)
        self._key_name = config.api_key_env
        self._key = env.get(config.api_key_env, "")

    def complete(self, request: LLMRequest) -> LLMResponse:
        if not self._key:
            raise LLMError(
                f"The environment variable {self._key_name} (the key of "
                f"provider '{self.name}') is not set."
            )
        body: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "system": request.system,
            "messages": [{"role": "user", "content": request.user}],
        }
        if request.schema is not None:
            body["tools"] = [
                {
                    "name": TOOL_NAME,
                    "description": "Submit the proposals of requirements.",
                    "input_schema": request.schema,
                }
            ]
            body["tool_choice"] = {"type": "tool", "name": TOOL_NAME}
        raw = post_json(
            url=self._url,
            headers={"x-api-key": self._key, "anthropic-version": API_VERSION},
            body=body,
            timeout=min(request.timeout, self._timeout),
            provider=self.name,
            secret=self._key,
        )
        return self._parse(raw)

    def _parse(self, raw: bytes) -> LLMResponse:
        try:
            data = json.loads(raw)
            blocks = data["content"]
            if not isinstance(blocks, list):
                raise TypeError
        except (ValueError, KeyError, TypeError):
            raise LLMError(
                f"Provider '{self.name}' answered something that is not a message."
            ) from None
        text = ""
        for block_ in blocks:
            if not isinstance(block_, dict):
                continue
            if (
                block_.get("type") == "tool_use"
                and block_.get("name") == TOOL_NAME
            ):
                text = json.dumps(block_.get("input", {}))
                break
            if block_.get("type") == "text" and not text:
                text = str(block_.get("text", ""))
        if len(text.strip()) == 0:
            raise LLMError(f"Provider '{self.name}' answered no text.")
        usage = data.get("usage") if isinstance(data, dict) else None
        usage = usage if isinstance(usage, dict) else {}
        return LLMResponse(
            text=text,
            model=str(data.get("model", self.model)),
            input_tokens=_integer(usage.get("input_tokens")),
            output_tokens=_integer(usage.get("output_tokens")),
        )
