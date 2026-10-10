"""
A client for servers that speak the chat-completions protocol: Ollama (its
/v1 address), OpenAI and many gateways. Standard library only.

The address is the one of the configuration, the key comes from an environment
variable that the configuration names, and a redirect is never followed (a
server must not be able to send the key, or the prompt, somewhere else).
"""

import json
import os
import socket
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from strictdoc.features.llm.config import OpenAICompatible
from strictdoc.features.llm.types import LLMError, LLMRequest, LLMResponse


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(  # type: ignore[override]
        self,
        _req: Any,
        _fp: Any,
        _code: int,
        _msg: str,
        _headers: Any,
        _newurl: str,
    ) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)
_MAX_BODY = 4 * 1024 * 1024


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
        if config.api_key_env and not self._key:
            self._missing_key = config.api_key_env
        else:
            self._missing_key = ""

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
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        if request.schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "proposals",
                    "strict": True,
                    "schema": request.schema,
                },
            }
        headers = {"Content-Type": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        http_request = urllib.request.Request(
            self._url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        timeout = min(request.timeout, self._timeout)
        try:
            with _OPENER.open(http_request, timeout=timeout) as response_:
                raw = response_.read(_MAX_BODY + 1)
        except urllib.error.HTTPError as exception_:
            detail = exception_.read(300).decode("utf-8", "replace")
            raise LLMError(
                f"Provider '{self.name}' answered HTTP {exception_.code}: "
                f"{self._scrub(detail)}"
            ) from None
        except (urllib.error.URLError, socket.timeout, OSError) as exception_:
            reason = getattr(exception_, "reason", exception_)
            raise LLMError(
                f"Provider '{self.name}' cannot be reached: "
                f"{self._scrub(str(reason))}"
            ) from None
        if len(raw) > _MAX_BODY:
            raise LLMError(f"Provider '{self.name}' answered too much data.")
        return self._parse(raw)

    def _parse(self, raw: bytes) -> LLMResponse:
        try:
            data = json.loads(raw)
            text = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMError(
                f"Provider '{self.name}' answered something that is not a "
                "chat completion."
            ) from None
        if not isinstance(text, str) or len(text.strip()) == 0:
            raise LLMError(f"Provider '{self.name}' answered no text.")
        usage = data.get("usage") if isinstance(data, dict) else None
        usage = usage if isinstance(usage, dict) else {}
        return LLMResponse(
            text=text,
            model=str(data.get("model", self.model)),
            input_tokens=_integer(usage.get("prompt_tokens")),
            output_tokens=_integer(usage.get("completion_tokens")),
        )

    def _scrub(self, text: str) -> str:
        """No key in a message, whatever the server echoes."""
        return text.replace(self._key, "***") if self._key else text


def _integer(value: Any) -> Optional[int]:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool)
        else None
    )
