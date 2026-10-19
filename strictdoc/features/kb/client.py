"""
A client for the MCP server of the knowledge base: JSON-RPC over HTTP, one POST
per call (the server keeps no session). Standard library only.

The token is the one of the service account (client credentials), kept until it
expires. Every call names the person on whose behalf it is made and the groups
of that person; the server answers only for the missions that both share.
"""

import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from strictdoc.features.kb.config import KBConfig

PROTOCOL_VERSION = "2025-03-26"
# A response bigger than this is not read.
MAX_RESPONSE_BYTES = 2_000_000
TOKEN_MARGIN_SECONDS = 30.0


class KBError(Exception):
    """The base cannot answer (network, refusal, bad answer)."""


@dataclass
class KBResult:
    tool: str
    ok: bool
    request_id: str = ""
    # The "result" of the server, or {} on an error.
    data: Dict[str, Any] = field(default_factory=dict)
    citations: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    truncated: bool = False
    message: str = ""


Opener = Callable[[urllib.request.Request, float], bytes]


class KBClient:
    def __init__(
        self,
        config: KBConfig,
        environment: Optional[Mapping[str, str]] = None,
        opener: Optional[Opener] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        env = environment if environment is not None else os.environ
        self._secret = env.get(config.secret_env, "")
        self._bundle = env.get(config.ca_bundle_env, "")
        self._opener = opener or self._default_opener
        self._clock = clock
        self._token = ""
        self._expires = 0.0
        self._lock = threading.Lock()

    # -- transport ----------------------------------------------------------

    def _default_opener(
        self, request: urllib.request.Request, timeout: float
    ) -> bytes:
        context = ssl.create_default_context()
        if self._bundle:
            context.load_verify_locations(cafile=self._bundle)
        try:
            with urllib.request.urlopen(  # noqa: S310 (address from the config)
                request, timeout=timeout, context=context
            ) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exception_:
            raise KBError(
                f"The base answered HTTP {exception_.code}."
            ) from None
        except (urllib.error.URLError, OSError, ssl.SSLError) as exception_:
            raise KBError(
                f"The base cannot be reached: {exception_}."
            ) from None
        if len(body) > MAX_RESPONSE_BYTES:
            raise KBError("The base answered too much.")
        return body

    def _access_token(self) -> str:
        with self._lock:
            now = self._clock()
            if self._token and now < self._expires:
                return self._token
            if not self._secret:
                raise KBError(
                    f"The environment variable {self._config.secret_env} "
                    "(the secret of the base) is not set."
                )
            form = urllib.parse.urlencode(
                {
                    "grant_type": "client_credentials",
                    "client_id": self._config.client_id,
                    "client_secret": self._secret,
                }
            ).encode()
            request = urllib.request.Request(  # noqa: S310
                self._config.token_url,
                data=form,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            try:
                data = json.loads(self._opener(request, self._config.timeout))
                token = str(data["access_token"])
                lifetime = float(data.get("expires_in", 60))
            except (ValueError, KeyError, TypeError):
                raise KBError("The token endpoint answered no token.") from None
            self._token = token
            self._expires = now + max(lifetime - TOKEN_MARGIN_SECONDS, 1.0)
            return token

    def _rpc(
        self,
        method: str,
        params: Dict[str, Any],
        *,
        user: str,
        groups: Sequence[str],
        request_id: str,
    ) -> Dict[str, Any]:
        token = self._access_token()
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        ).encode()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "X-On-Behalf-Of": user,
            "X-On-Behalf-Of-Groups": ",".join(groups),
            "X-Request-Id": request_id,
        }
        request = urllib.request.Request(  # noqa: S310
            self._config.url.rstrip("/") + "/mcp",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            answer = json.loads(self._opener(request, self._config.timeout))
        except ValueError:
            raise KBError(
                "The base answered something that is not JSON."
            ) from None
        if not isinstance(answer, dict):
            raise KBError("The base answered something unexpected.")
        if "error" in answer:
            error = answer["error"]
            message = error.get("message") if isinstance(error, dict) else ""
            raise KBError(f"The base refused: {message}.")
        result = answer.get("result")
        if not isinstance(result, dict):
            raise KBError("The base answered no result.")
        return result

    # -- the protocol -------------------------------------------------------

    def tool_definitions(
        self, *, user: str, groups: Sequence[str]
    ) -> List[Dict[str, Any]]:
        """The tools that the server offers, limited to the allow-list."""
        result = self._rpc(
            "tools/list",
            {},
            user=user,
            groups=groups,
            request_id=_new_request_id(),
        )
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise KBError("The base listed no tools.")
        allowed = set(self._config.tools)
        return [
            tool_
            for tool_ in tools
            if isinstance(tool_, dict) and tool_.get("name") in allowed
        ]

    def call(
        self,
        tool: str,
        arguments: Dict[str, Any],
        *,
        user: str,
        groups: Sequence[str],
    ) -> KBResult:
        """Calls one tool. A tool outside the allow-list is refused here."""
        if tool not in self._config.tools:
            raise KBError(f"The tool '{tool}' is not allowed.")
        return self._call(tool, arguments, user=user, groups=groups)

    def _call(
        self,
        tool: str,
        arguments: Dict[str, Any],
        *,
        user: str,
        groups: Sequence[str],
    ) -> KBResult:
        request_id = _new_request_id()
        result = self._rpc(
            "tools/call",
            {"name": tool, "arguments": arguments},
            user=user,
            groups=groups,
            request_id=request_id,
        )
        try:
            body = json.loads(result["content"][0]["text"])
        except (ValueError, KeyError, IndexError, TypeError):
            raise KBError("The base answered no content.") from None
        if not isinstance(body, dict):
            raise KBError("The base answered no content.")
        server_id = str(body.get("request_id") or request_id)
        if result.get("isError"):
            return KBResult(
                tool=tool,
                ok=False,
                request_id=server_id,
                message=str(body.get("message", "error")),
            )
        data = body.get("result")
        citations = body.get("citations")
        warnings = body.get("warnings")
        return KBResult(
            tool=tool,
            ok=True,
            request_id=server_id,
            data=data if isinstance(data, dict) else {},
            citations=[c_ for c_ in citations or [] if isinstance(c_, dict)],
            warnings=[str(w_) for w_ in warnings or []],
            truncated=body.get("truncated") is True,
        )

    def missions(
        self, *, user: str, groups: Sequence[str]
    ) -> List[Dict[str, Any]]:
        """The missions that the base shows to this person (list_missions)."""
        result = self._call("list_missions", {}, user=user, groups=groups)
        rows = result.data.get("missions")
        return [r_ for r_ in rows or [] if isinstance(r_, dict)]


def _new_request_id() -> str:
    return "sd-" + uuid.uuid4().hex[:12]
