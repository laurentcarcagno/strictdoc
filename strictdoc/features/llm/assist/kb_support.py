"""
What the commands need from the knowledge base: the search of a command, the
citation of a requirement, and the context that /ask, /req and /verify add to
their prompt (the tool loop of agent_loop.py).

Nothing here writes to the base. The person on whose behalf each call is made
is the one of the request; the server answers only for the missions that this
person and the service account of StrictDoc share.
"""

import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from strictdoc.features.kb.client import KBClient, KBError, KBResult
from strictdoc.features.kb.config import KBConfig
from strictdoc.features.llm.assist.agent_loop import (
    Gathered,
    ToolRecord,
    citation_line,
    gather,
    mission_row,
    model_allowed,
    retrieve,
)
from strictdoc.features.llm.assist.envelope import (
    OP_REPLACE_TEXT,
    Action,
    AssistRequest,
    AssistResult,
)
from strictdoc.features.llm.assist.errors import AssistError
from strictdoc.features.llm.assist.runner import Calls
from strictdoc.features.roles.principal import Principal

if TYPE_CHECKING:
    from strictdoc.features.llm.assist.service import AssistService

MISSION_CACHE_SECONDS = 60.0


class KBSupport:
    def __init__(self, service: "AssistService") -> None:
        self._service = service
        self._client: Optional[KBClient] = None
        self._missions: Dict[Any, Any] = {}

    # -- access -------------------------------------------------------------

    @property
    def config(self) -> Optional[KBConfig]:
        return self._service.llm.kb

    def client(self) -> KBClient:
        config = self.config
        if config is None:
            raise AssistError(400, "This project has no knowledge base.")
        if self._client is None:
            self._client = KBClient(config)
        return self._client

    def uses(self, command_name: str) -> bool:
        config = self.config
        return config is not None and command_name in config.commands

    def mission(self, principal: Principal) -> Optional[Dict[str, Any]]:
        """The mission as this person sees it; None when they do not see it."""
        config = self.config
        assert config is not None
        key = (principal.user, principal.groups)
        cached = self._missions.get(key)
        now = time.monotonic()
        if cached is not None and now - cached[0] < MISSION_CACHE_SECONDS:
            return cached[1]
        row = mission_row(
            self.client(), config, principal.user, principal.groups
        )
        self._missions[key] = (now, row)
        return row

    # -- /kb and /cite --------------------------------------------------------

    def search_command(
        self, principal: Principal, question: str
    ) -> AssistResult:
        """/kb: a search with no model; the answer is exact citations."""
        config = self.config
        if config is None:
            raise AssistError(400, "This project has no knowledge base.")
        if not question.strip():
            raise AssistError(400, "Say what to look for: /kb <question>")
        gathered = Gathered()
        try:
            row = self.mission(principal)
        except KBError as exception_:
            raise AssistError(502, str(exception_)) from exception_
        if row is None:
            raise AssistError(
                403,
                f"You have no access to the mission {config.mission} of the "
                "knowledge base.",
            )
        gathered = retrieve(
            client=self.client(),
            config=config,
            user=principal.user,
            groups=principal.groups,
            question=question,
            classification=str(row.get("classification") or ""),
        )
        self.audit(principal, gathered)
        lines: List[str] = []
        for result_ in self._last_results(gathered):
            for section_ in result_.data.get("sections", []):
                lines.append(
                    f"- **{section_.get('doc_ref')}** ed. "
                    f"{section_.get('edition')} §{section_.get('numero')} "
                    f"{section_.get('titre') or ''}: "
                    f"{_plain(section_.get('extract'))}"
                )
            ids = result_.data.get("requirement_ids") or []
            if ids:
                lines.append("- Requirements: " + ", ".join(map(str, ids)))
        message = (
            "\n".join(lines)
            if lines
            else f"The base has nothing on this in mission {config.mission}."
        )
        result = AssistResult(
            command="kb", message=message, warnings=list(gathered.notes)
        )
        result.meta = self.meta(gathered)
        return result

    def cite_command(
        self,
        principal: Principal,
        request: AssistRequest,
        identifier: str,
    ) -> AssistResult:
        """/cite: the text of a requirement of the base, word for word."""
        config = self.config
        if config is None:
            raise AssistError(400, "This project has no knowledge base.")
        identifier = identifier.strip().strip("@")
        if not identifier or " " in identifier:
            raise AssistError(400, "Give one identifier: /cite <ID>")
        if "get_requirement" not in config.tools:
            raise AssistError(403, "This project does not allow /cite.")
        try:
            if self.mission(principal) is None:
                raise AssistError(
                    403,
                    f"You have no access to the mission {config.mission} of "
                    "the knowledge base.",
                )
            found = self.client().call(
                "get_requirement",
                {"req_id": identifier, "mission": config.mission},
                user=principal.user,
                groups=principal.groups,
            )
        except KBError as exception_:
            raise AssistError(502, str(exception_)) from exception_
        gathered = Gathered(retrieval=True)
        gathered.records.append(
            ToolRecord(
                tool="get_requirement",
                arguments={"req_id": identifier, "mission": config.mission},
                ok=found.ok,
                request_id=found.request_id,
                note=found.message,
            )
        )
        self.audit(principal, gathered)
        if not found.ok:
            raise AssistError(404, found.message)
        if found.truncated or not found.citations:
            raise AssistError(
                409,
                "The requirement is too long to be cited here without a cut: "
                "open it in the base.",
            )
        text = str(found.data.get("text") or "")
        citation = found.citations[0]
        reference = (
            f"kb://{citation.get('mission')}/{citation.get('doc_ref')}/"
            f"{citation.get('edition')}/{citation.get('section')}"
        )
        quote = (
            "\n".join("> " + line_ for line_ in text.splitlines() or [""])
            + f"\n> — {found.data.get('req_id')}, {citation_line(citation)} "
            + f"({reference})"
        )
        selection = request.target.selection
        existing = request.target.text
        if selection is not None:
            old, new = selection.text, quote
            span: Optional[Dict[str, int]] = {
                "from": selection.start,
                "to": selection.end,
            }
        else:
            span = {"from": len(existing), "to": len(existing)}
            old = ""
            new = ("\n\n" if existing.strip() else "") + quote
        result = AssistResult(
            command="cite",
            message=f"{found.data.get('req_id')}: {citation_line(citation)}",
            warnings=list(found.warnings) + list(gathered.notes),
            actions=[
                Action(
                    op=OP_REPLACE_TEXT,
                    label=f"Insert {found.data.get('req_id')}",
                    data={
                        "field": request.target.field,
                        "range": span,
                        "old": old,
                        "new": new,
                    },
                )
            ],
        )
        gathered.sources.append(citation_line(citation))
        result.meta = self.meta(gathered)
        return result

    # -- the context of a command -----------------------------------------------

    def context_for(
        self,
        *,
        principal: Principal,
        provider_name: str,
        provider: Any,
        request_text: str,
        context_text: str,
        search_text: str,
    ) -> Gathered:
        """
        What /ask, /req and /verify read in the base, or None when this
        project has none for the command. A model on this network runs the
        tool loop; any other provider gets a plain search (the user confirms
        it before it is sent).
        """
        config = self.config
        assert config is not None
        gathered_calls: Calls = []
        try:
            row = self.mission(principal)
        except KBError as exception_:
            empty = Gathered()
            empty.notes.append(f"The knowledge base was not read: {exception_}")
            return empty
        if row is None:
            empty = Gathered()
            empty.notes.append(
                f"The knowledge base shows you no mission {config.mission}: "
                "it was not used."
            )
            return empty
        classification = str(row.get("classification") or "")
        if provider.is_local:
            gathered = gather(
                provider=provider,
                client=self.client(),
                config=config,
                user=principal.user,
                groups=principal.groups,
                request_text=request_text,
                context_text=context_text,
                classification=classification,
                calls=gathered_calls,
            )
        elif not model_allowed(row, provider_name, provider.model):
            empty = Gathered()
            empty.notes.append(
                f"The mission {config.mission} does not list "
                f"'{provider.model}' among its models: the base was not used."
            )
            return empty
        else:
            gathered = retrieve(
                client=self.client(),
                config=config,
                user=principal.user,
                groups=principal.groups,
                question=search_text,
                classification=classification,
            )
        gathered.classification = classification
        if gathered_calls:
            self._service.record_audit(
                principal=principal,
                provider_name=provider_name,
                provider=provider,
                prompt=request_text,
                calls=gathered_calls,
                answer_text=gathered_calls[-1][1].text
                if gathered_calls[-1][1]
                else "",
                uids=[],
                started=time.monotonic(),
                status="ok",
                detail=f"{gathered.rounds} round(s) in the base",
                template=gathered.prompt_label,
            )
        self.audit(principal, gathered)
        return gathered

    # -- audit and answer -----------------------------------------------------------

    def audit(self, principal: Principal, gathered: Gathered) -> None:
        config = self.config
        assert config is not None
        for record_ in gathered.records:
            self._service.audit.record_tool(
                user=principal.user,
                role=principal.role or "",
                project=self._service.context.project_config.project_title,
                mission=config.mission,
                tool=record_.tool,
                arguments=record_.arguments,
                ok=record_.ok,
                chars=record_.chars,
                request_id=record_.request_id,
                note=record_.note,
            )

    def meta(self, gathered: Gathered) -> Dict[str, Any]:
        config = self.config
        return {
            "kb": {
                "mission": config.mission if config else "",
                "sources": list(gathered.sources),
                "rounds": gathered.rounds,
                "retrieval": gathered.retrieval,
                "calls": [r_.tool for r_ in gathered.records],
            }
        }

    @staticmethod
    def _last_results(gathered: Gathered) -> List[KBResult]:
        return [r_ for r_ in gathered.results]


def _plain(text: Any) -> str:
    return " ".join(str(text or "").split())
