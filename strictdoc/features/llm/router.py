"""
The assistant in the interface: a page to ask for a draft, the proposals as
editable cards, and the creation of the nodes that the author accepts.

Nothing is saved before "Create". The server decides who may ask (author), which
provider may be used (policy) and what is sent (the context built from the
choices, never text from the browser). The call to the model holds no lock: it
can last a long time.
"""

import os
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from markupsafe import Markup
from starlette.responses import Response

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.core.document_iterator import SDocDocumentIterator
from strictdoc.core.transforms.constants import NodeCreationOrder
from strictdoc.features.comments.model import parse_comment
from strictdoc.features.hierarchy.source import build_reference_resolver
from strictdoc.features.llm.assist.router import create_assist_routers
from strictdoc.features.llm.assist.service import AssistService
from strictdoc.features.llm.audit import LLMAudit, LLMCall
from strictdoc.features.llm.context import (
    BuiltPrompt,
    ContextError,
    ContextSelection,
    build_prompt,
)
from strictdoc.features.llm.policy import Policy, PolicyError
from strictdoc.features.llm.prompts import PATTERNS
from strictdoc.features.llm.providers import create_provider
from strictdoc.features.llm.schema import (
    Draft,
    OutputError,
    Proposal,
    draft_proposals,
)
from strictdoc.features.llm.service import DraftOrigin, create_proposal_nodes
from strictdoc.features.llm.types import LLMError
from strictdoc.features.roles.router import get_principal
from strictdoc.helpers.mid import MID
from strictdoc.server.project_context import ProjectContext

HTTP_PRECONDITION_FAILED = 412
MAX_PROPOSALS_CREATED = 10


def llm_audit_path(context: ProjectContext) -> str:
    config = context.project_config
    folder = config.audit_dir or config.output_dir
    return os.path.join(folder, "llm_audit.jsonl")


