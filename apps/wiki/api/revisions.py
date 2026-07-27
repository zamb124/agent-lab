"""История версий страницы."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.wiki.api._scope import require_scope
from apps.wiki.dependencies import ContainerDep
from apps.wiki.models.api import WikiPageResponse
from apps.wiki.models.domain import WikiRevision, WikiRevisionSummary
from apps.wiki.services.wiki_service import WikiAccessDeniedError, WikiPageNotFoundError

router = APIRouter(tags=["wiki-revisions"])


@router.get("/pages/{wiki_page_id}/revisions", response_model=list[WikiRevisionSummary])
async def list_revisions(
    container: ContainerDep,
    wiki_page_id: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[WikiRevisionSummary]:
    scope = await require_scope(container)
    try:
        return await container.wiki_service.list_revisions(
            scope.company_id, scope.namespace, scope.user_id, wiki_page_id, limit
        )
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Страница не найдена") from exc
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Нет доступа к странице") from exc


@router.get("/revisions/{wiki_revision_id}", response_model=WikiRevision)
async def get_revision(container: ContainerDep, wiki_revision_id: str) -> WikiRevision:
    scope = await require_scope(container)
    try:
        return await container.wiki_service.get_revision(
            scope.company_id, scope.namespace, scope.user_id, wiki_revision_id
        )
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Ревизия не найдена") from exc
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Нет доступа к странице") from exc


@router.post("/revisions/{wiki_revision_id}/restore", response_model=WikiPageResponse)
async def restore_revision(
    container: ContainerDep, wiki_revision_id: str
) -> WikiPageResponse:
    """Вернуть страницу к состоянию ревизии.

    Текущее содержимое при этом само уходит в новую ревизию, поэтому откат
    обратим.
    """
    scope = await require_scope(container)
    try:
        page = await container.wiki_service.restore_revision(
            scope.company_id, scope.namespace, scope.user_id, wiki_revision_id
        )
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Ревизия не найдена") from exc
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Нет прав на изменение страницы") from exc
    return WikiPageResponse(page=page, can_edit=True, can_administer=False)
