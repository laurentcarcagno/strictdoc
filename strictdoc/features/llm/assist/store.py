"""The recent results of the assistant, so that `apply` uses what the server sent."""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

from strictdoc.features.llm.assist.envelope import AssistResult

MAX_STORED = 200
STORED_SECONDS = 3600.0


@dataclass
class Stored:
    user: str
    result: AssistResult
    provider: str
    model: str
    template: str
    created: float = field(default_factory=time.monotonic)


class ResultStore:
    def __init__(self) -> None:
        self._items: OrderedDict[str, Stored] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, call_id: str, stored: Stored) -> None:
        with self._lock:
            self._items[call_id] = stored
            while len(self._items) > MAX_STORED:
                self._items.popitem(last=False)

    def get(self, call_id: str, user: str) -> Optional[Stored]:
        with self._lock:
            stored = self._items.get(call_id)
            if stored is None or stored.user != user:
                return None
            if time.monotonic() - stored.created > STORED_SECONDS:
                del self._items[call_id]
                return None
            return stored
