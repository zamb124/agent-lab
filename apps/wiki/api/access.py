"""Доступ к странице: тонкая REST-обвязка тех же `op_*`."""

from __future__ import annotations

from fastapi import APIRouter, Request

from apps.wiki.di import Di
from apps.wiki.models.api import (
    WikiCompanyVisibleRequest,
    WikiMemberUpsertRequest,
    WikiPublicLinkRequest,
    WikiPublicLinkResponse,
)
from apps.wiki.models.domain import WikiPageAccess
from apps.wiki.realtime.operations import (
    WikiCompanyVisiblePayload,
    WikiMemberRemovePayload,
    WikiMemberUpsertPayload,
    WikiPageIdPayload,
    WikiPublicLinkPayload,
    op_pages_access,
    op_pages_company_visible,
    op_pages_member_add,
    op_pages_member_remove,
    op_pages_public_link,
)
from core.context import require_context
from core.middleware.auth.company_resolver import build_service_base_url

router = APIRouter(prefix="/pages", tags=["wiki-access"])


@router.get("/{wiki_page_id}/access", response_model=WikiPageAccess)
async def get_access(di: Di, wiki_page_id: str) -> WikiPageAccess:
    return await op_pages_access(
        WikiPageIdPayload(wiki_page_id=wiki_page_id),
        user=require_context().user,
        di=di,
    )


@router.patch("/{wiki_page_id}/access/company-visible", response_model=WikiPageAccess)
async def patch_company_visible(
    di: Di,
    wiki_page_id: str,
    body: WikiCompanyVisibleRequest,
) -> WikiPageAccess:
    return await op_pages_company_visible(
        WikiCompanyVisiblePayload(
            wiki_page_id=wiki_page_id, company_visible=body.company_visible
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/{wiki_page_id}/access/members", response_model=WikiPageAccess)
async def upsert_member(
    di: Di, wiki_page_id: str, request: WikiMemberUpsertRequest
) -> WikiPageAccess:
    return await op_pages_member_add(
        WikiMemberUpsertPayload(
            wiki_page_id=wiki_page_id,
            user_id=request.user_id,
            relation=request.relation,
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/{wiki_page_id}/access/members/{member_user_id}", response_model=WikiPageAccess)
async def remove_member(
    di: Di, wiki_page_id: str, member_user_id: str
) -> WikiPageAccess:
    return await op_pages_member_remove(
        WikiMemberRemovePayload(wiki_page_id=wiki_page_id, member_user_id=member_user_id),
        user=require_context().user,
        di=di,
    )


@router.post("/{wiki_page_id}/access/link", response_model=WikiPublicLinkResponse)
async def rotate_public_link(
    di: Di,
    wiki_page_id: str,
    http_request: Request,
    body: WikiPublicLinkRequest,
) -> WikiPublicLinkResponse:
    origin = build_service_base_url(http_request).rstrip("/")
    return await op_pages_public_link(
        WikiPublicLinkPayload(
            wiki_page_id=wiki_page_id,
            enabled=body.enabled,
            permission=body.permission,
            origin=origin,
        ),
        user=require_context().user,
        di=di,
    )
