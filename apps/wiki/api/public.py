"""
Анонимный доступ по публичной ссылке.

Единственная часть API без namespace в запросе: посетитель по ссылке его не
знает. Пространство берётся из самой страницы, найденной по хешу токена, и
дальше используется как граница для всего остального.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from apps.wiki.dependencies import ContainerDep
from apps.wiki.models.api import WikiMarkdownResponse, WikiPublicPageResponse

router = APIRouter(prefix="/public", tags=["wiki-public"])


@router.get("/pages/{link_token}", response_model=WikiPublicPageResponse)
async def get_public_page(
    container: ContainerDep, link_token: str
) -> WikiPublicPageResponse:
    page = await container.wiki_service.get_page_by_link_token(link_token)
    if page is None:
        raise HTTPException(status_code=404, detail="Страница не найдена")
    return WikiPublicPageResponse(
        wiki_page_id=page.wiki_page_id,
        title=page.title,
        icon=page.icon,
        content=page.content,
        updated_at=page.updated_at,
    )


@router.get("/pages/{link_token}/markdown", response_model=WikiMarkdownResponse)
async def get_public_page_markdown(
    container: ContainerDep, link_token: str
) -> WikiMarkdownResponse:
    page = await container.wiki_service.get_page_by_link_token(link_token)
    if page is None:
        raise HTTPException(status_code=404, detail="Страница не найдена")
    return WikiMarkdownResponse(
        wiki_page_id=page.wiki_page_id,
        title=page.title,
        markdown=page.text_markdown,
    )
