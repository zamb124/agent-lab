"""Комментарии к страницам."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from apps.wiki.api._scope import require_scope
from apps.wiki.dependencies import ContainerDep
from apps.wiki.models.api import (
    WikiCommentCreateRequest,
    WikiCommentListResponse,
    WikiCommentResolveRequest,
)
from apps.wiki.models.domain import WikiComment
from apps.wiki.services.wiki_service import WikiAccessDeniedError, WikiPageNotFoundError

router = APIRouter(tags=["wiki-comments"])


@router.get("/pages/{wiki_page_id}/comments", response_model=WikiCommentListResponse)
async def list_comments(
    container: ContainerDep, wiki_page_id: str
) -> WikiCommentListResponse:
    scope = await require_scope(container)
    try:
        items = await container.wiki_service.list_comments(
            scope.company_id, scope.namespace, scope.user_id, wiki_page_id
        )
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Страница не найдена") from exc
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Нет доступа к странице") from exc
    return WikiCommentListResponse(items=items)


@router.post("/pages/{wiki_page_id}/comments", response_model=WikiComment, status_code=201)
async def create_comment(
    container: ContainerDep, wiki_page_id: str, request: WikiCommentCreateRequest
) -> WikiComment:
    scope = await require_scope(container)
    try:
        return await container.wiki_service.create_comment(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=wiki_page_id,
            body_markdown=request.body_markdown,
            anchor_text=request.anchor_text,
            parent_comment_id=request.parent_comment_id,
        )
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Страница не найдена") from exc
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Нет доступа к странице") from exc


@router.post("/comments/{wiki_comment_id}/resolve", response_model=WikiComment)
async def resolve_comment(
    container: ContainerDep, wiki_comment_id: str, request: WikiCommentResolveRequest
) -> WikiComment:
    scope = await require_scope(container)
    try:
        return await container.wiki_service.resolve_comment(
            scope.company_id, scope.namespace, scope.user_id, wiki_comment_id, request.resolved
        )
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Комментарий не найден") from exc


@router.delete("/comments/{wiki_comment_id}", status_code=204)
async def delete_comment(container: ContainerDep, wiki_comment_id: str) -> None:
    scope = await require_scope(container)
    await container.wiki_service.delete_comment(
        scope.company_id, scope.namespace, scope.user_id, wiki_comment_id
    )
