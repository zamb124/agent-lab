"""Регистрация WS command-handler'ов wiki в `core.websocket`."""

from __future__ import annotations

from apps.wiki.container import WikiContainer, get_wiki_container
from apps.wiki.models.api import (
    WikiMarkdownImportRequest,
    WikiMarkdownParseRequest,
    WikiPageCreateRequest,
    WikiSearchRequest,
)
from apps.wiki.realtime.operations import (
    WikiBacklinksPayload,
    WikiChildrenPayload,
    WikiCommentCreatePayload,
    WikiCommentIdPayload,
    WikiCommentResolvePayload,
    WikiCompanyVisiblePayload,
    WikiEmptyPayload,
    WikiMarkdownImportPagePayload,
    WikiMemberRemovePayload,
    WikiMemberUpsertPayload,
    WikiPageContentUpdatePayload,
    WikiPageIdPayload,
    WikiPageMoveNamespacePayload,
    WikiPageMovePayload,
    WikiPagePropertiesUpdatePayload,
    WikiPublicLinkPayload,
    WikiRevisionIdPayload,
    WikiRevisionsListPayload,
    op_backlinks_list,
    op_comments_remove,
    op_comments_resolve,
    op_pages_access,
    op_pages_children_list,
    op_pages_comment_create,
    op_pages_comments_list,
    op_pages_company_visible,
    op_pages_content_update,
    op_pages_create,
    op_pages_deleted_list,
    op_pages_get,
    op_pages_list,
    op_pages_markdown,
    op_pages_markdown_create,
    op_pages_markdown_import,
    op_pages_markdown_parse,
    op_pages_member_add,
    op_pages_member_remove,
    op_pages_move,
    op_pages_move_namespace,
    op_pages_properties_update,
    op_pages_public_link,
    op_pages_remove,
    op_pages_restore,
    op_pages_revisions_list,
    op_revisions_get,
    op_revisions_restore,
    op_search_run,
)
from core.logging import get_logger
from core.namespace.operations import NamespacesListPayload, op_namespaces_list
from core.websocket import Operation, RegisteredOperation, register_service_operations

logger = get_logger(__name__)

WIKI_OPERATIONS: dict[str, RegisteredOperation[WikiContainer]] = {
    "wiki/pages/list_requested": Operation(payload_model=WikiEmptyPayload, fn=op_pages_list),
    "wiki/pages/deleted_list_requested": Operation(
        payload_model=WikiEmptyPayload, fn=op_pages_deleted_list
    ),
    "wiki/pages/item_requested": Operation(payload_model=WikiPageIdPayload, fn=op_pages_get),
    "wiki/pages/create_requested": Operation(
        payload_model=WikiPageCreateRequest, fn=op_pages_create
    ),
    "wiki/pages/content_update_requested": Operation(
        payload_model=WikiPageContentUpdatePayload, fn=op_pages_content_update
    ),
    "wiki/pages/properties_update_requested": Operation(
        payload_model=WikiPagePropertiesUpdatePayload, fn=op_pages_properties_update
    ),
    "wiki/pages/move_requested": Operation(
        payload_model=WikiPageMovePayload, fn=op_pages_move
    ),
    "wiki/pages/move_namespace_requested": Operation(
        payload_model=WikiPageMoveNamespacePayload, fn=op_pages_move_namespace
    ),
    "wiki/pages/remove_requested": Operation(
        payload_model=WikiPageIdPayload, fn=op_pages_remove
    ),
    "wiki/pages/restore_requested": Operation(
        payload_model=WikiPageIdPayload, fn=op_pages_restore
    ),
    "wiki/pages/markdown_requested": Operation(
        payload_model=WikiPageIdPayload, fn=op_pages_markdown
    ),
    "wiki/pages/markdown_parse_requested": Operation(
        payload_model=WikiMarkdownParseRequest, fn=op_pages_markdown_parse
    ),
    "wiki/pages/markdown_create_requested": Operation(
        payload_model=WikiMarkdownImportRequest, fn=op_pages_markdown_create
    ),
    "wiki/pages/markdown_import_requested": Operation(
        payload_model=WikiMarkdownImportPagePayload, fn=op_pages_markdown_import
    ),
    "wiki/pages/children_list_requested": Operation(
        payload_model=WikiChildrenPayload, fn=op_pages_children_list
    ),
    "wiki/pages/access_requested": Operation(
        payload_model=WikiPageIdPayload, fn=op_pages_access
    ),
    "wiki/pages/company_visible_requested": Operation(
        payload_model=WikiCompanyVisiblePayload, fn=op_pages_company_visible
    ),
    "wiki/pages/member_add_requested": Operation(
        payload_model=WikiMemberUpsertPayload, fn=op_pages_member_add
    ),
    "wiki/pages/member_remove_requested": Operation(
        payload_model=WikiMemberRemovePayload, fn=op_pages_member_remove
    ),
    "wiki/pages/public_link_requested": Operation(
        payload_model=WikiPublicLinkPayload, fn=op_pages_public_link
    ),
    "wiki/pages/revisions_list_requested": Operation(
        payload_model=WikiRevisionsListPayload, fn=op_pages_revisions_list
    ),
    "wiki/pages/comments_list_requested": Operation(
        payload_model=WikiPageIdPayload, fn=op_pages_comments_list
    ),
    "wiki/pages/comment_create_requested": Operation(
        payload_model=WikiCommentCreatePayload, fn=op_pages_comment_create
    ),
    "wiki/revisions/item_requested": Operation(
        payload_model=WikiRevisionIdPayload, fn=op_revisions_get
    ),
    "wiki/revisions/restore_requested": Operation(
        payload_model=WikiRevisionIdPayload, fn=op_revisions_restore
    ),
    "wiki/comments/resolve_requested": Operation(
        payload_model=WikiCommentResolvePayload, fn=op_comments_resolve
    ),
    "wiki/comments/remove_requested": Operation(
        payload_model=WikiCommentIdPayload, fn=op_comments_remove
    ),
    "wiki/search/run_requested": Operation(payload_model=WikiSearchRequest, fn=op_search_run),
    "wiki/backlinks/list_requested": Operation(
        payload_model=WikiBacklinksPayload, fn=op_backlinks_list
    ),
    "wiki/namespaces/list_requested": Operation(
        payload_model=NamespacesListPayload, fn=op_namespaces_list
    ),
}


def register_wiki_ws_commands() -> None:
    register_service_operations(WIKI_OPERATIONS, get_wiki_container)
    logger.info(
        "Wiki WS command-handlers зарегистрированы (%d операций)",
        len(WIKI_OPERATIONS),
    )
