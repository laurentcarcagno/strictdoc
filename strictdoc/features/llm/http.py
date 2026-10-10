"""
One HTTPS/HTTP POST with JSON, for the provider clients.

A redirect is never followed (a server must not be able to send the key, or the
prompt, somewhere else), the answer is size-limited, and an error message never
holds the secret, whatever the server echoes.
"""

import json
import socket
import urllib.error
import urllib.request
from typing import Any, Dict

from strictdoc.features.llm.types import LLMError

MAX_BODY = 4 * 1024 * 1024


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


def post_json(
    *,
    url: str,
    headers: Dict[str, str],
    body: Dict[str, Any],
    timeout: float,
    provider: str,
    secret: str = "",
) -> bytes:
    def scrub(text: str) -> str:
        return text.replace(secret, "***") if secret else text

    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with _OPENER.open(request, timeout=timeout) as response_:
            raw: bytes = response_.read(MAX_BODY + 1)
    except urllib.error.HTTPError as exception_:
        detail = exception_.read(300).decode("utf-8", "replace")
        raise LLMError(
            f"Provider '{provider}' answered HTTP {exception_.code}: "
            f"{scrub(detail)}"
        ) from None
    except (urllib.error.URLError, socket.timeout, OSError) as exception_:
        reason = getattr(exception_, "reason", exception_)
        raise LLMError(
            f"Provider '{provider}' cannot be reached: {scrub(str(reason))}"
        ) from None
    if len(raw) > MAX_BODY:
        raise LLMError(f"Provider '{provider}' answered too much data.")
    return raw
