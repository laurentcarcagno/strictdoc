"""
Runs a command of the assistant bar, and applies the operations that a person
ticked.

The browser sends only the typed text, the text of the field, the selection and
the ids of the nodes; the server finds everything else itself, checks the role
of the user for the command, the policy for the provider, and validates every
operation before it goes back. Nothing here writes a document except `apply`.
"""

import hashlib
import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.core.transforms.constants import NodeCreationOrder
from strictdoc.core.transforms.update_requirement import (
    CreateOrUpdateNodeCommand,
    UpdateNodeInfo,
)
from strictdoc.export.html.form_objects.requirement_form_object import (
    RequirementFormObject,
    RequirementReferenceFormField,
)
from strictdoc.features.comments.model import Comment
from strictdoc.features.comments.service import (
    comments_of,
    save_comments,
    supports_comments,
)
from strictdoc.features.llm.assist.commands import (
    COMMANDS,
    KIND_LOCAL,
    Command,
    CommandError,
    catalogue,
    effective,
    help_result,
    parse_input,
)
from strictdoc.features.llm.assist.converters import (
    ConvertContext,
    convert,
    model_schema,
    parse_answer,
)
from strictdoc.features.llm.assist.documents import DocumentCommands
from strictdoc.features.llm.assist.envelope import (
    OP_ADD_COMMENT,
    OP_ADD_RELATION,
    OP_CREATE_DOCUMENT,
    OP_INSERT_NODE,
    OP_INSERT_TEXT,
    Action,
    AssistRequest,
    AssistResult,
    Finding,
)
from strictdoc.features.llm.assist.errors import AssistError
from strictdoc.features.llm.assist.lint import lint
from strictdoc.features.llm.assist.mentions import (
    find_mentions,
    resolve_mentions,
)
from strictdoc.features.llm.assist.prompting import (
    MAX_TOKENS,
    TEXT_KINDS,
    build_user_prompt,
)
from strictdoc.features.llm.assist.runner import Calls, ask_validated
from strictdoc.features.llm.assist.store import ResultStore, Stored
from strictdoc.features.llm.assist.translation import check_text
from strictdoc.features.llm.audit import LLMAudit, LLMCall
from strictdoc.features.llm.config import LLMConfig
from strictdoc.features.llm.context import (
    KIND_PARENT,
    ContextItem,
    _item,
    _render_blocks,
)
from strictdoc.features.llm.policy import Policy, PolicyError
from strictdoc.features.llm.prompts import AssistPrompt, load_assist_prompt
from strictdoc.features.llm.providers import create_provider
from strictdoc.features.llm.schema import OutputError, Proposal
from strictdoc.features.llm.service import (
    DraftOrigin,
    create_proposal_nodes,
    create_text_node,
)
from strictdoc.features.llm.types import LLMError, LLMRequest
from strictdoc.features.reviewers.reviewers import can_comment
from strictdoc.features.roles.principal import Principal
from strictdoc.features.roles.roles import (
    ROLE_AUTHOR,
    ROLE_READER,
    ROLE_REVIEWER,
    role_allows,
)
from strictdoc.helpers.cast import assert_cast
from strictdoc.helpers.exception import StrictDocException
from strictdoc.helpers.mid import MID
from strictdoc.helpers.path_filter import PathFilter
from strictdoc.helpers.string import is_safe_alphanumeric_string
from strictdoc.server.project_context import ProjectContext

MAX_STORED = 200
STORED_SECONDS = 3600.0
MAX_PARENTS = 5


