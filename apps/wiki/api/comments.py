"""Комментарии к страницам: тонкая REST-обвязка тех же `op_*`."""

from __future__ import annotations

from fastapi import APIRouter

from apps.wiki.di import Di
from apps.wiki.models.api import (
    WikiCommentCreateRequest,
    WikiCommentResolveRequest,
)
from apps.wiki.models.domain import WikiComment
from apps.wiki.realtime.operations import (
    WikiCommentCreatePayload,
    WikiCommentIdPayload,
    WikiCommentResolvePayload,
    WikiPageIdPayload,
    op_comments_remove,
    op_comments_resolve,
    op_pages_comment_create,
    op_pages_comments_list,
)
from core.context import require_context
from core.pagination import ListResponse

router = APIRouter(tags=["wiki-comments"])


@router.get("/pages/{wiki_page_id}/comments", response_model=ListResponse[WikiComment])
async def list_comments(
    di: Di, wiki_page_id: str
) -> ListResponse[WikiComment]:
    return await op_pages_comments_list(
        WikiPageIdPayload(wiki_page_id=wiki_page_id),
        user=require_context().user,
        di=di,
    )


@router.post("/pages/{wiki_page_id}/comments", response_model=WikiComment, status_code=201)
async def create_comment(
    di: Di, wiki_page_id: str, request: WikiCommentCreateRequest
) -> WikiComment:
    return await op_pages_comment_create(
        WikiCommentCreatePayload(
            wiki_page_id=wiki_page_id,
            body_markdown=request.body_markdown,
            anchor_text=request.anchor_text,
            parent_comment_id=request.parent_comment_id,
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/comments/{wiki_comment_id}/resolve", response_model=WikiComment)
async def resolve_comment(
    di: Di, wiki_comment_id: str, request: WikiCommentResolveRequest
) -> WikiComment:
    return await op_comments_resolve(
        WikiCommentResolvePayload(
            wiki_comment_id=wiki_comment_id, resolved=request.resolved
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/comments/{wiki_comment_id}", status_code=204)
async def delete_comment(di: Di, wiki_comment_id: str) -> None:
    await op_comments_remove(
        WikiCommentIdPayload(wiki_comment_id=wiki_comment_id),
        user=require_context().user,
        di=di,
    )
