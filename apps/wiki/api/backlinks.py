"""
Обратные ссылки на сущности платформы.

Этот эндпоинт вызывает общий компонент `platform-wiki-backlinks` из карточки
сущности Networkle, панели Documents и деталей задачи, поэтому namespace тут
не задаётся: связи собираются по всем пространствам компании, а невидимые
пользователю страницы отсеиваются по правам.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.wiki.dependencies import ContainerDep
from apps.wiki.models.api import WikiBacklinkItem, WikiBacklinksResponse
from apps.wiki.models.domain import WikiLinkTargetKind
from core.context import get_context

router = APIRouter(prefix="/backlinks", tags=["wiki-backlinks"])


@router.get("", response_model=WikiBacklinksResponse)
async def list_backlinks(
    container: ContainerDep,
    target_kind: Annotated[WikiLinkTargetKind, Query()],
    target_id: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> WikiBacklinksResponse:
    context = get_context()
    if context is None or context.active_company is None:
        raise HTTPException(status_code=403, detail="Компания не выбрана")

    items = await container.wiki_service.list_backlinks(
        company_id=context.active_company.company_id,
        user_id=context.user.user_id,
        target_kind=target_kind,
        target_id=target_id,
        limit=limit,
    )
    return WikiBacklinksResponse(
        items=[
            WikiBacklinkItem(
                wiki_page_id=item.wiki_page_id,
                namespace=item.namespace,
                title=item.title,
                icon=item.icon,
                url=f"/wiki/p/{item.wiki_page_id}",
                updated_at=item.updated_at,
            )
            for item in items
        ]
    )