def create_llm_routers(
    *, context: ProjectContext
) -> Tuple[APIRouter, APIRouter, Optional[Policy]]:
    config = context.project_config

    def require_feature() -> None:
        if not config.is_activated_llm():
            raise HTTPException(
                status_code=HTTP_PRECONDITION_FAILED,
                detail="The assistant is not activated (project feature "
                "LLM and option llm).",
            )

    read_router = APIRouter(dependencies=[Depends(require_feature)])
    write_router = APIRouter(dependencies=[Depends(require_feature)])
    if config.llm is None:
        return read_router, write_router, None

    llm = config.llm
    audit = LLMAudit(
        llm_audit_path(context), store_prompts=llm.audit_store_prompts
    )
    policy = Policy(llm, audit)

    # The command bar of the editors (assist/): same provider layer and policy.
    assist_read, assist_write = create_assist_routers(
        service=AssistService(
            context=context, llm=llm, audit=audit, policy=policy
        )
    )
    read_router.include_router(assist_read)
    write_router.include_router(assist_write)

    def index() -> Any:
        return context.export_action.traceability_index

    def render(page_name: str, status: int = 200, **values: Any) -> Response:
        page = (
            context.env()
            .get_template(f"features/llm/{page_name}")
            .render(**values)
        )
        return HTMLResponse(content=Markup(page), status_code=status)

    def reference_for(reference_mid: str) -> Tuple[str, str]:
        """The node a draft is added to, and where: after a node, in a document."""
        node = index().get_node_by_mid_weak(MID(reference_mid))
        if isinstance(node, SDocDocument):
            return reference_mid, NodeCreationOrder.CHILD
        if isinstance(node, SDocNode):
            return reference_mid, NodeCreationOrder.AFTER
        raise HTTPException(status_code=404, detail="Node not found.")

    def page_values(reference_mid: str, **extra: Any) -> Dict[str, Any]:
        base: Dict[str, Any] = {
            "reference_mid": reference_mid,
            "patterns": PATTERNS,
            "providers": policy.allowed_providers(),
            "default_provider": llm.default,
            "verification_methods": sorted(llm.verification_methods),
            "instruction": "",
            "pattern": "free",
            "include_node": False,
            "include_parents": False,
            "input_refs": "",
            "neighbours": 0,
            "provider": llm.default,
            "error": "",
            "proposals": None,
            "confirm": None,
        }
        base.update(extra)
        return base

    @read_router.get("/llm/draft", response_class=Response)
    def draft_page(reference_mid: str) -> Response:
        reference_for(reference_mid)
        return render("draft.jinja.html", **page_values(reference_mid))

    def selection_from(
        reference_mid: str,
        include_node: bool,
        include_parents: bool,
        input_refs: str,
        neighbours: int,
    ) -> ContextSelection:
        node = index().get_node_by_mid_weak(MID(reference_mid))
        return ContextSelection(
            node_mid=reference_mid if isinstance(node, SDocNode) else None,
            include_node=include_node,
            include_parents=include_parents,
            input_refs=[
                ref_.strip() for ref_ in input_refs.splitlines() if ref_.strip()
            ],
            neighbours=max(0, min(neighbours, 5)),
        )

    @read_router.post("/actions/llm/draft", response_class=Response)
    def ask(
        request: Request,
        reference_mid: str = Form(...),
        instruction: str = Form(""),
        pattern: str = Form("free"),
        provider: str = Form(""),
        include_node: bool = Form(False),
        include_parents: bool = Form(False),
        input_refs: str = Form(""),
        neighbours: int = Form(0),
        confirm_cloud: bool = Form(False),
    ) -> Response:
        principal = get_principal(request)
        reference_for(reference_mid)
        provider_name = provider or llm.default
        form_values = {
            "instruction": instruction,
            "pattern": pattern,
            "include_node": include_node,
            "include_parents": include_parents,
            "input_refs": input_refs,
            "neighbours": neighbours,
            "provider": provider_name,
        }

        def fail(message: str, status: int = 400) -> Response:
            return render(
                "draft.jinja.html",
                status,
                **page_values(reference_mid, error=message, **form_values),
            )

        resolver = build_reference_resolver(
            config.applicable_documents, index()
        )
        try:
            built = build_prompt(
                traceability_index=index(),
                llm=llm,
                selection=selection_from(
                    reference_mid,
                    include_node,
                    include_parents,
                    input_refs,
                    neighbours,
                ),
                instruction=instruction,
                pattern=pattern,
                resolve_reference=resolver,
            )
        except ContextError as exception_:
            return fail(str(exception_))

        try:
            policy.check(
                user=principal.user,
                provider_name=provider_name,
                classifications=built.classifications,
                cloud_confirmed=confirm_cloud,
            )
        except PolicyError as exception_:
            if exception_.status == 409:
                # Show exactly what would leave the network and ask.
                return render(
                    "draft.jinja.html",
                    200,
                    **page_values(
                        reference_mid,
                        confirm=_confirmation(built, provider_name, llm),
                        **form_values,
                    ),
                )
            return fail(exception_.message, exception_.status)

        provider_object = create_provider(provider_name, llm)
        started = time.monotonic()
        calls: List[Tuple[Any, Any, Optional[str]]] = []
        status, detail = "ok", ""
        draft: Optional[Draft] = None
        try:
            draft = draft_proposals(
                provider_object,
                built.request,
                verification_methods=llm.verification_methods,
                known_uids=set(built.node_uids),
                on_call=lambda req, res, err: calls.append((req, res, err)),
            )
        except LLMError as exception_:
            status, detail = "provider_error", str(exception_)
        except OutputError as exception_:
            status, detail = "invalid_answer", str(exception_)
        latency = time.monotonic() - started
        answer = (
            draft.response.text
            if draft
            else (calls[-1][1].text if calls and calls[-1][1] else "")
        )
        input_tokens = _sum_tokens(calls, "input_tokens")
        output_tokens = _sum_tokens(calls, "output_tokens")
        audit.record(
            LLMCall(
                user=principal.user,
                role=principal.role or "",
                project=config.project_title,
                provider=provider_name,
                model=provider_object.model,
                is_local=provider_object.is_local,
                prompt=built.prompt_text,
                answer=answer,
                node_uids=built.node_uids,
                latency=latency,
                status=status,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                template=built.template.label,
                detail=detail,
            )
        )
        if draft is None:
            return fail(detail, 502)
        return render(
            "draft.jinja.html",
            200,
            **page_values(
                reference_mid,
                proposals=draft.proposals,
                model=provider_object.model,
                template=built.template.label,
                known_uids=built.node_uids,
                **form_values,
            ),
        )

    @write_router.post("/actions/llm/create", response_class=Response)
    async def create(request: Request) -> Response:
        principal = get_principal(request)
        form = await request.form()
        reference_mid = str(form.get("reference_mid", ""))
        provider_name = str(form.get("provider", ""))
        template_label = str(form.get("template", ""))
        model = str(form.get("model", ""))
        known_uids = [
            uid_ for uid_ in str(form.get("known_uids", "")).split(",") if uid_
        ]
        if provider_name not in llm.providers:
            raise HTTPException(status_code=400, detail="Unknown provider.")
        reference, whereto = reference_for(reference_mid)
        proposals: List[Proposal] = []
        count = min(_integer(form.get("count")), MAX_PROPOSALS_CREATED)
        for number in range(count):
            if not form.get(f"accept_{number}"):
                continue
            linked = [
                uid_.strip()
                for uid_ in str(form.get(f"linked_to_{number}", "")).split(",")
                if uid_.strip()
            ]
            # What the browser sends is checked again: only UIDs that were in
            # the context, a method of the project.
            if any(uid_ not in known_uids for uid_ in linked):
                raise HTTPException(
                    status_code=400, detail="Unknown UID in linked_to."
                )
            method = str(form.get(f"verification_method_{number}", ""))
            if (
                llm.verification_methods
                and method not in llm.verification_methods
            ):
                raise HTTPException(
                    status_code=400, detail="Unknown verification method."
                )
            proposals.append(
                Proposal(
                    title=str(form.get(f"title_{number}", "")).strip(),
                    statement=str(form.get(f"statement_{number}", "")).strip(),
                    rationale=str(form.get(f"rationale_{number}", "")).strip(),
                    verification_method=method,
                    linked_to=linked,
                )
            )
        if not proposals:
            return render(
                "created.jinja.html",
                400,
                created=[],
                error="Nothing was ticked.",
            )
        for proposal_ in proposals:
            if not proposal_.title or not proposal_.statement:
                return render(
                    "created.jinja.html",
                    400,
                    created=[],
                    error="A title and a statement are needed.",
                )
        result = create_proposal_nodes(
            context,
            reference_mid=reference,
            whereto=whereto,
            proposals=proposals,
            origin=DraftOrigin(
                provider=provider_name,
                model=model,
                template=template_label,
                user=principal.user,
            ),
        )
        return render(
            "created.jinja.html",
            400 if result.error else 200,
            created=result.created_uids,
            error=result.error,
        )

    @read_router.get("/llm/drafts", response_class=Response)
    def drafts_screen() -> Response:
        rows = []
        for document_ in index().document_tree.document_list:
            for node_, _ in SDocDocumentIterator(
                document=document_, node_filter=None
            ).all_content(print_fragments=False):
                if not isinstance(node_, SDocNode) or not node_.reserved_uid:
                    continue
                if (node_.reserved_status or "").lower() == "active":
                    continue
                for field_ in node_.get_comment_fields():
                    comment = parse_comment(field_.get_text_value())
                    if comment.source == "llm":
                        rows.append(
                            {
                                "uid": node_.reserved_uid,
                                "title": node_.reserved_title or "",
                                "document": document_.title,
                                "status": node_.reserved_status or "",
                                "model": comment.model,
                                "provider": comment.provider,
                                "date": comment.date,
                                "accepted_by": comment.accepted_by,
                            }
                        )
                        break
        return render("drafts.jinja.html", rows=rows)

    return read_router, write_router, policy


def _integer(value: Any) -> int:
    try:
        return max(0, int(str(value)))
    except ValueError:
        return 0


def _sum_tokens(
    calls: List[Tuple[Any, Any, Optional[str]]], name: str
) -> Optional[int]:
    values = [
        getattr(response_, name)
        for _, response_, _ in calls
        if response_ is not None
    ]
    known = [value_ for value_ in values if value_ is not None]
    return sum(known) if known else None


def _confirmation(
    built: BuiltPrompt, provider_name: str, llm: Any
) -> Dict[str, Any]:
    return {
        "provider": provider_name,
        "model": llm.providers[provider_name].model,
        "prompt": built.prompt_text,
        "chars": len(built.prompt_text),
        "node_uids": built.node_uids,
    }
