"""
A client for servers that speak the chat-completions protocol: Ollama (its
/v1 address), OpenAI and many gateways. Standard library only.

The address is the one of the configuration and the key comes from an
environment variable that the configuration names (see http.py for the rest).
"""

import json
import os
from typing import Any, Dict, Optional

from strictdoc.features.llm.config import OpenAICompatible
from strictdoc.features.llm.http import post_json
from strictdoc.features.llm.types import (
    LLMError,
    LLMRequest,
    LLMResponse,
    Message,
    ToolCall,
)


class OpenAICompatibleProvider:
    def __init__(
        self,
        name: str,
        config: OpenAICompatible,
        environment: Optional[Dict[str, str]] = None,
    ) -> None:
        self.name = name
        self.model = config.model
        self.is_local = config.is_local
        self._url = config.base_url.rstrip("/") + "/chat/completions"
        self._timeout = config.timeout
        env = environment if environment is not None else dict(os.environ)
        self._key = (
            env.get(config.api_key_env, "") if config.api_key_env else ""
        )
        self._missing_key = (
            config.api_key_env if config.api_key_env and not self._key else ""
        )

    def complete(self, request: LLMRequest) -> LLMResponse:
        if self._missing_key:
            raise LLMError(
                f"The environment variable {self._missing_key} (the key of "
                f"provider '{self.name}') is not set."
            )
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.user},
                *[_message(message_) for message_ in request.messages],
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        if request.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool_["name"],
                        "description": tool_.get("description", ""),
                        "parameters": tool_.get(
                            "input_schema", {"type": "object"}
                        ),
                    },
                }
                for tool_ in request.tools
            ]
        elif request.schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "proposals",
                    "strict": True,
                    "schema": request.schema,
                },
            }
        headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}
        raw = post_json(
            url=self._url,
            headers=headers,
            body=body,
            timeout=min(request.timeout, self._timeout),
            provider=self.name,
            secret=self._key,
        )
        return self._parse(raw)

    def _parse(self, raw: bytes) -> LLMResponse:
        try:
            data = json.loads(raw)
            message = data["choices"][0]["message"]
            text = message.get("content") or ""
            tool_calls = _tool_calls(message.get("tool_calls"))
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise LLMError(
                f"Provider '{self.name}' answered something that is not a "
                "chat completion."
            ) from None
        if not isinstance(text, str) or (
            len(text.strip()) == 0 and not tool_calls
        ):
            raise LLMError(f"Provider '{self.name}' answered no text.")
        usage = data.get("usage") if isinstance(data, dict) else None
        usage = usage if isinstance(usage, dict) else {}
        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            model=str(data.get("model", self.model)),
            input_tokens=_integer(usage.get("prompt_tokens")),
            output_tokens=_integer(usage.get("completion_tokens")),
        )


def _integer(value: Any) -> Optional[int]:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool)
        else None
    )


def _message(message: Message) -> Dict[str, Any]:
    if message.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }
    entry: Dict[str, Any] = {
        "role": message.role,
        "content": message.content or None,
    }
    if message.tool_calls:
        entry["tool_calls"] = [
            {
                "id": call_.id,
                "type": "function",
                "function": {
                    "name": call_.name,
                    "arguments": json.dumps(call_.arguments),
                },
            }
            for call_ in message.tool_calls
        ]
    return entry


def _tool_calls(raw: Any) -> "tuple[ToolCall, ...]":
    """The tools a model asked for; a call that is not well formed is dropped."""
    calls = []
    for index_, item_ in enumerate(raw if isinstance(raw, list) else []):
        try:
            function = item_["function"]
            arguments = function.get("arguments") or {}
            if isinstance(arguments, str):
                arguments = json.loads(arguments) if arguments.strip() else {}
            if not isinstance(arguments, dict):
                continue
            calls.append(
                ToolCall(
                    id=str(item_.get("id") or f"call_{index_}"),
                    name=str(function["name"]),
                    arguments=arguments,
                )
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return tuple(calls)
