"""Бизнес-функции wiki: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from pydantic import Field

from apps.wiki.base_model import WikiBaseModel
from apps.wiki.content.markdown_file import markdown_file_name, split_markdown_file
from apps.wiki.content.markdown_parser import (
    WikiMarkdownError,
    markdown_to_document,
    parse_markdown,
)
from apps.wiki.content.prosemirror import ProseMirrorNode
from apps.wiki.content.schema import WikiSchemaError
from apps.wiki.di import Di
from apps.wiki.models.api import (
    WikiCommentCreateRequest,
    WikiCommentResolveRequest,
    WikiCompanyVisibleRequest,
    WikiMarkdownImportRequest,
    WikiMarkdownImportResponse,
    WikiMarkdownParseRequest,
    WikiMarkdownParseResponse,
    WikiMarkdownResponse,
    WikiMemberUpsertRequest,
    WikiPageContentUpdateRequest,
    WikiPageCreateRequest,
    WikiPageMoveNamespaceRequest,
    WikiPageMoveRequest,
    WikiPagePropertiesUpdateRequest,
    WikiPageResponse,
    WikiPublicLinkRequest,
    WikiPublicLinkResponse,
    WikiSearchRequest,
    WikiTreeResponse,
)
from apps.wiki.models.comment import WikiComment
from apps.wiki.models.domain import (
    WikiBacklink,
    WikiLinkTargetKind,
    WikiPageAccess,
    WikiPageSummary,
    WikiRevisionSummary,
    WikiSearchHit,
)
from apps.wiki.models.revision import WikiRevision
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.errors.boundary import PlatformAccessDeniedError, PlatformNotFoundError
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.pagination import ListResponse
from core.request_scope import NamespaceScope, require_company, require_namespace
from core.websocket import (
    EmptyPayload,
    WsCommandError,
    raise_forbidden,
    raise_invalid,
    raise_not_found,
)


class WikiPageIdPayload(StrictBaseModel):
    wiki_page_id: str = Field(min_length=1)


class WikiPageContentUpdatePayload(WikiPageContentUpdateRequest):
    wiki_page_id: str = Field(min_length=1)


class WikiPagePropertiesUpdatePayload(WikiPagePropertiesUpdateRequest):
    wiki_page_id: str = Field(min_length=1)


class WikiPageMovePayload(WikiPageMoveRequest):
    wiki_page_id: str = Field(min_length=1)


class WikiPageMoveNamespacePayload(WikiPageMoveNamespaceRequest):
    wiki_page_id: str = Field(min_length=1)


class WikiMarkdownImportPagePayload(WikiMarkdownImportRequest):
    wiki_page_id: str = Field(min_length=1)


class WikiMemberUpsertPayload(WikiMemberUpsertRequest):
    wiki_page_id: str = Field(min_length=1)


class WikiMemberRemovePayload(StrictBaseModel):
    wiki_page_id: str = Field(min_length=1)
    member_user_id: str = Field(min_length=1)


class WikiCompanyVisiblePayload(WikiCompanyVisibleRequest):
    wiki_page_id: str = Field(min_length=1)


class WikiPublicLinkPayload(WikiPublicLinkRequest):
    wiki_page_id: str = Field(min_length=1)
    origin: str = Field(min_length=1)


class WikiCommentCreatePayload(WikiCommentCreateRequest):
    wiki_page_id: str = Field(min_length=1)


class WikiCommentResolvePayload(WikiCommentResolveRequest):
    wiki_comment_id: str = Field(min_length=1)


class WikiCommentIdPayload(StrictBaseModel):
    wiki_comment_id: str = Field(min_length=1)


class WikiRevisionIdPayload(StrictBaseModel):
    wiki_revision_id: str = Field(min_length=1)


class WikiRevisionsListPayload(StrictBaseModel):
    wiki_page_id: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=200)


class WikiChildrenPayload(StrictBaseModel):
    wiki_page_id: str = Field(min_length=1)
    include_self: bool = False


class WikiBacklinksPayload(WikiBaseModel):
    target_kind: WikiLinkTargetKind
    target_id: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=200)


class WikiMarkdownFileResult(StrictBaseModel):
    body: str
    file_name: str


async def _scope(di: Di) -> NamespaceScope:
    scope = await require_namespace(di.namespace_service)
    try:
        await di.authz_service.require_can_view(
            AuthzObject.platform_namespace(scope.company_id, scope.namespace),
            user_id=scope.user_id,
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    return scope


def _resolve_content(
    content: ProseMirrorNode | None, markdown: str | None
) -> ProseMirrorNode | None:
    if content is not None and markdown is not None:
        raise ValueError("Specify either content or markdown, not both")
    if markdown is None:
        return content
    try:
        return markdown_to_document(markdown)
    except WikiMarkdownError as exc:
        raise ValueError(f"Markdown is not parsed: {exc}") from exc


async def op_pages_list(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> WikiTreeResponse:
    _ = payload, user
    scope = await _scope(di)
    items = await di.wiki_service.list_tree(scope.company_id, scope.namespace, scope.user_id)
    return WikiTreeResponse(namespace=scope.namespace, items=items)


async def op_pages_deleted_list(
    payload: EmptyPayload,
    *,
    user: User,
    di: Di,
) -> WikiTreeResponse:
    _ = payload, user
    scope = await _scope(di)
    items = await di.wiki_service.list_deleted(scope.company_id, scope.namespace)
    return WikiTreeResponse(namespace=scope.namespace, items=items)


async def op_pages_create(
    payload: WikiPageCreateRequest,
    *,
    user: User,
    di: Di,
) -> WikiPageResponse:
    _ = user
    scope = await _scope(di)
    try:
        content = _resolve_content(payload.content, payload.markdown)
        page = await di.wiki_service.create_page(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            title=payload.title,
            parent_page_id=payload.parent_page_id,
            content=content,
            icon=payload.icon,
        )
    except WikiSchemaError as exc:
        raise_invalid(exc)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No permission to create a page", error_code='forbidden') from exc
    except ValueError as exc:
        raise_invalid(exc)
    return await di.wiki_service.page_response(page, user_id=scope.user_id)


async def op_pages_get(
    payload: WikiPageIdPayload,
    *,
    user: User,
    di: Di,
) -> WikiPageResponse:
    _ = user
    scope = await _scope(di)
    try:
        page = await di.wiki_service.require_viewable_page(
            scope.company_id, scope.namespace, payload.wiki_page_id, scope.user_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No access to page", error_code='forbidden') from exc
    return await di.wiki_service.page_response(page, user_id=scope.user_id)


async def op_pages_markdown(
    payload: WikiPageIdPayload,
    *,
    user: User,
    di: Di,
) -> WikiMarkdownResponse:
    _ = user
    scope = await _scope(di)
    try:
        page = await di.wiki_service.require_viewable_page(
            scope.company_id, scope.namespace, payload.wiki_page_id, scope.user_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No access to page", error_code='forbidden') from exc
    return WikiMarkdownResponse(
        wiki_page_id=page.wiki_page_id,
        title=page.title,
        markdown=page.text_markdown,
    )


async def op_pages_markdown_file(
    payload: WikiPageIdPayload,
    *,
    user: User,
    di: Di,
) -> WikiMarkdownFileResult:
    _ = user
    scope = await _scope(di)
    try:
        page = await di.wiki_service.require_viewable_page(
            scope.company_id, scope.namespace, payload.wiki_page_id, scope.user_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No access to page", error_code='forbidden') from exc
    return WikiMarkdownFileResult(
        body=di.wiki_service.export_markdown_file(page),
        file_name=markdown_file_name(page.title, page.wiki_page_id),
    )


async def op_pages_markdown_parse(
    payload: WikiMarkdownParseRequest,
    *,
    user: User,
    di: Di,
) -> WikiMarkdownParseResponse:
    _ = user
    _ = await _scope(di)
    parts = split_markdown_file(payload.markdown)
    try:
        parsed = parse_markdown(parts.body)
    except WikiMarkdownError as exc:
        raise WsCommandError("ws_invalid_payload", f"Markdown is not parsed: {exc}", error_code='ws_invalid_payload') from exc
    return WikiMarkdownParseResponse(
        document=parsed.document, notices=[*parts.notices, *parsed.notices]
    )


async def op_pages_markdown_create(
    payload: WikiMarkdownImportRequest,
    *,
    user: User,
    di: Di,
) -> WikiMarkdownImportResponse:
    _ = user
    scope = await _scope(di)
    try:
        page, notices = await di.wiki_service.import_markdown(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            markdown=payload.markdown,
            parent_page_id=payload.parent_page_id,
            apply_front_matter=payload.apply_front_matter,
        )
    except WikiMarkdownError as exc:
        raise WsCommandError("ws_invalid_payload", f"Markdown is not parsed: {exc}", error_code='ws_invalid_payload') from exc
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No permission to create a page", error_code='forbidden') from exc
    return WikiMarkdownImportResponse(page=page, notices=notices)


async def op_pages_markdown_import(
    payload: WikiMarkdownImportPagePayload,
    *,
    user: User,
    di: Di,
) -> WikiMarkdownImportResponse:
    _ = user
    scope = await _scope(di)
    try:
        page, notices = await di.wiki_service.import_markdown(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            markdown=payload.markdown,
            wiki_page_id=payload.wiki_page_id,
            apply_front_matter=payload.apply_front_matter,
        )
    except WikiMarkdownError as exc:
        raise WsCommandError("ws_invalid_payload", f"Markdown is not parsed: {exc}", error_code='ws_invalid_payload') from exc
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No permission to edit page", error_code='forbidden') from exc
    return WikiMarkdownImportResponse(page=page, notices=notices)


async def op_pages_content_update(
    payload: WikiPageContentUpdatePayload,
    *,
    user: User,
    di: Di,
) -> WikiPageResponse:
    _ = user
    scope = await _scope(di)
    try:
        content = _resolve_content(payload.content, payload.markdown)
        if content is None:
            raise ValueError("Page content was not provided")
        page = await di.wiki_service.update_page_content(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=payload.wiki_page_id,
            content=content,
            title=payload.title,
            create_revision=payload.create_revision,
        )
    except WikiSchemaError as exc:
        raise_invalid(exc)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No permission to edit page", error_code='forbidden') from exc
    except ValueError as exc:
        raise_invalid(exc)
    return await di.wiki_service.page_response(page, user_id=scope.user_id)


async def op_pages_properties_update(
    payload: WikiPagePropertiesUpdatePayload,
    *,
    user: User,
    di: Di,
) -> WikiPageResponse:
    _ = user
    scope = await _scope(di)
    try:
        page = await di.wiki_service.update_page_properties(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=payload.wiki_page_id,
            title=payload.title,
            icon=payload.icon,
            cover_url=payload.cover_url,
            is_published=payload.is_published,
            is_template=payload.is_template,
            is_full_width=payload.is_full_width,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No permission to edit page", error_code='forbidden') from exc
    return await di.wiki_service.page_response(page, user_id=scope.user_id)


async def op_pages_move(
    payload: WikiPageMovePayload,
    *,
    user: User,
    di: Di,
) -> WikiPageResponse:
    _ = user
    scope = await _scope(di)
    try:
        page = await di.wiki_service.move_page(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=payload.wiki_page_id,
            new_parent_page_id=payload.parent_page_id,
            position=payload.position,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No permission to move", error_code='forbidden') from exc
    except ValueError as exc:
        raise_invalid(exc)
    return await di.wiki_service.page_response(page, user_id=scope.user_id)


async def op_pages_move_namespace(
    payload: WikiPageMoveNamespacePayload,
    *,
    user: User,
    di: Di,
) -> WikiPageResponse:
    _ = user
    scope = await _scope(di)
    target = await di.namespace_service.get(payload.target_namespace)
    if target is None or target.company_id != scope.company_id:
        raise WsCommandError("ws_invalid_payload", "Target workspace is unavailable", error_code='ws_invalid_payload')
    try:
        page = await di.wiki_service.move_page_to_namespace(
            company_id=scope.company_id,
            namespace=scope.namespace,
            target_namespace=target.name,
            user_id=scope.user_id,
            wiki_page_id=payload.wiki_page_id,
            new_parent_page_id=payload.parent_page_id,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No permission to transfer the page", error_code='forbidden') from exc
    except ValueError as exc:
        raise_invalid(exc)
    return await di.wiki_service.page_response(page, user_id=scope.user_id)


async def op_pages_remove(
    payload: WikiPageIdPayload,
    *,
    user: User,
    di: Di,
) -> None:
    _ = user
    scope = await _scope(di)
    try:
        _ = await di.wiki_service.delete_page(
            scope.company_id, scope.namespace, scope.user_id, payload.wiki_page_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No permission to delete", error_code='forbidden') from exc


async def op_pages_restore(
    payload: WikiPageIdPayload,
    *,
    user: User,
    di: Di,
) -> WikiPageResponse:
    _ = user
    scope = await _scope(di)
    try:
        page = await di.wiki_service.restore_page(
            scope.company_id, scope.namespace, scope.user_id, payload.wiki_page_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return await di.wiki_service.page_response(page, user_id=scope.user_id)


async def op_pages_children_list(
    payload: WikiChildrenPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[WikiPageSummary]:
    _ = user
    scope = await _scope(di)
    try:
        _ = await di.wiki_service.require_viewable_page(
            scope.company_id, scope.namespace, payload.wiki_page_id, scope.user_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No access to page", error_code='forbidden') from exc
    tree = await di.wiki_service.list_tree(scope.company_id, scope.namespace, scope.user_id)
    children = [item for item in tree if item.parent_page_id == payload.wiki_page_id]
    if payload.include_self:
        children = [item for item in tree if item.wiki_page_id == payload.wiki_page_id] + children
    return ListResponse[WikiPageSummary](items=children)


async def op_pages_access(
    payload: WikiPageIdPayload,
    *,
    user: User,
    di: Di,
) -> WikiPageAccess:
    _ = user
    scope = await _scope(di)
    try:
        return await di.wiki_service.get_access(
            scope.company_id, scope.namespace, scope.user_id, payload.wiki_page_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No access to page", error_code='forbidden') from exc


async def op_pages_company_visible(
    payload: WikiCompanyVisiblePayload,
    *,
    user: User,
    di: Di,
) -> WikiPageAccess:
    _ = user
    scope = await _scope(di)
    try:
        return await di.wiki_service.set_company_visible(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=payload.wiki_page_id,
            company_visible=payload.company_visible,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No permission to change access", error_code='forbidden') from exc
    except ValueError as exc:
        raise_invalid(exc)


async def op_pages_member_add(
    payload: WikiMemberUpsertPayload,
    *,
    user: User,
    di: Di,
) -> WikiPageAccess:
    _ = user
    scope = await _scope(di)
    try:
        return await di.wiki_service.set_member(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=payload.wiki_page_id,
            member_user_id=payload.user_id,
            relation=payload.relation,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No permission to change access", error_code='forbidden') from exc
    except ValueError as exc:
        raise_invalid(exc)


async def op_pages_member_remove(
    payload: WikiMemberRemovePayload,
    *,
    user: User,
    di: Di,
) -> WikiPageAccess:
    _ = user
    scope = await _scope(di)
    try:
        return await di.wiki_service.remove_member(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=payload.wiki_page_id,
            member_user_id=payload.member_user_id,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No permission to change access", error_code='forbidden') from exc


async def op_pages_public_link(
    payload: WikiPublicLinkPayload,
    *,
    user: User,
    di: Di,
) -> WikiPublicLinkResponse:
    _ = user
    scope = await _scope(di)
    try:
        raw_token = await di.wiki_service.rotate_public_link(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=payload.wiki_page_id,
            enabled=payload.enabled,
            permission=payload.permission,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No permission to publish a link", error_code='forbidden') from exc
    if raw_token is None:
        return WikiPublicLinkResponse(enabled=False, permission=payload.permission, url=None)
    origin = payload.origin.rstrip("/")
    return WikiPublicLinkResponse(
        enabled=True,
        permission=payload.permission,
        url=f"{origin}/wiki/s/{raw_token}",
    )


async def op_pages_revisions_list(
    payload: WikiRevisionsListPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[WikiRevisionSummary]:
    _ = user
    scope = await _scope(di)
    try:
        items = await di.wiki_service.list_revisions(
            scope.company_id,
            scope.namespace,
            scope.user_id,
            payload.wiki_page_id,
            payload.limit,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No access to page", error_code='forbidden') from exc
    return ListResponse[WikiRevisionSummary](items=items)


async def op_revisions_get(
    payload: WikiRevisionIdPayload,
    *,
    user: User,
    di: Di,
) -> WikiRevision:
    _ = user
    scope = await _scope(di)
    try:
        return await di.wiki_service.get_revision(
            scope.company_id, scope.namespace, scope.user_id, payload.wiki_revision_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No access to page", error_code='forbidden') from exc


async def op_revisions_restore(
    payload: WikiRevisionIdPayload,
    *,
    user: User,
    di: Di,
) -> WikiPageResponse:
    _ = user
    scope = await _scope(di)
    try:
        page = await di.wiki_service.restore_revision(
            scope.company_id, scope.namespace, scope.user_id, payload.wiki_revision_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No permission to edit page", error_code='forbidden') from exc
    return await di.wiki_service.page_response(page, user_id=scope.user_id)


async def op_pages_comments_list(
    payload: WikiPageIdPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[WikiComment]:
    _ = user
    scope = await _scope(di)
    try:
        items = await di.wiki_service.list_comments(
            scope.company_id, scope.namespace, scope.user_id, payload.wiki_page_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No access to page", error_code='forbidden') from exc
    return ListResponse[WikiComment](items=items)


async def op_pages_comment_create(
    payload: WikiCommentCreatePayload,
    *,
    user: User,
    di: Di,
) -> WikiComment:
    _ = user
    scope = await _scope(di)
    try:
        return await di.wiki_service.create_comment(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=payload.wiki_page_id,
            body_markdown=payload.body_markdown,
            anchor_text=payload.anchor_text,
            parent_comment_id=payload.parent_comment_id,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except PlatformAccessDeniedError as exc:
        raise WsCommandError("forbidden", "No access to page", error_code='forbidden') from exc


async def op_comments_resolve(
    payload: WikiCommentResolvePayload,
    *,
    user: User,
    di: Di,
) -> WikiComment:
    _ = user
    scope = await _scope(di)
    try:
        return await di.wiki_service.resolve_comment(
            scope.company_id,
            scope.namespace,
            scope.user_id,
            payload.wiki_comment_id,
            payload.resolved,
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)


async def op_comments_remove(
    payload: WikiCommentIdPayload,
    *,
    user: User,
    di: Di,
) -> None:
    _ = user
    scope = await _scope(di)
    try:
        await di.wiki_service.delete_comment(
            scope.company_id, scope.namespace, scope.user_id, payload.wiki_comment_id
        )
    except PlatformNotFoundError as exc:
        raise_not_found(exc)


async def op_search_run(
    payload: WikiSearchRequest,
    *,
    user: User,
    di: Di,
) -> ListResponse[WikiSearchHit]:
    _ = user
    scope = await _scope(di)
    updated_after = (
        datetime.now(timezone.utc) - timedelta(days=payload.updated_after_days)
        if payload.updated_after_days is not None
        else None
    )
    items: list[WikiSearchHit] = []
    seen: set[str] = set()
    if payload.mode in ("auto", "semantic"):
        semantic_hits = await di.wiki_service.semantic_search(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            query=payload.query,
            limit=payload.limit,
            root_page_id=payload.root_page_id,
            published_only=payload.published_only,
            updated_after=updated_after,
            editor_user_id=payload.editor_user_id,
        )
        for hit in semantic_hits:
            seen.add(hit.wiki_page_id)
            items.append(hit)
    if payload.mode in ("auto", "lexical") and len(items) < payload.limit:
        lexical_hits = await di.wiki_service.search_pages(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            query=payload.query,
            limit=payload.limit,
        )
        for hit in lexical_hits:
            if hit.wiki_page_id in seen:
                continue
            items.append(hit)
            if len(items) >= payload.limit:
                break
    return ListResponse[WikiSearchHit](items=items[: payload.limit])


async def op_backlinks_list(
    payload: WikiBacklinksPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[WikiBacklink]:
    _ = user
    company = require_company()
    items = await di.wiki_service.list_backlinks(
        company_id=company.company_id,
        user_id=company.user_id,
        target_kind=payload.target_kind,
        target_id=payload.target_id,
        limit=payload.limit,
    )
    return ListResponse[WikiBacklink](items=items)


def markdown_file_disposition(file_name: str) -> str:
    return f"attachment; filename*=UTF-8''{quote(file_name)}"
