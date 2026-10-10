"""
What a call to a language model needs before it is made.

Cloud providers are closed unless the project opens them (allow_cloud). Even
then, a prompt that holds a node of a blocked classification never goes to one,
a monthly token budget can close them, and each use is confirmed by a click that
shows what will be sent. A rate limit protects every provider. The server
decides: whatever the browser sends is checked here.
"""

import threading
import time
from collections import defaultdict, deque
from typing import Callable, Collection, Deque, Dict, Optional

from strictdoc.features.llm.audit import LLMAudit
from strictdoc.features.llm.config import LLMConfig

HTTP_BAD_REQUEST = 400
HTTP_FORBIDDEN = 403
HTTP_CONFLICT = 409
HTTP_TOO_MANY = 429


class PolicyError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class Policy:
    def __init__(
        self,
        llm: LLMConfig,
        audit: LLMAudit,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._llm = llm
        self._audit = audit
        self._clock = clock
        self._calls: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(
        self,
        *,
        user: str,
        provider_name: str,
        classifications: Collection[str],
        cloud_confirmed: bool,
    ) -> None:
        """Raises PolicyError when the call must not be made (yet)."""
        llm = self._llm
        if provider_name not in llm.providers:
            raise PolicyError(
                HTTP_BAD_REQUEST, f"Unknown provider '{provider_name}'."
            )
        if llm.is_cloud(provider_name):
            if not llm.allow_cloud:
                raise PolicyError(
                    HTTP_FORBIDDEN,
                    "Cloud providers are closed for this project.",
                )
            blocked = {
                name_.strip().lower()
                for name_ in llm.cloud_blocked_classifications
            }
            found = sorted(
                name_
                for name_ in classifications
                if name_.strip().lower() in blocked
            )
            if found:
                raise PolicyError(
                    HTTP_FORBIDDEN,
                    "The context holds a classification that never goes to a "
                    f"cloud provider: {', '.join(found)}.",
                )
            budget = llm.cloud_token_budget_per_month
            if budget > 0 and self._audit.cloud_tokens_in_month() >= budget:
                raise PolicyError(
                    HTTP_FORBIDDEN,
                    "The monthly token budget of the cloud providers is used up.",
                )
            if not cloud_confirmed:
                raise PolicyError(
                    HTTP_CONFLICT,
                    "A cloud provider needs the confirmation of what is sent.",
                )
        self._rate_limit(user)

    def _rate_limit(self, user: str) -> None:
        now = self._clock()
        with self._lock:
            calls = self._calls[user]
            while calls and now - calls[0] > 60:
                calls.popleft()
            if len(calls) >= self._llm.rate_limit_per_minute:
                raise PolicyError(
                    HTTP_TOO_MANY,
                    "Too many requests: wait a minute before asking again.",
                )
            calls.append(now)

    def allowed_providers(
        self, classifications: Optional[Collection[str]] = None
    ) -> Dict[str, str]:
        """The providers the user may choose, with their model, for the page."""
        names: Dict[str, str] = {}
        for name_, provider_ in self._llm.providers.items():
            if not provider_.is_local:
                if not self._llm.allow_cloud:
                    continue
                blocked = {
                    c_.strip().lower()
                    for c_ in self._llm.cloud_blocked_classifications
                }
                if any(
                    c_.strip().lower() in blocked
                    for c_ in (classifications or [])
                ):
                    continue
            names[name_] = provider_.model
        return names