class AssistService:
    def __init__(
        self,
        *,
        context: ProjectContext,
        llm: LLMConfig,
        audit: LLMAudit,
        policy: Policy,
    ) -> None:
        self.context = context
        self.llm = llm
        self.audit = audit
        self.policy = policy
        self.store = ResultStore()
        self.documents = DocumentCommands(self)
        # The findings of the last /verify, for /fix: (user, text hash).
        self._last_findings: Dict[Tuple[str, str], List[Finding]] = {}

    # -- lookups ------------------------------------------------------------

    def _index(self) -> Any:
        return self.context.export_action.traceability_index

    def find_node(self, mid: str) -> Optional[SDocNode]:
        if not mid:
            return None
        node = self._index().get_node_by_mid_weak(MID(mid))
        return node if isinstance(node, SDocNode) else None

    def find_document(
        self, mid: str, node: Optional[SDocNode]
    ) -> Optional[SDocDocument]:
        if node is not None:
            return assert_cast(
                node.get_parent_or_including_document(), SDocDocument
            )
        if not mid:
            return None
        found = self._index().get_node_by_mid_weak(MID(mid))
        return found if isinstance(found, SDocDocument) else None

    # -- roles --------------------------------------------------------------

    @staticmethod
    def allowed(
        command: Command,
        principal: Principal,
        document: Optional[SDocDocument],
    ) -> bool:
        if command.role == ROLE_READER:
            return role_allows(principal.role, ROLE_READER)
        if command.role == ROLE_AUTHOR:
            return role_allows(principal.role, ROLE_AUTHOR)
        if command.role == ROLE_REVIEWER:
            if document is None:
                return role_allows(principal.role, ROLE_REVIEWER)
            return can_comment(principal.role, principal.user, document)
        return False

    # -- the prompt ---------------------------------------------------------

    def _material(
        self, items: List[ContextItem]
    ) -> Tuple[str, List[ContextItem]]:
        blocks, kept = _render_blocks(items, self.llm.max_context_chars)
        return ("\n".join(blocks) if blocks else "(none)"), kept

    def _problems(self, user: str, text: str, notes: str) -> str:
        """The points of the last /verify of this text, else the lint."""
        remembered = self._last_findings.get((user, _digest(text)))
        if remembered:
            findings = remembered
        else:
            findings = [
                Finding(
                    f_.severity, f_.rule, f_.quote, f_.message, f_.suggestion
                )
                for f_ in lint(text)
            ]
        lines = [
            f"- {f_.rule}: {f_.message}"
            + (f' (words: "{f_.quote}")' if f_.quote else "")
            + (f" Suggestion: {f_.suggestion}" if f_.suggestion else "")
            for f_ in findings
        ]
        if notes:
            lines.append(f"- Notes of the user: {notes}")
        return (
            "\n".join(lines) if lines else "- none found: improve the clarity."
        )

    # -- run ------------------------------------------------------------------

    def provider(self, name: str) -> Any:
        """The provider object (the tests replace create_provider)."""
        return create_provider(name, self.llm)

    def run(self, principal: Principal, request: AssistRequest) -> AssistResult:
        if request.scope == "document":
            return self.documents.run(principal, request)
        try:
            parsed = effective(parse_input(request.input))
        except CommandError as exception_:
            raise AssistError(400, str(exception_)) from exception_
        command = COMMANDS[parsed.command]
        if request.scope not in command.scopes:
            raise AssistError(
                400, f"/{command.name} is not available for a {request.scope}."
            )
        node = self.find_node(request.target.node_mid)
        if request.target.node_mid and node is None:
            raise AssistError(404, "The requirement does not exist.")
        document = self.find_document(request.target.document_mid, node)
        if not self.allowed(command, principal, document):
            raise AssistError(403, f"Your role does not allow /{command.name}.")
        if command.kind == KIND_LOCAL:
            return help_result(command)
        arguments = parsed.arguments
        if command.name in ("translate", "retranslate") and not arguments:
            raise AssistError(400, f"Say the language: /{command.name} fr")
        if command.name in ("req", "ask") and not arguments:
            raise AssistError(400, f"Say what you want after /{command.name}.")

        selection = request.target.selection
        text = request.target.text
        if command.name in ("split", "fix", "trace", "retranslate", "test"):
            # These work on the whole text.
            selection = None
        has_selection = selection is not None
        original = selection.text if selection is not None else text
        if command.kind in TEXT_KINDS and len(original.strip()) == 0:
            raise AssistError(400, "There is no text to work on.")

        resolved = resolve_mentions(
            index=self._index(),
            applicable_documents=self.context.project_config.applicable_documents,
            tokens=find_mentions(arguments),
            target_node=node,
            target_document=document,
            selection_text=selection.text if selection is not None else "",
            limit_chars=self.llm.max_context_chars,
        )
        if resolved.unresolved:
            raise AssistError(400, " ".join(resolved.unresolved))
        items = list(resolved.items)
        if command.name == "trace" and not items:
            raise AssistError(
                400,
                "Mention what to link to: /trace @REQ-1 @DA1 §5.2 ...",
            )
        if node is not None and command.name in (
            "verify",
            "comment",
            "test",
        ):
            for parent_ in self._index().get_parent_requirements(node)[
                :MAX_PARENTS
            ]:
                items.append(_item(KIND_PARENT, parent_))
        material, kept = self._material(items)

        prompt = load_assist_prompt(command.prompt)
        link_candidates = {item_.uid for item_ in resolved.items if item_.uid}
        if node is not None:
            link_candidates -= {
                parent_.reserved_uid or ""
                for parent_ in self._index().get_parent_requirements(node)
            }
            link_candidates.discard(node.reserved_uid or "")
        insert_ref, insert_after = self._insertion_point(
            request, node, document
        )
        convert_context = ConvertContext(
            command=command,
            arguments=arguments,
            request=request,
            node_mid=request.target.node_mid if node is not None else "",
            insert_ref=insert_ref,
            insert_after=insert_after,
            can_add_comments=(
                node is not None
                and supports_comments(node)
                and document is not None
                and can_comment(principal.role, principal.user, document)
            ),
            verification_methods=self.llm.verification_methods,
            known_uids=(
                link_candidates
                if command.name == "trace"
                else {item_.uid for item_ in kept if item_.uid}
            ),
            original=original,
            start=selection.start if selection is not None else None,
            end=selection.end if selection is not None else None,
        )
        llm_request = LLMRequest(
            max_tokens=MAX_TOKENS,
            system=prompt.system,
            user=build_user_prompt(
                command=command,
                arguments=arguments,
                field=request.target.field,
                uid=(node.reserved_uid if node is not None else "") or "",
                original=original,
                whole_text=request.target.text,
                has_selection=has_selection,
                material=material,
                methods=self.llm.verification_methods,
                problems=(
                    self._problems(
                        principal.user, request.target.text, arguments
                    )
                    if command.name == "fix"
                    else ""
                ),
                link_uids=sorted(link_candidates),
            ),
            schema=model_schema(command, convert_context),
        )
        classifications: Set[str] = {
            item_.classification for item_ in kept if item_.classification
        }
        if (
            document is not None
            and document.config is not None
            and document.config.classification
        ):
            classifications.add(document.config.classification)

        provider_name = request.provider or self.llm.default
        confirmation = self.check_policy(
            principal=principal,
            command=command,
            provider_name=provider_name,
            classifications=classifications,
            confirmed=request.cloud_confirmed,
            prompt_text=llm_request.system + "\n\n" + llm_request.user,
            uids=sorted(convert_context.known_uids or ()),
        )
        if confirmation is not None:
            return confirmation

        return self._ask_and_convert(
            principal=principal,
            command=command,
            prompt=prompt,
            llm_request=llm_request,
            provider_name=provider_name,
            convert_context=convert_context,
            uids=sorted(convert_context.known_uids or ()),
            notes=resolved.notes,
        )

    def check_policy(
        self,
        *,
        principal: Principal,
        command: Command,
        provider_name: str,
        classifications: Set[str],
        confirmed: bool,
        prompt_text: str,
        uids: List[str],
    ) -> Optional[AssistResult]:
        """
        None when the call may be made. A result that asks for the
        confirmation of a cloud call. Raises AssistError when it is refused.
        """
        try:
            self.policy.check(
                user=principal.user,
                provider_name=provider_name,
                classifications=classifications,
                cloud_confirmed=confirmed,
            )
        except PolicyError as exception_:
            if exception_.status == 409:
                return AssistResult(
                    command=command.name,
                    status="needs_confirmation",
                    message="A cloud provider needs your confirmation.",
                    confirmation={
                        "provider": provider_name,
                        "model": self.llm.providers[provider_name].model,
                        "chars": len(prompt_text),
                        "prompt": prompt_text,
                        "node_uids": uids,
                    },
                )
            raise AssistError(
                exception_.status, exception_.message
            ) from exception_
        return None

    def record_audit(
        self,
        *,
        principal: Principal,
        provider_name: str,
        provider: Any,
        prompt: str,
        calls: Calls,
        answer_text: str,
        uids: List[str],
        started: float,
        status: str,
        detail: str,
        template: str,
    ) -> None:
        self.audit.record(
            LLMCall(
                user=principal.user,
                role=principal.role or "",
                project=self.context.project_config.project_title,
                provider=provider_name,
                model=provider.model,
                is_local=provider.is_local,
                prompt=prompt,
                answer=answer_text,
                node_uids=uids,
                latency=time.monotonic() - started,
                status=status,
                input_tokens=_sum(calls, "input_tokens"),
                output_tokens=_sum(calls, "output_tokens"),
                template=template,
                detail=detail,
            )
        )

    def _insertion_point(
        self,
        request: AssistRequest,
        node: Optional[SDocNode],
        document: Optional[SDocDocument],
    ) -> Tuple[str, bool]:
        """
        Where /req puts new nodes: after the node being edited, else after
        the node the new one follows, else at the end of the document.
        """
        if node is not None:
            return request.target.node_mid, True
        reference = self.find_node(request.target.reference_mid)
        if reference is not None:
            return request.target.reference_mid, True
        if document is not None:
            mid = document.reserved_mid
            return (
                mid if isinstance(mid, str) else mid.get_string_value()
            ), False
        return "", False

    def _ask_and_convert(
        self,
        *,
        principal: Principal,
        command: Command,
        prompt: AssistPrompt,
        llm_request: LLMRequest,
        provider_name: str,
        convert_context: ConvertContext,
        uids: List[str],
        notes: List[str],
    ) -> AssistResult:
        provider = self.provider(provider_name)
        calls: Calls = []
        started = time.monotonic()
        status, detail = "ok", ""
        answer = None
        try:
            answer = ask_validated(
                provider,
                llm_request,
                lambda text: parse_answer(convert_context, text),
                calls,
            )
        except LLMError as exception_:
            status, detail = "provider_error", str(exception_)
        except OutputError as exception_:
            status, detail = "invalid_answer", str(exception_)
        self.record_audit(
            principal=principal,
            provider_name=provider_name,
            provider=provider,
            prompt=llm_request.system + "\n\n" + llm_request.user,
            calls=calls,
            answer_text=(
                answer.response.text
                if answer
                else (calls[-1][1].text if calls and calls[-1][1] else "")
            ),
            uids=uids,
            started=started,
            status=status,
            detail=detail,
            template=prompt.label,
        )
        if answer is None:
            raise AssistError(502, detail)
        try:
            conversion = convert(convert_context, answer.data)
        except OutputError as exception_:
            raise AssistError(502, str(exception_)) from exception_
        if command.name == "verify":
            self._last_findings[
                (principal.user, _digest(convert_context.request.target.text))
            ] = list(conversion.findings)
            while len(self._last_findings) > MAX_STORED:
                self._last_findings.pop(next(iter(self._last_findings)))
        result = AssistResult(
            command=command.name,
            message=conversion.message,
            actions=conversion.actions,
            findings=conversion.findings,
            warnings=notes + conversion.warnings,
        )
        call_id = "c" + MID.create().get_string_value()[:10]
        result.meta = {
            "call_id": call_id,
            "provider": provider_name,
            "model": provider.model,
            "is_local": provider.is_local,
            "prompt": prompt.label,
            "attempts": answer.attempts,
            "input_tokens": answer.response.input_tokens,
            "output_tokens": answer.response.output_tokens,
        }
        self.store.put(
            call_id,
            Stored(
                user=principal.user,
                result=result,
                provider=provider_name,
                model=provider.model,
                template=prompt.label,
            ),
        )
        return result

    # -- apply ----------------------------------------------------------------

    def apply(
        self, principal: Principal, call_id: str, action_ids: List[str]
    ) -> Dict[str, Any]:
        """Carries out the ticked operations that the server itself sent."""
        stored = self.store.get(call_id, principal.user)
        if stored is None:
            raise AssistError(404, "This result is too old: ask again.")
        by_id = {action_.id: action_ for action_ in stored.result.actions}
        chosen: List[Action] = []
        for id_ in action_ids:
            if id_ not in by_id:
                raise AssistError(400, f"Unknown action {id_}.")
            chosen.append(by_id[id_])
        applied: List[str] = []
        errors: List[Dict[str, str]] = []
        opened = ""

        def done(actions: List[Action], error: str) -> None:
            for action_ in actions:
                if error:
                    errors.append({"id": action_.id, "message": error})
                else:
                    applied.append(action_.id)

        comments_by_node: Dict[str, List[Action]] = {}
        relations_by_node: Dict[str, List[Action]] = {}
        inserts: Dict[Tuple[str, str], List[Action]] = {}
        for action_ in chosen:
            if action_.op == OP_ADD_COMMENT:
                comments_by_node.setdefault(action_.data["node"], []).append(
                    action_
                )
            elif action_.op == OP_ADD_RELATION:
                relations_by_node.setdefault(action_.data["node"], []).append(
                    action_
                )
            elif action_.op == OP_INSERT_TEXT:
                done([action_], self._insert_text(principal, action_))
            elif action_.op == OP_CREATE_DOCUMENT:
                error, link = self._create_document(principal, action_)
                done([action_], error)
                if link:
                    opened = link
            elif action_.op == OP_INSERT_NODE:
                position = action_.data["position"]
                inserts.setdefault(
                    (position["ref"], position["where"]), []
                ).append(action_)
            else:
                errors.append(
                    {
                        "id": action_.id,
                        "message": "This operation is applied in the editor.",
                    }
                )
        for (ref_, _where), actions_ in inserts.items():
            done(actions_, self._insert(principal, stored, ref_, actions_))
        for node_mid, actions_ in relations_by_node.items():
            done(actions_, self._relate(principal, node_mid, actions_))
        for node_mid, actions_ in comments_by_node.items():
            done(actions_, self._comment(principal, node_mid, actions_))
        outcome: Dict[str, Any] = {"applied": applied, "errors": errors}
        if opened:
            outcome["open"] = opened
        return outcome

    def _insert_text(self, principal: Principal, action: Action) -> str:
        """Adds a paragraph (the glossary) at the place the result named."""
        if not role_allows(principal.role, ROLE_AUTHOR):
            return "Your role does not allow adding text."
        position = action.data["position"]
        reference = self._index().get_node_by_mid_weak(MID(position["ref"]))
        if isinstance(reference, SDocDocument):
            whereto = NodeCreationOrder.CHILD
        elif isinstance(reference, SDocNode):
            whereto = NodeCreationOrder.AFTER
        else:
            return "The place for the text does not exist."
        return create_text_node(
            self.context,
            reference_mid=position["ref"],
            whereto=whereto,
            text=str(action.data["text"]),
        )

    def _create_document(
        self, principal: Principal, action: Action
    ) -> Tuple[str, str]:
        """
        Writes the translated document that a job prepared, after checking its
        path and that none of its UIDs exists. Returns an error message (or
        an empty string) and the address of the new document.
        """
        if not role_allows(principal.role, ROLE_AUTHOR):
            return "Your role does not allow creating documents.", ""
        config = self.context.project_config
        path = str(action.data["path"]).strip().lstrip("/")
        if not is_safe_alphanumeric_string(path):
            return (
                "The path may only hold letters, digits, '_', '.', and '/'.",
                "",
            )
        extensions = tuple(config.get_editable_document_extensions())
        if not path.endswith(extensions):
            return (
                f"The path must end with one of: {', '.join(extensions)}.",
                "",
            )
        if config.include_doc_paths is not None and not PathFilter(
            config.include_doc_paths, positive_or_negative=True
        ).match(path):
            return "The path is not allowed by include_doc_paths.", ""
        if config.exclude_doc_paths is not None and PathFilter(
            config.exclude_doc_paths, positive_or_negative=False
        ).match(path):
            return "The path is excluded by exclude_doc_paths.", ""
        assert isinstance(config.input_paths, list)
        root = os.path.realpath(config.input_paths[0])
        full = os.path.realpath(os.path.join(root, path))
        if os.path.commonpath([root, full]) != root:
            return "The path leaves the project.", ""
        if os.path.exists(full):
            return f"{path} exists already: choose another path.", ""
        text = str(action.hidden["sdoc_text"])
        try:
            uids = check_text(text)
        except StrictDocException as exception_:
            return f"The translated document is not valid: {exception_}", ""
        index = self._index()
        taken = [uid_ for uid_ in uids if index.get_node_by_uid_weak2(uid_)]
        if taken:
            return (
                "These UIDs exist already: " + ", ".join(taken[:5]) + ".",
                "",
            )
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf8") as file_:
            file_.write(text)
        self.context.export_action.build_index()
        self.context.export_action.export()
        for document_ in self._index().document_tree.document_list:
            meta = document_.meta
            if (
                meta is not None
                and os.path.realpath(meta.input_doc_full_path) == full
            ):
                return "", "/" + meta.get_html_doc_link()
        return "", ""

    def _relate(
        self, principal: Principal, node_mid: str, actions: List[Action]
    ) -> str:
        """Adds parents to a saved node, through the form of the node."""
        if not role_allows(principal.role, ROLE_AUTHOR):
            return "Your role does not allow changing requirements."
        node = self.find_node(node_mid)
        index = self._index()
        if node is None or not index.can_edit_node(node):
            return "The requirement cannot be changed."
        document = assert_cast(
            node.get_parent_or_including_document(), SDocDocument
        )
        revision = self.context.revisions[node_mid]
        form = RequirementFormObject.create_from_requirement(
            requirement=node,
            revision=revision,
            context_document_mid=document.reserved_mid,
        )
        existing = {
            parent_.reserved_uid
            for parent_ in index.get_parent_requirements(node)
        }
        for action_ in actions:
            uid = str(action_.data["uid"])
            if uid in existing or index.get_node_by_uid_weak2(uid) is None:
                continue
            form.reference_fields.append(
                RequirementReferenceFormField(
                    field_mid=MID.create().get_string_value(),
                    field_type=RequirementReferenceFormField.FieldType.PARENT,
                    field_value=uid,
                    field_role=None,
                    is_new=True,
                )
            )
        form.validate(
            traceability_index=index,
            context_document=document,
            config=self.context.project_config,
            existing_revision=revision,
        )
        if form.any_errors():
            messages = [
                message_
                for messages_ in form.errors.values()
                for message_ in messages_
            ] + [
                message_
                for field_ in form.reference_fields
                for message_ in field_.validation_messages
            ]
            return " ".join(messages) or "The link is not valid."
        CreateOrUpdateNodeCommand(
            form_object=form,
            node_info=UpdateNodeInfo(node_to_update=node),
            traceability_index=index,
            project_config=self.context.project_config,
        ).perform()
        self.context.write_document_to_file(document)
        self.context.revisions[node_mid] += 1
        return ""

    def _comment(
        self, principal: Principal, node_mid: str, actions: List[Action]
    ) -> str:
        node = self.find_node(node_mid)
        if node is None or not supports_comments(node):
            return "The requirement cannot take comments."
        document = assert_cast(
            node.get_parent_or_including_document(), SDocDocument
        )
        if not can_comment(principal.role, principal.user, document):
            return "You are not a reviewer of this document."
        comments = comments_of(node)
        for action_ in actions:
            anchor = action_.data.get("anchor") or {}
            comments.append(
                Comment.new(
                    principal.user,
                    str(action_.data["body"]),
                    anchor=str(anchor.get("text", "")),
                    anchor_n=int(anchor.get("n", 0) or 0),
                )
            )
        return save_comments(self.context, node, comments) or ""

    def _insert(
        self,
        principal: Principal,
        stored: Stored,
        reference_mid: str,
        actions: List[Action],
    ) -> str:
        """Creates the nodes of one place, one after the other, as Draft."""
        if not role_allows(principal.role, ROLE_AUTHOR):
            return "Your role does not allow adding requirements."
        reference = self._index().get_node_by_mid_weak(MID(reference_mid))
        if isinstance(reference, SDocDocument):
            whereto = NodeCreationOrder.CHILD
        elif isinstance(reference, SDocNode):
            whereto = NodeCreationOrder.AFTER
        else:
            return "The place for the new requirement does not exist."
        proposals = []
        for action_ in actions:
            fields = action_.data["node"]["fields"]
            proposals.append(
                Proposal(
                    title=fields["TITLE"],
                    statement=fields["STATEMENT"],
                    rationale=fields.get("RATIONALE", ""),
                    verification_method=fields.get("VERIFICATION_METHOD", ""),
                    linked_to=list(action_.data["node"].get("linked_to", [])),
                )
            )
        result = create_proposal_nodes(
            self.context,
            reference_mid=reference_mid,
            whereto=whereto,
            proposals=proposals,
            origin=DraftOrigin(
                provider=stored.provider,
                model=stored.model,
                template=stored.template,
                user=principal.user,
            ),
        )
        return result.error

    def commands(self, scope: str) -> List[Dict[str, str]]:
        return catalogue(scope)


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf8")).hexdigest()


def _sum(calls: Calls, name: str) -> Optional[int]:
    values = [
        getattr(response_, name)
        for _, response_, _ in calls
        if response_ is not None and getattr(response_, name) is not None
    ]
    return sum(values) if values else None
