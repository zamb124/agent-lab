"""Страницы wiki: тонкая REST-обвязка тех же `op_*`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from apps.wiki.di import Di
from apps.wiki.models.api import (
    WikiMarkdownImportRequest,
    WikiMarkdownImportResponse,
    WikiMarkdownParseRequest,
    WikiMarkdownParseResponse,
    WikiMarkdownResponse,
    WikiPageContentUpdateRequest,
    WikiPageCreateRequest,
    WikiPageMoveNamespaceRequest,
    WikiPageMoveRequest,
    WikiPagePropertiesUpdateRequest,
    WikiPageResponse,
    WikiTreeResponse,
)
from apps.wiki.models.domain import WikiPageSummary
from apps.wiki.realtime.operations import (
    WikiChildrenPayload,
    WikiMarkdownImportPagePayload,
    WikiPageContentUpdatePayload,
    WikiPageIdPayload,
    WikiPageMoveNamespacePayload,
    WikiPageMovePayload,
    WikiPagePropertiesUpdatePayload,
    markdown_file_disposition,
    op_pages_children_list,
    op_pages_content_update,
    op_pages_create,
    op_pages_deleted_list,
    op_pages_get,
    op_pages_list,
    op_pages_markdown,
    op_pages_markdown_create,
    op_pages_markdown_file,
    op_pages_markdown_import,
    op_pages_markdown_parse,
    op_pages_move,
    op_pages_move_namespace,
    op_pages_properties_update,
    op_pages_remove,
    op_pages_restore,
)
from core.context import require_context
from core.pagination import ListResponse
from core.websocket import EmptyPayload

router = APIRouter(prefix="/pages", tags=["wiki-pages"])


@router.get("", response_model=WikiTreeResponse)
async def list_tree(di: Di) -> WikiTreeResponse:
    return await op_pages_list(
        EmptyPayload(), user=require_context().user, di=di
    )


@router.get("/deleted", response_model=WikiTreeResponse)
async def list_deleted(di: Di) -> WikiTreeResponse:
    return await op_pages_deleted_list(
        EmptyPayload(), user=require_context().user, di=di
    )


@router.post("", response_model=WikiPageResponse, status_code=201)
async def create_page(
    di: Di, request: WikiPageCreateRequest
) -> WikiPageResponse:
    return await op_pages_create(request, user=require_context().user, di=di)


@router.get("/{wiki_page_id}", response_model=WikiPageResponse)
async def get_page(di: Di, wiki_page_id: str) -> WikiPageResponse:
    return await op_pages_get(
        WikiPageIdPayload(wiki_page_id=wiki_page_id),
        user=require_context().user,
        di=di,
    )


@router.get("/{wiki_page_id}/markdown", response_model=WikiMarkdownResponse)
async def get_page_markdown(
    di: Di, wiki_page_id: str
) -> WikiMarkdownResponse:
    return await op_pages_markdown(
        WikiPageIdPayload(wiki_page_id=wiki_page_id),
        user=require_context().user,
        di=di,
    )


@router.get("/{wiki_page_id}/markdown/file", response_class=PlainTextResponse)
async def download_page_markdown(di: Di, wiki_page_id: str) -> PlainTextResponse:
    result = await op_pages_markdown_file(
        WikiPageIdPayload(wiki_page_id=wiki_page_id),
        user=require_context().user,
        di=di,
    )
    return PlainTextResponse(
        content=result.body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": markdown_file_disposition(result.file_name)},
    )


@router.post("/markdown/parse", response_model=WikiMarkdownParseResponse)
async def parse_markdown_fragment(
    di: Di, request: WikiMarkdownParseRequest
) -> WikiMarkdownParseResponse:
    return await op_pages_markdown_parse(
        request, user=require_context().user, di=di
    )


@router.post("/import/markdown", response_model=WikiMarkdownImportResponse, status_code=201)
async def import_markdown_as_page(
    di: Di, request: WikiMarkdownImportRequest
) -> WikiMarkdownImportResponse:
    return await op_pages_markdown_create(
        request, user=require_context().user, di=di
    )


@router.post("/{wiki_page_id}/import/markdown", response_model=WikiMarkdownImportResponse)
async def import_markdown_into_page(
    di: Di, wiki_page_id: str, request: WikiMarkdownImportRequest
) -> WikiMarkdownImportResponse:
    return await op_pages_markdown_import(
        WikiMarkdownImportPagePayload(
            wiki_page_id=wiki_page_id,
            markdown=request.markdown,
            parent_page_id=request.parent_page_id,
            apply_front_matter=request.apply_front_matter,
        ),
        user=require_context().user,
        di=di,
    )


@router.put("/{wiki_page_id}/content", response_model=WikiPageResponse)
async def update_content(
    di: Di, wiki_page_id: str, request: WikiPageContentUpdateRequest
) -> WikiPageResponse:
    return await op_pages_content_update(
        WikiPageContentUpdatePayload(
            wiki_page_id=wiki_page_id,
            content=request.content,
            markdown=request.markdown,
            title=request.title,
            create_revision=request.create_revision,
        ),
        user=require_context().user,
        di=di,
    )


@router.patch("/{wiki_page_id}", response_model=WikiPageResponse)
async def update_properties(
    di: Di, wiki_page_id: str, request: WikiPagePropertiesUpdateRequest
) -> WikiPageResponse:
    return await op_pages_properties_update(
        WikiPagePropertiesUpdatePayload(
            wiki_page_id=wiki_page_id,
            title=request.title,
            icon=request.icon,
            cover_url=request.cover_url,
            is_published=request.is_published,
            is_template=request.is_template,
            is_full_width=request.is_full_width,
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/{wiki_page_id}/move", response_model=WikiPageResponse)
async def move_page(
    di: Di, wiki_page_id: str, request: WikiPageMoveRequest
) -> WikiPageResponse:
    return await op_pages_move(
        WikiPageMovePayload(
            wiki_page_id=wiki_page_id,
            parent_page_id=request.parent_page_id,
            position=request.position,
        ),
        user=require_context().user,
        di=di,
    )


@router.post("/{wiki_page_id}/move-namespace", response_model=WikiPageResponse)
async def move_page_to_namespace(
    di: Di, wiki_page_id: str, request: WikiPageMoveNamespaceRequest
) -> WikiPageResponse:
    return await op_pages_move_namespace(
        WikiPageMoveNamespacePayload(
            wiki_page_id=wiki_page_id,
            target_namespace=request.target_namespace,
            parent_page_id=request.parent_page_id,
        ),
        user=require_context().user,
        di=di,
    )


@router.delete("/{wiki_page_id}", status_code=204)
async def delete_page(di: Di, wiki_page_id: str) -> None:
    await op_pages_remove(
        WikiPageIdPayload(wiki_page_id=wiki_page_id),
        user=require_context().user,
        di=di,
    )


@router.post("/{wiki_page_id}/restore", response_model=WikiPageResponse)
async def restore_page(di: Di, wiki_page_id: str) -> WikiPageResponse:
    return await op_pages_restore(
        WikiPageIdPayload(wiki_page_id=wiki_page_id),
        user=require_context().user,
        di=di,
    )


@router.get("/{wiki_page_id}/children", response_model=ListResponse[WikiPageSummary])
async def list_children(
    di: Di,
    wiki_page_id: str,
    include_self: Annotated[bool, Query()] = False,
) -> ListResponse[WikiPageSummary]:
    return await op_pages_children_list(
        WikiChildrenPayload(wiki_page_id=wiki_page_id, include_self=include_self),
        user=require_context().user,
        di=di,
    )
