"""
Reading and changing the comments of a node.

The comments of a node are its COMMENT fields. A change builds the form of the
node, replaces its comments and saves it through the same command as an edit
in the interface, so that every validation and the revision counter apply.
"""

from typing import TYPE_CHECKING, List, Optional

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.core.transforms.update_requirement import (
    CreateOrUpdateNodeCommand,
    UpdateNodeInfo,
)
from strictdoc.export.html.form_objects.requirement_form_object import (
    RequirementFormField,
    RequirementFormObject,
)
from strictdoc.features.comments.model import (
    Comment,
    format_comment,
    parse_comment,
)
from strictdoc.helpers.cast import assert_cast

if TYPE_CHECKING:
    from strictdoc.server.project_context import ProjectContext

LEGACY_PREFIX = "legacy-"


def comments_of(node: SDocNode) -> List[Comment]:
    """The comments of a node, in file order. A legacy one gets a stable id."""
    comments: List[Comment] = []
    for index_, field_ in enumerate(node.get_comment_fields()):
        comment = parse_comment(field_.get_text_value())
        if comment.legacy:
            comment.id = f"{LEGACY_PREFIX}{index_}"
        comments.append(comment)
    return comments


def supports_comments(node: SDocNode) -> bool:
    document = assert_cast(node.get_document(), SDocDocument)
    assert document.grammar is not None
    element = document.grammar.elements_by_type.get(node.node_type)
    return element is not None and "COMMENT" in element.fields_map


def find_comment(comments: List[Comment], comment_id: str) -> Optional[int]:
    for index_, comment_ in enumerate(comments):
        if comment_.id == comment_id:
            return index_
    return None


def save_comments(
    context: "ProjectContext", node: SDocNode, comments: List[Comment]
) -> Optional[str]:
    """
    Replaces the comments of the node and saves the document. Returns None, or
    the message of the validation error that stopped the change.
    """
    document = assert_cast(node.get_document(), SDocDocument)
    assert document.grammar is not None
    markup = document.config.get_markup()
    node_mid = node.reserved_mid.get_string_value()
    element = document.grammar.elements_by_type[node.node_type]
    revision = context.revisions[node_mid]

    form_object = RequirementFormObject.create_from_requirement(
        requirement=node,
        revision=revision,
        context_document_mid=document.reserved_mid,
    )
    if len(comments) == 0:
        form_object.fields.pop("COMMENT", None)
    else:
        form_object.fields["COMMENT"] = [
            RequirementFormField.create_from_grammar_field(
                grammar_field=element.fields_map["COMMENT"],
                multiline=True,
                # A legacy comment that is kept as it is gets no header.
                value=(
                    comment_.body
                    if comment_.legacy
                    else format_comment(comment_, markup)
                ),
            )
            for comment_ in comments
        ]
    form_object.validate(
        traceability_index=context.export_action.traceability_index,
        context_document=document,
        config=context.project_config,
        existing_revision=revision,
    )
    if form_object.any_errors():
        errors = [
            message_
            for messages_ in form_object.errors.values()
            for message_ in messages_
        ]
        return " ".join(errors) or "The comment could not be saved."

    CreateOrUpdateNodeCommand(
        form_object=form_object,
        node_info=UpdateNodeInfo(node_to_update=node),
        traceability_index=context.export_action.traceability_index,
        project_config=context.project_config,
    ).perform()
    context.write_document_to_file(document)
    context.revisions[node_mid] += 1
    return None
