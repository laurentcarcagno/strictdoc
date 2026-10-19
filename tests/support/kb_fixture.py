"""A stand-in for the client of the knowledge base, for the tests of the assistant."""

from typing import Any, Dict, List, Optional, Sequence

from strictdoc.features.kb.client import KBError, KBResult
from strictdoc.features.kb.config import KBConfig

REQ_TEXT = "The OBC shall send the heartbeat packet every 500 ms."
CITATION = {
    "mission": "isis",
    "doc_ref": "ISIS-SYS-IF-249-CNES",
    "edition": "9.0",
    "section": "3.2",
    "git_commit": "abc123",
    "path": "docs/20-interfaces/if-249.md#32",
}

DEFINITIONS = [
    {
        "name": name_,
        "description": f"The tool {name_}.",
        "inputSchema": {"type": "object", "properties": {}},
    }
    for name_ in (
        "search",
        "get_requirement",
        "get_requirement_batch",
        "trace",
        "get_section",
        "get_interface",
        "glossary",
        "find_references",
    )
]


def make_kb_config(**kwargs: Any) -> KBConfig:
    values: Dict[str, Any] = {
        "url": "http://kb.internal",
        "mission": "isis",
        "token_url": "https://keycloak.example/realms/x/protocol/openid-connect/token",
    }
    values.update(kwargs)
    return KBConfig(**values)


class FakeKBClient:
    """Answers like the server for a few requests; records every call."""

    def __init__(
        self,
        *,
        missions: Optional[List[Dict[str, Any]]] = None,
        fail: bool = False,
        text: str = REQ_TEXT,
        truncated: bool = False,
    ) -> None:
        self.missions_rows = (
            missions
            if missions is not None
            else [
                {
                    "code": "isis",
                    "client": "CNES",
                    "classification": "interne",
                    "allowed_models": ["gpt-oss"],
                }
            ]
        )
        self.fail = fail
        self.text = text
        self.truncated = truncated
        self.calls: List[Dict[str, Any]] = []

    def tool_definitions(
        self, *, user: str, groups: Sequence[str]
    ) -> List[Dict[str, Any]]:
        if self.fail:
            raise KBError("The base cannot be reached: down.")
        return list(DEFINITIONS)

    def missions(
        self, *, user: str, groups: Sequence[str]
    ) -> List[Dict[str, Any]]:
        if self.fail:
            raise KBError("The base cannot be reached: down.")
        return self.missions_rows

    def call(
        self,
        tool: str,
        arguments: Dict[str, Any],
        *,
        user: str,
        groups: Sequence[str],
    ) -> KBResult:
        self.calls.append(
            {
                "tool": tool,
                "arguments": arguments,
                "user": user,
                "groups": list(groups),
            }
        )
        if self.fail:
            raise KBError("The base cannot be reached: down.")
        if tool == "search":
            return KBResult(
                tool=tool,
                ok=True,
                request_id="srv-1",
                data={
                    "sections": [
                        {
                            "doc_ref": CITATION["doc_ref"],
                            "edition": "9.0",
                            "numero": "3.2",
                            "titre": "Heartbeat",
                            "extract": "heartbeat every 500 ms",
                        }
                    ],
                    "requirement_ids": ["ISIS-IF-249-0100"],
                },
                citations=[CITATION],
            )
        if tool == "get_requirement":
            if arguments.get("req_id") == "NOPE-1":
                return KBResult(
                    tool=tool,
                    ok=False,
                    message="requirement 'NOPE-1' not found",
                )
            return KBResult(
                tool=tool,
                ok=True,
                request_id="srv-2",
                data={"req_id": arguments.get("req_id"), "text": self.text},
                citations=[CITATION],
                truncated=self.truncated,
            )
        return KBResult(
            tool=tool, ok=True, request_id="srv-3", data={}, citations=[]
        )
