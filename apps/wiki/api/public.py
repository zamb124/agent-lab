"""
Публичный сайт: анонимный доступ по ссылке.

Единственная часть API без namespace в запросе: посетитель по ссылке его не
знает. Пространство берётся из страницы, найденной по хешу токена, и дальше
используется как граница для всего остального.

Токен живёт на корне сайта, а сам сайт — опубликованное поддерево этого корня:
подстраницы открываются по той же ссылке, а снятая с публикации страница
скрывает и всех своих потомков. `WikiLinkPermission` — `viewer` или `editor`;
"""

from __future__ import annotations

from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from apps.wiki.content.public_media import rewrite_cover_for_public, rewrite_media_for_public
from apps.wiki.dependencies import ContainerDep
from apps.wiki.models.api import (
    WikiMarkdownResponse,
    WikiPublicPageResponse,
    WikiPublicPageSummary,
    WikiPublicTreeResponse,
)
from apps.wiki.models.domain import WikiPage
from core.files.http_range import RangeNotSatisfiableError
from core.files.s3_client import S3ClientFactory
from core.files.streaming import stream_s3_file
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/public", tags=["wiki-public"])


def _public_page_response(page: WikiPage, link_token: str) -> WikiPublicPageResponse:
    return WikiPublicPageResponse(
        wiki_page_id=page.wiki_page_id,
        parent_page_id=page.parent_page_id,
        title=page.title,
        icon=page.icon,
        cover_url=rewrite_cover_for_public(page.cover_url, link_token),
        is_full_width=page.is_full_width,
        content=rewrite_media_for_public(page.content, link_token),
        updated_at=page.updated_at,
    )


@router.get("/pages/{link_token}", response_model=WikiPublicPageResponse)
async def get_public_page(container: ContainerDep, link_token: str) -> WikiPublicPageResponse:
    page = await container.wiki_service.get_public_page(link_token)
    if page is None:
        raise HTTPException(status_code=404, detail="Страница не найдена")
    return _public_page_response(page, link_token)


@router.get("/pages/{link_token}/markdown", response_model=WikiMarkdownResponse)
async def get_public_page_markdown(
    container: ContainerDep, link_token: str
) -> WikiMarkdownResponse:
    page = await container.wiki_service.get_public_page(link_token)
    if page is None:
        raise HTTPException(status_code=404, detail="Страница не найдена")
    return WikiMarkdownResponse(
        wiki_page_id=page.wiki_page_id,
        title=page.title,
        markdown=page.text_markdown,
    )


@router.get("/pages/{link_token}/tree", response_model=WikiPublicTreeResponse)
async def get_public_site_tree(container: ContainerDep, link_token: str) -> WikiPublicTreeResponse:
    items = await container.wiki_service.get_public_site_tree(link_token)
    if not items:
        raise HTTPException(status_code=404, detail="Страница не найдена")
    return WikiPublicTreeResponse(
        root_page_id=items[0].wiki_page_id,
        items=[
            WikiPublicPageSummary(
                wiki_page_id=item.wiki_page_id,
                parent_page_id=item.parent_page_id,
                title=item.title,
                icon=item.icon,
                has_children=item.has_children,
            )
            for item in items
        ],
    )


@router.get("/pages/{link_token}/pages/{wiki_page_id}", response_model=WikiPublicPageResponse)
async def get_public_site_page(
    container: ContainerDep, link_token: str, wiki_page_id: str
) -> WikiPublicPageResponse:
    page = await container.wiki_service.get_public_site_page(link_token, wiki_page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Страница не найдена")
    return _public_page_response(page, link_token)


@router.get(
    "/pages/{link_token}/pages/{wiki_page_id}/markdown", response_model=WikiMarkdownResponse
)
async def get_public_site_page_markdown(
    container: ContainerDep, link_token: str, wiki_page_id: str
) -> WikiMarkdownResponse:
    page = await container.wiki_service.get_public_site_page(link_token, wiki_page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Страница не найдена")
    return WikiMarkdownResponse(
        wiki_page_id=page.wiki_page_id,
        title=page.title,
        markdown=page.text_markdown,
    )


@router.get("/pages/{link_token}/files/{file_id}", response_model=None)
async def get_public_site_file(
    container: ContainerDep, link_token: str, file_id: str, request: Request
) -> StreamingResponse | Response:
    """Файл публичного сайта.

    Права проверяет содержимое: файл отдаётся только если он встречается на
    опубликованной странице этого сайта. Отдаём лишь то, что лежит в S3 —
    внешние хранилища через публичную ссылку не проксируем.
    """
    if not await container.wiki_service.public_site_has_file(link_token, file_id):
        raise HTTPException(status_code=404, detail="Файл не найден")

    try:
        file_record = await container.files_service.get(file_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Файл не найден") from exc

    if file_record.s3_bucket == "" or file_record.s3_key == "":
        raise HTTPException(status_code=404, detail="Файл не найден")
    if file_record.content_type == "":
        raise HTTPException(status_code=500, detail="У файла не задан content_type")

    s3_client = S3ClientFactory.create_client_for_bucket(file_record.s3_bucket)
    range_raw = request.headers.get("range")
    try:
        return await stream_s3_file(
            s3_client=s3_client,
            s3_key=file_record.s3_key,
            content_type=file_record.content_type,
            bucket=None,
            range_header=range_raw.strip() if isinstance(range_raw, str) else None,
        )
    except RangeNotSatisfiableError as exc:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{exc.total_size}"})
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        status = exc.response["ResponseMetadata"]["HTTPStatusCode"]
        if code in ("404", "NoSuchKey", "NotFound") or status == 404:
            raise HTTPException(status_code=404, detail="Файл не найден") from exc
        logger.exception("wiki.public_file_download_failed", file_id=file_id)
        raise HTTPException(status_code=502, detail="Не удалось прочитать файл") from exc
