"""
The routes of the assistant bar (JSON, used by the script of the bar):

    POST /actions/llm/assist           a command typed in the bar
    GET  /llm/assist/commands          the commands, for the "/" list
    GET  /llm/assist/mentions          the suggestions of the "@" list
    POST /actions/llm/apply            the operations that were ticked

The role of each route is in strictdoc/features/roles/route_roles.py (reader);
the role each command needs is checked by AssistService, which also checks the
policy of the provider. A command that calls the model holds no lock: it can
last a long time.
"""

from typing import Any, Dict, Tuple

from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from strictdoc.features.llm.assist.envelope import (
    EnvelopeError,
    parse_request,
)
from strictdoc.features.llm.assist.mentions import search_mentions
from strictdoc.features.llm.assist.service import AssistError, AssistService
from strictdoc.features.roles.router import get_principal

_BODY = Body(...)


def create_assist_routers(
    *, service: AssistService
) -> Tuple[APIRouter, APIRouter]:
    read_router = APIRouter()
    write_router = APIRouter()

    def fail(status: int, message: str) -> Response:
        return JSONResponse({"detail": message}, status_code=status)

    @read_router.post("/actions/llm/assist", response_class=Response)
    def assist(request: Request, payload: Any = _BODY) -> Response:
        principal = get_principal(request)
        try:
            parsed = parse_request(payload)
            result = service.run(principal, parsed)
        except EnvelopeError as exception_:
            return fail(400, str(exception_))
        except AssistError as exception_:
            return fail(exception_.status, exception_.message)
        return JSONResponse(result.to_json())

    @read_router.get("/llm/assist/commands", response_class=Response)
    def commands(scope: str = "field") -> Response:
        return JSONResponse(
            {
                "providers": service.policy.allowed_providers(),
                "default_provider": service.llm.default,
                "commands": service.commands(scope),
            }
        )

    @read_router.get("/llm/assist/mentions", response_class=Response)
    def mentions(
        q: str = "",
        node_mid: str = "",
        selection: bool = False,
    ) -> Response:
        found = search_mentions(
            index=service.context.export_action.traceability_index,
            applicable_documents=(
                service.context.project_config.applicable_documents
            ),
            query=q[:80],
            target_node_available=service.find_node(node_mid[:64]) is not None,
            selection_available=selection,
        )
        return JSONResponse({"mentions": found})

    @write_router.post("/actions/llm/apply", response_class=Response)
    def apply(request: Request, payload: Dict[str, Any] = _BODY) -> Response:
        principal = get_principal(request)
        call_id = payload.get("call_id")
        action_ids = payload.get("action_ids")
        if not isinstance(call_id, str) or not (
            isinstance(action_ids, list)
            and all(isinstance(id_, str) for id_ in action_ids)
        ):
            return fail(400, "Send call_id and a list of action_ids.")
        try:
            outcome = service.apply(principal, call_id, action_ids[:50])
        except AssistError as exception_:
            return fail(exception_.status, exception_.message)
        return JSONResponse(outcome)

    return read_router, write_router
