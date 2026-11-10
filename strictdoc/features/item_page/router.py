"""
The page of one item (a node of a document) at /item/{uid_or_mid}: its
content, its links grouped by relation role, its comments and its history in
Git. /UID/{uid_or_mid} is the stable link that redirects to the node in its
document; this page is the item itself.

The role each route needs is in strictdoc/features/roles/route_roles.py.

@relation(SDOC-SRS-213, scope=file)
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response

from strictdoc.backend.sdoc.models.document import SDocDocument
from strictdoc.backend.sdoc.models.model import RequirementFieldName
from strictdoc.backend.sdoc.models.node import SDocNode
from strictdoc.export.html.document_type import DocumentType
from strictdoc.export.html.generators.view_objects.app_screen_view_object import (
    render_app_screen,
)
from strictdoc.export.html.renderers.link_renderer import LinkRenderer
from strictdoc.export.html.renderers.markup_renderer import MarkupRenderer
from strictdoc.features.comments.service import comments_of, supports_comments
from strictdoc.features.git_config.git_service import (
    GitService,
    GitServiceError,
)
from strictdoc.features.i18n.i18n import gettext
from strictdoc.features.item_page.service import (
    block_lines_of_uid,
    relation_groups,
)
from strictdoc.helpers.cast import assert_cast
from strictdoc.helpers.mid import MID
from strictdoc.server.project_context import ProjectContext

TAB_CONTENT = "content"
TAB_LINKS = "links"
TAB_COMMENTS = "comments"
TAB_HISTORY = "history"
TABS = (TAB_CONTENT, TAB_LINKS, TAB_COMMENTS, TAB_HISTORY)


def create_item_page_router(*, context: ProjectContext) -> APIRouter:
    router = APIRouter()

    def find_linkable(uid_or_mid: str) -> Optional[Any]:
        index = context.export_action.traceability_index
        linkable = index.get_node_by_mid_weak(MID(uid_or_mid))
        if linkable is None:
            linkable = index.get_linkable_node_by_uid_weak(uid_or_mid)
        return linkable

    def link_to_document(linkable: Any) -> str:
        link_renderer = LinkRenderer(
            root_path="",
            static_path=context.project_config.dir_for_sdoc_assets,
        )
        return "/" + link_renderer.render_node_link(
            linkable, None, document_type=DocumentType.DOCUMENT
        )

    def content_of(node: SDocNode) -> List[Dict[str, Any]]:
        """The statement, then the other fields, each as rendered HTML."""
        document = assert_cast(node.get_document(), SDocDocument)
        assert document.meta is not None
        renderer = MarkupRenderer.create(
            markup=document.config.get_markup(),
            traceability_index=context.export_action.traceability_index,
            link_renderer=LinkRenderer(
                root_path=document.meta.get_root_path_prefix(),
                static_path=context.project_config.dir_for_sdoc_assets,
            ),
            html_templates=context.html_generator.html_templates,
            config=context.project_config,
            context_document=document,
        )
        rows: List[Dict[str, Any]] = [
            {
                "title": node.get_field_human_title_for_statement(),
                "html": renderer.render_node_statement(
                    DocumentType.DOCUMENT, node
                ),
            }
        ]
        if RequirementFieldName.RATIONALE in node.ordered_fields_lookup:
            rows.append(
                {
                    "title": node.get_field_human_title(
                        RequirementFieldName.RATIONALE
                    ),
                    "html": renderer.render_node_rationale(
                        DocumentType.DOCUMENT, node
                    ),
                }
            )
        for title_, field_ in node.enumerate_meta_fields():
            rows.append(
                {
                    "title": title_,
                    "html": renderer.render_node_field(
                        DocumentType.DOCUMENT, field_
                    ),
                }
            )
        return rows

    def history_of(node: SDocNode) -> Dict[str, Any]:
        """Either the revisions, or the reason why there are none."""
        committer = context.git_committer
        if committer is None:
            return {
                "revisions": [],
                "reason": gettext(
                    "Configuration management is not activated, so the "
                    "history is not recorded."
                ),
            }
        document = assert_cast(node.get_document(), SDocDocument)
        assert document.meta is not None
        path = document.meta.input_doc_full_path
        lines = (
            block_lines_of_uid(path, node.reserved_uid)
            if node.reserved_uid is not None
            else None
        )
        if lines is None:
            return {
                "revisions": [],
                "reason": gettext(
                    "The item has no UID in its file, so its lines cannot "
                    "be followed."
                ),
            }
        service: GitService = committer.service
        try:
            revisions = service.history_of_lines(path, lines[0], lines[1])
        except GitServiceError as error:
            return {"revisions": [], "reason": str(error)}
        return {"revisions": revisions, "reason": ""}

    @router.get("/item/{uid_or_mid}", response_class=Response)
    def item_page(
        uid_or_mid: str, tab: str = TAB_CONTENT, role: str = ""
    ) -> Response:
        linkable = find_linkable(uid_or_mid)
        if linkable is None:
            raise HTTPException(
                status_code=404, detail="UID or MID was not found"
            )
        if (
            not isinstance(linkable, SDocNode)
            or not linkable.is_normative_node()
        ):
            return RedirectResponse(
                url=link_to_document(linkable), status_code=302
            )
        node: SDocNode = linkable
        if tab not in TABS:
            tab = TAB_CONTENT

        groups = relation_groups(context.export_action.traceability_index, node)
        selected_groups = [
            group_ for group_ in groups if role in ("", group_.key)
        ]

        comments_reason = ""
        comments: List[Any] = []
        if not context.project_config.is_activated_comments():
            comments_reason = gettext("The comments are not activated.")
        elif not supports_comments(node):
            comments_reason = gettext("This kind of item has no COMMENT field.")
        else:
            comments = comments_of(node)

        history: Dict[str, Any] = {"revisions": [], "reason": ""}
        if tab == TAB_HISTORY:
            history = history_of(node)

        uid = node.reserved_uid or node.reserved_mid.get_string_value()
        output = render_app_screen(
            jinja_environment=context.env(),
            project_config=context.project_config,
            title=uid,
            viewtype="item-page",
            content_template="features/item_page/item.jinja.html",
            node=node,
            uid=uid,
            tab=tab,
            tabs=TABS,
            document_link=link_to_document(node),
            document_title=assert_cast(node.get_document(), SDocDocument).title,
            content=content_of(node) if tab == TAB_CONTENT else [],
            groups=groups,
            selected_groups=selected_groups,
            selected_role=role,
            comments=comments,
            comments_reason=comments_reason,
            history=history,
        )
        return HTMLResponse(content=output, status_code=200)

    return router
