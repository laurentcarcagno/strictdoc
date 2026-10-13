"""
The role that every route needs.

There is no default: a route that is not in this table makes the server
refuse to start (see check_routes_classified), so that a new route cannot be
forgotten. A GET that opens a form that edits is classified like the POST that
saves it.

Keys are (method, path as declared in the router); "WS" is a WebSocket.
"""

import re
from typing import Dict, Iterable, Iterator, List, Optional, Pattern, Tuple

from starlette.routing import compile_path

from strictdoc.features.roles.roles import (
    ROLE_ADMINISTRATOR,
    ROLE_AUTHOR,
    ROLE_READER,
)

RouteKey = Tuple[str, str]


def _routes(role: str, *routes: str) -> Dict[RouteKey, str]:
    """The table entries of "METHOD /path" strings that need the same role."""
    entries: Dict[RouteKey, str] = {}
    for route_ in routes:
        method, path = route_.split(" ", 1)
        entries[(method, path)] = role
    return entries


ROUTE_ROLES: Dict[RouteKey, str] = {
    **_routes(
        ROLE_READER,
        "GET /",
        "GET /whoami",
        "GET /actions/show_full_node",
        "GET /search",
        "GET /autocomplete/uid",
        "GET /autocomplete/field",
        "GET /UID/{uid_or_mid}",
        "GET /fragments/document/{document_mid}/chunk",
        "GET /reqif/export_document/{document_mid}",
        "GET /reqif/export_tree",
        "GET /export_html2pdf/{document_mid}",
        "GET /{full_path:path}/static_html_search_index.js",
        "GET /{full_path:path}",
        "GET /diff",
        "GET /diff_result",
        "GET /comments",
        "GET /suspect_links",
        "GET /hierarchy",
        "GET /llm/drafts",
        "GET /llm/assist/commands",
        "GET /llm/assist/mentions",
        "POST /actions/llm/assist",
        "POST /actions/llm/apply",
        "GET /actions/project_index/export_docx_form",
        "POST /actions/project_index/export_docx_preview",
        "POST /docx/export",
        "WS /ws/{client_id}",
    ),
    # Any member may reach these; the route then checks that the user is a
    # reviewer of the document (strictdoc/features/reviewers).
    **_routes(
        ROLE_READER,
        "POST /actions/comments/add",
        "POST /actions/comments/edit",
        "POST /actions/comments/delete",
    ),
    **_routes(
        ROLE_AUTHOR,
        "GET /actions/project_index/new_document",
        "GET /actions/project_index/new_folder",
        "POST /actions/project_index/create_folder",
        "POST /actions/project_index/create_document",
        "GET /actions/reviewers/form",
        "POST /actions/reviewers/set",
        "GET /actions/document/new_requirement",
        "GET /actions/document/clone_requirement",
        "GET /actions/document/edit_requirement",
        "GET /reset_uid",
        "GET /actions/document/cancel_new_requirement",
        "GET /actions/document/cancel_edit_requirement",
        "GET /actions/document/show_move_node",
        "GET /actions/document/new_comment",
        "GET /actions/document/new_relation",
        "GET /actions/table/get_node_comments_inline",
        "GET /actions/table/get_node_relations_inline",
        "GET /actions/table/get_node_autocomplete_inline",
        "GET /actions/table/get_node_contenteditable_inline",
        "POST /actions/document/create_requirement",
        "POST /actions/document/update_requirement",
        "POST /actions/document/upload_asset",
        "POST /actions/document/move_node",
        "POST /actions/document/move_node_across_documents",
        "POST /actions/table/add_node",
        "POST /actions/table/update_node_field",
        "POST /actions/table/update_node_field_multiline",
        "POST /actions/table/update_node_comments",
        "POST /actions/table/update_node_relations",
        "DELETE /actions/table/delete_node",
        "DELETE /actions/document/delete_requirement",
        "POST /actions/comments/resolve",
        "POST /actions/comments/reopen",
        "POST /actions/suspect/clear",
        "GET /llm/draft",
        "POST /actions/llm/draft",
        "POST /actions/llm/create",
        "GET /actions/project_index/import_docx_form",
        "POST /actions/project_index/import_docx_preview",
        "POST /actions/project_index/import_docx",
    ),
    **_routes(
        ROLE_ADMINISTRATOR,
        "GET /actions/project_index/edit_project_title_form",
        "GET /actions/project_index/import_reqif_document_form",
        "GET /actions/document/edit_config",
        "GET /actions/document/cancel_edit_config",
        "GET /actions/document/new_metadata",
        "GET /actions/document/edit_included_document",
        "GET /actions/document/cancel_edit_included_document",
        "GET /actions/document/edit_grammar",
        "GET /actions/document/add_grammar_element",
        "GET /actions/document/edit_grammar_element",
        "GET /actions/document/add_grammar_field",
        "GET /actions/document/add_grammar_relation",
        "GET /actions/table/get_document_config_field_inline",
        "GET /actions/table/get_document_custom_meta_inline",
        "GET /actions/table/get_document_custom_meta_new_inline",
        "GET /__nestor",
        "GET /audit",
        "GET /members",
        "POST /actions/members/set",
        "POST /actions/members/remove",
        "POST /actions/suspect/baseline",
        "POST /actions/hierarchy/resolve_references",
        # FastAPI's own documentation of the routes (disabled behind a login
        # proxy, see create_app).
        "GET /openapi.json",
        "GET /docs",
        "GET /docs/oauth2-redirect",
        "GET /redoc",
        "POST /actions/project_index/save_project_title",
        "POST /actions/project_index/import_document_reqif",
        "POST /actions/document/save_config",
        "POST /actions/document/save_included_document",
        "POST /actions/document/save_grammar",
        "POST /actions/document/save_grammar_element",
        "POST /actions/table/update_document_config_field",
        "POST /actions/table/update_document_custom_meta",
        "DELETE /actions/document/delete_document",
    ),
}


