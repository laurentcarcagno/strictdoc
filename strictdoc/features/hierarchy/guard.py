"""
Keeps the write routes away from input documents.

The can_edit_* predicates of the traceability index already protect the
routes that call them and hide the edit controls. A write route that does not
call a predicate (create, move, upload, table edits) is covered here: the
nodes and documents it names, in the query or in the form, must not be in a
read-only input document.
"""

from typing import TYPE_CHECKING, Any, Awaitable, Callable, Iterable, List

from fastapi import HTTPException, Request

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.helpers.mid import MID

if TYPE_CHECKING:
    from strictdoc.core.traceability_index import TraceabilityIndex

COMMENT_ROUTES = "/actions/comments/"

# The parameters that name the node or the document a route works on.
MID_PARAMETERS = (
    "document_mid",
    "context_document_mid",
    "doc_mid",
    "requirement_mid",
    "node_mid",
    "node_id",
    "target_mid",
    "target_node_mid",
    "moved_node_mid",
)


def create_input_guard(
    get_index: Callable[[], "TraceabilityIndex"],
) -> Callable[[Request], Awaitable[None]]:
    async def guard(request: Request) -> None:
        # A review comment is not an edit of the document: reviewers comment
        # on the customer's text (the comments feature checks its own role).
        if request.url.path.startswith(COMMENT_ROUTES):
            return
        index = get_index()
        values: List[str] = list(_values(request.query_params))
        content_type = request.headers.get("content-type", "")
        if content_type.startswith(
            ("application/x-www-form-urlencoded", "multipart/form-data")
        ):
            values.extend(_values(await request.form()))
        for mid in values:
            node: Any = index.get_node_by_mid_weak(MID(mid))
            if isinstance(node, SDocNode):
                document = node.get_parent_or_including_document()
            elif isinstance(node, SDocDocument):
                document = node
            else:
                continue
            if not index.input_allows_edit(document):
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "This is an input document: it is read-only. "
                        "Import a new revision to change it."
                    ),
                )

    return guard


def _values(parameters: Any) -> Iterable[str]:
    for name in MID_PARAMETERS:
        value = parameters.get(name)
        if isinstance(value, str) and len(value) > 0:
            yield value
