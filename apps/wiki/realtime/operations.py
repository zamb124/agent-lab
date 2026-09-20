"""Бизнес-функции wiki: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from pydantic import Field

from apps.wiki.base_model import WikiBaseModel
from apps.wiki.container import WikiContainer
from apps.wiki.content.markdown_file import markdown_file_name, split_markdown_file
from apps.wiki.content.markdown_parser import (
    WikiMarkdownError,
    markdown_to_document,
    parse_markdown,
)
from apps.wiki.content.prosemirror import ProseMirrorNode
from apps.wiki.content.schema import WikiSchemaError
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
from apps.wiki.models.domain import (
    WikiBacklink,
    WikiComment,
    WikiLinkTargetKind,
    WikiPageAccess,
    WikiPageSummary,
    WikiRevision,
    WikiRevisionSummary,
    WikiSearchHit,
)
from apps.wiki.services.wiki_service import WikiAccessDeniedError, WikiPageNotFoundError
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.pagination import ListResponse
from core.request_scope import NamespaceScope, require_company, require_namespace
from core.websocket import (
    WsCommandError,
    raise_forbidden,
    raise_invalid,
    raise_not_found,
)


class WikiEmptyPayload(StrictBaseModel):
    pass


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





async def _scope(container: WikiContainer) -> NamespaceScope:
    scope = await require_namespace(container.namespace_service)
    try:
        await container.authz_service.require_can_view(
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
        raise ValueError("Укажите либо content, либо markdown, но не оба поля")
    if markdown is None:
        return content
    try:
        return markdown_to_document(markdown)
    except WikiMarkdownError as exc:
        raise ValueError(f"Markdown не разобран: {exc}") from exc


async def op_pages_list(
    payload: WikiEmptyPayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiTreeResponse:
    _ = payload, user
    scope = await _scope(container)
    items = await container.wiki_service.list_tree(
        scope.company_id, scope.namespace, scope.user_id
    )
    return WikiTreeResponse(namespace=scope.namespace, items=items)


async def op_pages_deleted_list(
    payload: WikiEmptyPayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiTreeResponse:
    _ = payload, user
    scope = await _scope(container)
    items = await container.wiki_service.list_deleted(scope.company_id, scope.namespace)
    return WikiTreeResponse(namespace=scope.namespace, items=items)


async def op_pages_create(
    payload: WikiPageCreateRequest,
    *,
    user: User,
    container: WikiContainer,
) -> WikiPageResponse:
    _ = user
    scope = await _scope(container)
    try:
        content = _resolve_content(payload.content, payload.markdown)
        page = await container.wiki_service.create_page(
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
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Родительская страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет прав на создание страницы") from exc
    except ValueError as exc:
        raise_invalid(exc)
    return await container.wiki_service.page_response(page, user_id=scope.user_id)


async def op_pages_get(
    payload: WikiPageIdPayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiPageResponse:
    _ = user
    scope = await _scope(container)
    try:
        page = await container.wiki_service.require_viewable_page(
            scope.company_id, scope.namespace, payload.wiki_page_id, scope.user_id
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет доступа к странице") from exc
    return await container.wiki_service.page_response(page, user_id=scope.user_id)


async def op_pages_markdown(
    payload: WikiPageIdPayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiMarkdownResponse:
    _ = user
    scope = await _scope(container)
    try:
        page = await container.wiki_service.require_viewable_page(
            scope.company_id, scope.namespace, payload.wiki_page_id, scope.user_id
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет доступа к странице") from exc
    return WikiMarkdownResponse(
        wiki_page_id=page.wiki_page_id,
        title=page.title,
        markdown=page.text_markdown,
    )


async def op_pages_markdown_file(
    payload: WikiPageIdPayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiMarkdownFileResult:
    _ = user
    scope = await _scope(container)
    try:
        page = await container.wiki_service.require_viewable_page(
            scope.company_id, scope.namespace, payload.wiki_page_id, scope.user_id
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет доступа к странице") from exc
    return WikiMarkdownFileResult(
        body=container.wiki_service.export_markdown_file(page),
        file_name=markdown_file_name(page.title, page.wiki_page_id),
    )


async def op_pages_markdown_parse(
    payload: WikiMarkdownParseRequest,
    *,
    user: User,
    container: WikiContainer,
) -> WikiMarkdownParseResponse:
    _ = user
    _ = await _scope(container)
    parts = split_markdown_file(payload.markdown)
    try:
        parsed = parse_markdown(parts.body)
    except WikiMarkdownError as exc:
        raise WsCommandError("ws_invalid_payload", f"Markdown не разобран: {exc}") from exc
    return WikiMarkdownParseResponse(
        document=parsed.document, notices=[*parts.notices, *parsed.notices]
    )


async def op_pages_markdown_create(
    payload: WikiMarkdownImportRequest,
    *,
    user: User,
    container: WikiContainer,
) -> WikiMarkdownImportResponse:
    _ = user
    scope = await _scope(container)
    try:
        page, notices = await container.wiki_service.import_markdown(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            markdown=payload.markdown,
            parent_page_id=payload.parent_page_id,
            apply_front_matter=payload.apply_front_matter,
        )
    except WikiMarkdownError as exc:
        raise WsCommandError("ws_invalid_payload", f"Markdown не разобран: {exc}") from exc
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Родительская страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет прав на создание страницы") from exc
    return WikiMarkdownImportResponse(page=page, notices=notices)


async def op_pages_markdown_import(
    payload: WikiMarkdownImportPagePayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiMarkdownImportResponse:
    _ = user
    scope = await _scope(container)
    try:
        page, notices = await container.wiki_service.import_markdown(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            markdown=payload.markdown,
            wiki_page_id=payload.wiki_page_id,
            apply_front_matter=payload.apply_front_matter,
        )
    except WikiMarkdownError as exc:
        raise WsCommandError("ws_invalid_payload", f"Markdown не разобран: {exc}") from exc
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет прав на изменение страницы") from exc
    return WikiMarkdownImportResponse(page=page, notices=notices)


async def op_pages_content_update(
    payload: WikiPageContentUpdatePayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiPageResponse:
    _ = user
    scope = await _scope(container)
    try:
        content = _resolve_content(payload.content, payload.markdown)
        if content is None:
            raise ValueError("Не передано содержимое страницы")
        page = await container.wiki_service.update_page_content(
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
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет прав на изменение страницы") from exc
    except ValueError as exc:
        raise_invalid(exc)
    return await container.wiki_service.page_response(page, user_id=scope.user_id)


async def op_pages_properties_update(
    payload: WikiPagePropertiesUpdatePayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiPageResponse:
    _ = user
    scope = await _scope(container)
    try:
        page = await container.wiki_service.update_page_properties(
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
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет прав на изменение страницы") from exc
    return await container.wiki_service.page_response(page, user_id=scope.user_id)


async def op_pages_move(
    payload: WikiPageMovePayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiPageResponse:
    _ = user
    scope = await _scope(container)
    try:
        page = await container.wiki_service.move_page(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=payload.wiki_page_id,
            new_parent_page_id=payload.parent_page_id,
            position=payload.position,
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет прав на перемещение") from exc
    except ValueError as exc:
        raise_invalid(exc)
    return await container.wiki_service.page_response(page, user_id=scope.user_id)


async def op_pages_move_namespace(
    payload: WikiPageMoveNamespacePayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiPageResponse:
    _ = user
    scope = await _scope(container)
    target = await container.namespace_service.get(payload.target_namespace)
    if target is None or target.company_id != scope.company_id:
        raise WsCommandError("ws_invalid_payload", "Целевое пространство недоступно")
    try:
        page = await container.wiki_service.move_page_to_namespace(
            company_id=scope.company_id,
            namespace=scope.namespace,
            target_namespace=target.name,
            user_id=scope.user_id,
            wiki_page_id=payload.wiki_page_id,
            new_parent_page_id=payload.parent_page_id,
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет прав на перенос страницы") from exc
    except ValueError as exc:
        raise_invalid(exc)
    return await container.wiki_service.page_response(page, user_id=scope.user_id)


async def op_pages_remove(
    payload: WikiPageIdPayload,
    *,
    user: User,
    container: WikiContainer,
) -> None:
    _ = user
    scope = await _scope(container)
    try:
        _ = await container.wiki_service.delete_page(
            scope.company_id, scope.namespace, scope.user_id, payload.wiki_page_id
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет прав на удаление") from exc


async def op_pages_restore(
    payload: WikiPageIdPayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiPageResponse:
    _ = user
    scope = await _scope(container)
    try:
        page = await container.wiki_service.restore_page(
            scope.company_id, scope.namespace, scope.user_id, payload.wiki_page_id
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    return await container.wiki_service.page_response(page, user_id=scope.user_id)


async def op_pages_children_list(
    payload: WikiChildrenPayload,
    *,
    user: User,
    container: WikiContainer,
) -> ListResponse[WikiPageSummary]:
    _ = user
    scope = await _scope(container)
    try:
        _ = await container.wiki_service.require_viewable_page(
            scope.company_id, scope.namespace, payload.wiki_page_id, scope.user_id
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет доступа к странице") from exc
    tree = await container.wiki_service.list_tree(
        scope.company_id, scope.namespace, scope.user_id
    )
    children = [item for item in tree if item.parent_page_id == payload.wiki_page_id]
    if payload.include_self:
        children = [item for item in tree if item.wiki_page_id == payload.wiki_page_id] + children
    return ListResponse[WikiPageSummary](items=children)


async def op_pages_access(
    payload: WikiPageIdPayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiPageAccess:
    _ = user
    scope = await _scope(container)
    try:
        return await container.wiki_service.get_access(
            scope.company_id, scope.namespace, scope.user_id, payload.wiki_page_id
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет доступа к странице") from exc


async def op_pages_company_visible(
    payload: WikiCompanyVisiblePayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiPageAccess:
    _ = user
    scope = await _scope(container)
    try:
        return await container.wiki_service.set_company_visible(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=payload.wiki_page_id,
            company_visible=payload.company_visible,
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет прав на изменение доступа") from exc
    except ValueError as exc:
        raise_invalid(exc)


async def op_pages_member_add(
    payload: WikiMemberUpsertPayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiPageAccess:
    _ = user
    scope = await _scope(container)
    try:
        return await container.wiki_service.set_member(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=payload.wiki_page_id,
            member_user_id=payload.user_id,
            relation=payload.relation,
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет прав на изменение доступа") from exc
    except ValueError as exc:
        raise_invalid(exc)


async def op_pages_member_remove(
    payload: WikiMemberRemovePayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiPageAccess:
    _ = user
    scope = await _scope(container)
    try:
        return await container.wiki_service.remove_member(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=payload.wiki_page_id,
            member_user_id=payload.member_user_id,
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет прав на изменение доступа") from exc


async def op_pages_public_link(
    payload: WikiPublicLinkPayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiPublicLinkResponse:
    _ = user
    scope = await _scope(container)
    try:
        raw_token = await container.wiki_service.rotate_public_link(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=payload.wiki_page_id,
            enabled=payload.enabled,
            permission=payload.permission,
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет прав на публикацию ссылки") from exc
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
    container: WikiContainer,
) -> ListResponse[WikiRevisionSummary]:
    _ = user
    scope = await _scope(container)
    try:
        items = await container.wiki_service.list_revisions(
            scope.company_id,
            scope.namespace,
            scope.user_id,
            payload.wiki_page_id,
            payload.limit,
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет доступа к странице") from exc
    return ListResponse[WikiRevisionSummary](items=items)


async def op_revisions_get(
    payload: WikiRevisionIdPayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiRevision:
    _ = user
    scope = await _scope(container)
    try:
        return await container.wiki_service.get_revision(
            scope.company_id, scope.namespace, scope.user_id, payload.wiki_revision_id
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Ревизия не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет доступа к странице") from exc


async def op_revisions_restore(
    payload: WikiRevisionIdPayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiPageResponse:
    _ = user
    scope = await _scope(container)
    try:
        page = await container.wiki_service.restore_revision(
            scope.company_id, scope.namespace, scope.user_id, payload.wiki_revision_id
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Ревизия не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет прав на изменение страницы") from exc
    return await container.wiki_service.page_response(page, user_id=scope.user_id)


async def op_pages_comments_list(
    payload: WikiPageIdPayload,
    *,
    user: User,
    container: WikiContainer,
) -> ListResponse[WikiComment]:
    _ = user
    scope = await _scope(container)
    try:
        items = await container.wiki_service.list_comments(
            scope.company_id, scope.namespace, scope.user_id, payload.wiki_page_id
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет доступа к странице") from exc
    return ListResponse[WikiComment](items=items)


async def op_pages_comment_create(
    payload: WikiCommentCreatePayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiComment:
    _ = user
    scope = await _scope(container)
    try:
        return await container.wiki_service.create_comment(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=payload.wiki_page_id,
            body_markdown=payload.body_markdown,
            anchor_text=payload.anchor_text,
            parent_comment_id=payload.parent_comment_id,
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Страница не найдена")
    except WikiAccessDeniedError as exc:
        raise WsCommandError("forbidden", "Нет доступа к странице") from exc


async def op_comments_resolve(
    payload: WikiCommentResolvePayload,
    *,
    user: User,
    container: WikiContainer,
) -> WikiComment:
    _ = user
    scope = await _scope(container)
    try:
        return await container.wiki_service.resolve_comment(
            scope.company_id,
            scope.namespace,
            scope.user_id,
            payload.wiki_comment_id,
            payload.resolved,
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Комментарий не найден")


async def op_comments_remove(
    payload: WikiCommentIdPayload,
    *,
    user: User,
    container: WikiContainer,
) -> None:
    _ = user
    scope = await _scope(container)
    try:
        await container.wiki_service.delete_comment(
            scope.company_id, scope.namespace, scope.user_id, payload.wiki_comment_id
        )
    except WikiPageNotFoundError as exc:
        raise_not_found(exc, "Комментарий не найден")


async def op_search_run(
    payload: WikiSearchRequest,
    *,
    user: User,
    container: WikiContainer,
) -> ListResponse[WikiSearchHit]:
    _ = user
    scope = await _scope(container)
    updated_after = (
        datetime.now(timezone.utc) - timedelta(days=payload.updated_after_days)
        if payload.updated_after_days is not None
        else None
    )
    items: list[WikiSearchHit] = []
    seen: set[str] = set()
    if payload.mode in ("auto", "semantic"):
        semantic_hits = await container.wiki_service.semantic_search(
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
        lexical_hits = await container.wiki_service.search_pages(
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
    container: WikiContainer,
) -> ListResponse[WikiBacklink]:
    _ = user
    company = require_company()
    items = await container.wiki_service.list_backlinks(
        company_id=company.company_id,
        user_id=company.user_id,
        target_kind=payload.target_kind,
        target_id=payload.target_id,
        limit=payload.limit,
    )
    return ListResponse[WikiBacklink](items=items)


def markdown_file_disposition(file_name: str) -> str:
    return f"attachment; filename*=UTF-8''{quote(file_name)}"
