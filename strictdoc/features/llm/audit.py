"""
The audit log of the calls to a language model: one JSON line per call, in
llm_audit.jsonl next to the audit log of the project (administrators read it).

A line holds who, when, which provider and model, whether the data stayed on
the network, the SHA-256 of the prompt and the sizes, the UIDs of the nodes
that went into the prompt, the latency, the token counts when the provider gave
them and the outcome. The text of the prompt is written only when the project
asks for it (audit_store_prompts).
"""

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional


@dataclass
class LLMCall:
    user: str
    role: str
    project: str
    provider: str
    model: str
    is_local: bool
    prompt: str
    answer: str
    node_uids: List[str]
    latency: float
    status: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    template: str = ""
    detail: str = ""


class LLMAudit:
    def __init__(self, path: str, store_prompts: bool = False) -> None:
        self.path = path
        self.store_prompts = store_prompts
        self._lock = threading.Lock()

    def record(self, call: LLMCall, now: Optional[datetime] = None) -> None:
        moment = now or datetime.now(timezone.utc)
        entry: Dict[str, Any] = {
            "time": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "user": call.user,
            "role": call.role,
            "project": call.project,
            "provider": call.provider,
            "model": call.model,
            "is_local": call.is_local,
            "prompt_sha256": hashlib.sha256(call.prompt.encode()).hexdigest(),
            "prompt_chars": len(call.prompt),
            "answer_chars": len(call.answer),
            "node_uids": call.node_uids,
            "latency_s": round(call.latency, 3),
            "input_tokens": call.input_tokens,
            "output_tokens": call.output_tokens,
            "template": call.template,
            "status": call.status,
        }
        if call.detail:
            entry["detail"] = call.detail[:300]
        if self.store_prompts:
            entry["prompt"] = call.prompt
        self._write(entry)

    def record_tool(
        self,
        *,
        user: str,
        role: str,
        project: str,
        mission: str,
        tool: str,
        arguments: Dict[str, Any],
        ok: bool,
        chars: int,
        request_id: str,
        note: str = "",
        now: Optional[datetime] = None,
    ) -> None:
        """One call to the knowledge base. `request_id` is the one of its audit log."""
        moment = now or datetime.now(timezone.utc)
        text = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
        entry: Dict[str, Any] = {
            "time": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "kind": "kb_tool",
            "user": user,
            "role": role,
            "project": project,
            "mission": mission,
            "tool": tool,
            "arguments_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "result_chars": chars,
            "request_id": request_id,
            "is_local": True,
            "status": "ok" if ok else "error",
        }
        if note:
            entry["detail"] = note[:300]
        if self.store_prompts:
            entry["arguments"] = arguments
        self._write(entry)

    def _write(self, entry: Dict[str, Any]) -> None:
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        with self._lock:
            os.makedirs(
                os.path.dirname(os.path.abspath(self.path)), exist_ok=True
            )
            descriptor = os.open(
                self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600
            )
            with os.fdopen(descriptor, "a", encoding="utf-8") as file_:
                file_.write(line + "\n")

    def entries(self) -> Iterator[Dict[str, Any]]:
        if not os.path.isfile(self.path):
            return
        with open(self.path, encoding="utf-8") as file_:
            for line_ in file_:
                try:
                    yield json.loads(line_)
                except ValueError:
                    continue

    def cloud_tokens_in_month(self, now: Optional[datetime] = None) -> int:
        """Tokens that the cloud providers used this calendar month (UTC)."""
        moment = now or datetime.now(timezone.utc)
        prefix = moment.strftime("%Y-%m")
        total = 0
        for entry_ in self.entries():
            if entry_.get("is_local") or not str(
                entry_.get("time", "")
            ).startswith(prefix):
                continue
            total += int(entry_.get("input_tokens") or 0)
            total += int(entry_.get("output_tokens") or 0)
        return total
