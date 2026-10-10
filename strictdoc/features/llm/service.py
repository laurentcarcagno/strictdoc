"""
Creating the nodes that a person accepted from a draft.

The nodes are created through the same form object and command as a node typed
in the interface, so every validation applies. Each one gets STATUS Draft (when
the grammar has the field) and a comment that says it came from a model:
provider, model, prompt version and the person who accepted it.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Sequence

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.core.analyzers.document_uid_analyzer import DocumentUIDAnalyzer
from strictdoc.core.transforms.constants import NodeCreationOrder
from strictdoc.core.transforms.update_requirement import (
    CreateNodeInfo,
    CreateOrUpdateNodeCommand,
)
from strictdoc.export.html.document_type import DocumentType
from strictdoc.export.html.form_objects.requirement_form_object import (
    RequirementFormField,
    RequirementFormObject,
    RequirementReferenceFormField,
)
from strictdoc.features.comments.model import Comment, format_comment, now_iso
from strictdoc.features.llm.schema import Proposal
from strictdoc.helpers.cast import assert_cast
from strictdoc.helpers.mid import MID

if TYPE_CHECKING:
    from strictdoc.server.project_context import ProjectContext

STATUS_DRAFT = "Draft"
ELEMENT_TYPE = "REQUIREMENT"


@dataclass
class DraftOrigin:
    provider: str
    model: str
    template: str
    user: str


@dataclass
class CreationResult:
    created_uids: List[str] = field(default_factory=list)
    error: str = ""


def create_proposal_nodes(
    context: "ProjectContext",
    *,
    reference_mid: str,
    whereto: str,
    proposals: Sequence[Proposal],
    origin: DraftOrigin,
) -> CreationResult:
    """
    Creates one node per proposal, the first one at `whereto` of the reference
    node, the next ones after the previous. Stops at the first error and
    reports it; what was created before stays.
    """
    index = context.export_action.traceability_index
    result = CreationResult()
    reference: object = index.get_node_by_mid(MID(reference_mid))
    where = whereto
    for proposal_ in proposals:
        if not isinstance(reference, (SDocDocument, SDocNode)):
            result.error = "The reference node does not exist."
            return result
        if not index.can_create_node_at(reference, where):
            result.error = "Adding nodes here is not allowed."
            return result
        document = _document_for(reference)
        error, node = _create_one(
            context, document, reference, where, proposal_, origin
        )
        if error or node is None:
            result.error = error or "The node could not be created."
            return result
        result.created_uids.append(node.reserved_uid or "")
        reference, where = node, NodeCreationOrder.AFTER
    return result


def _document_for(reference: object) -> SDocDocument:
    if isinstance(reference, SDocDocument):
        return reference
    node = assert_cast(reference, SDocNode)
    return assert_cast(node.get_document(), SDocDocument)


def _next_uid(
    context: "ProjectContext",
    document: SDocDocument,
    reference: object,
) -> Optional[str]:
    index = context.export_action.traceability_index
    config = context.project_config
    assert document.grammar is not None
    element = document.grammar.elements_by_type[ELEMENT_TYPE]
    stats = DocumentUIDAnalyzer.analyze_document_tree(
        index, project_config=config
    )
    prefix = config.resolve_custom_node_prefix(
        reference, element, document, index
    ) or assert_cast(
        reference, (SDocDocument, SDocNode)
    ).get_prefix_for_new_node(ELEMENT_TYPE)
    if prefix is None:
        return None
    number = stats.get_next_requirement_uid_number(prefix)
    return (
        config.resolve_custom_node_uid(
            prefix,
            number,
            node=reference,
            grammar_element=element,
            document=document,
            traceability_index=index,
        )
        or f"{prefix}{number}"
    )


def _create_one(
    context: "ProjectContext",
    document: SDocDocument,
    reference: object,
    whereto: str,
    proposal: Proposal,
    origin: DraftOrigin,
) -> "tuple[str, Optional[SDocNode]]":
    index = context.export_action.traceability_index
    config = context.project_config
    assert document.grammar is not None
    element = document.grammar.elements_by_type[ELEMENT_TYPE]
    markup = document.config.get_markup()

    form = RequirementFormObject.create_new(
        document=document,
        context_document_mid=document.reserved_mid,
        next_uid=_next_uid(context, document, reference),
        element_type=ELEMENT_TYPE,
    )
    _set(form, "TITLE", proposal.title)
    _set(form, element.content_field[0], proposal.statement)
    if proposal.rationale:
        _set(form, "RATIONALE", proposal.rationale)
    _set(form, "STATUS", STATUS_DRAFT)
    field_name = config.llm.verification_field if config.llm else ""
    if field_name and proposal.verification_method:
        _set(form, field_name, proposal.verification_method)
    if "COMMENT" in element.fields_map:
        comment = Comment(
            body=(
                "Drafted by a language model from the instruction of "
                f"{origin.user}. Review before use."
            ),
            id="llm" + MID.create().get_string_value()[:5],
            author=origin.provider,
            date=now_iso(),
            source="llm",
            model=origin.model,
            provider=origin.provider,
            prompt=origin.template,
            accepted_by=origin.user,
        )
        form.fields["COMMENT"] = [
            RequirementFormField.create_from_grammar_field(
                grammar_field=element.fields_map["COMMENT"],
                multiline=True,
                value=format_comment(comment, markup),
            )
        ]
    for uid_ in proposal.linked_to:
        form.reference_fields.append(
            RequirementReferenceFormField(
                field_mid=MID.create().get_string_value(),
                field_type=RequirementReferenceFormField.FieldType.PARENT,
                field_value=uid_,
                field_role=None,
                is_new=True,
            )
        )
    form.validate(
        traceability_index=index,
        context_document=document,
        config=config,
        existing_revision=0,
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
        return " ".join(messages) or "The node is not valid.", None

    CreateOrUpdateNodeCommand(
        form_object=form,
        node_info=CreateNodeInfo(
            whereto=whereto,
            requirement_mid=form.requirement_mid,
            reference_mid=_mid_of(reference),
        ),
        traceability_index=index,
        project_config=config,
    ).perform()
    context.write_document_to_file(document)
    context.html_generator.export_single_document_with_performance(
        document=document,
        traceability_index=index,
        specific_documents=(DocumentType.DOCUMENT,),
    )
    node = index.get_node_by_mid(MID(form.requirement_mid))
    return "", assert_cast(node, SDocNode)


def _mid_of(reference: object) -> str:
    mid = assert_cast(reference, (SDocDocument, SDocNode)).reserved_mid
    return mid if isinstance(mid, str) else mid.get_string_value()


def _set(form: RequirementFormObject, name: str, value: str) -> None:
    for field_ in form.fields.get(name, []):
        field_.field_value = value
        return