def _flatten(routes: Iterable[object]) -> Iterator[object]:
    """
    The routes of an application, with the routers that were included in it
    opened. Recent FastAPI versions keep an included router as one object that
    can list its routes; older ones list them directly.
    """
    for route_ in routes:
        opener = getattr(route_, "effective_route_contexts", None)
        if opener is not None:
            yield from _flatten(opener())
        else:
            yield route_


def route_keys(routes: Iterable[object]) -> List[RouteKey]:
    """The (method, path) pairs of the routes of an application."""
    keys: List[RouteKey] = []
    for route_ in _flatten(routes):
        path = getattr(route_, "path", None)
        if path is None:
            continue
        methods = getattr(route_, "methods", None)
        if methods is None:
            # A WebSocket route has no methods.
            keys.append(("WS", path))
            continue
        for method_ in sorted(methods):
            if method_ in ("HEAD", "OPTIONS"):
                continue
            keys.append((method_, path))
    return keys


def check_routes_classified(routes: Iterable[object]) -> None:
    """Raises when a route has no role. The server must not start then."""
    missing = [key_ for key_ in route_keys(routes) if key_ not in ROUTE_ROLES]
    if len(missing) > 0:
        listing = "\n".join(
            f"  {method_} {path_}" for method_, path_ in missing
        )
        raise RuntimeError(
            "These routes have no role in "
            "strictdoc/features/roles/route_roles.py:\n" + listing
        )


def _specificity(path: str) -> int:
    """How much of a path is fixed text: a catch-all has the least."""
    return len(re.sub(r"\{[^}]*\}", "", path))


# (method, path) of the table, the most specific first, with the expression
# that matches a request path.
_MATCHERS: List[Tuple[RouteKey, Pattern[str]]] = sorted(
    ((key_, compile_path(key_[1])[0]) for key_ in ROUTE_ROLES),
    key=lambda item_: -_specificity(item_[0][1]),
)


def match_route_key(method: str, path: str) -> Optional[RouteKey]:
    """
    The table entry that serves a request ("WS" for a WebSocket), choosing
    the most specific path when several match, as the router does.
    """
    for key_, expression_ in _MATCHERS:
        if key_[0] == method and expression_.match(path) is not None:
            return key_
    return None
