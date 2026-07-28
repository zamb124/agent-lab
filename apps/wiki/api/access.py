"""
Доступ к странице: участники и публичная ссылка.

Любое изменение здесь пересчитывает видимость поддерева и переносит индекс
RAG — это делает сервис, роутер лишь передаёт намерение.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from apps.wiki.api._scope import require_scope
from apps.wiki.dependencies import ContainerDep
from apps.wiki.models.api import (
    WikiAccessResponse,
    WikiMemberUpsertRequest,
    WikiPublicLinkRequest,
    WikiPublicLinkResponse,
)
from apps.wiki.models.domain import WikiPageAccess
from apps.wiki.services.wiki_service import WikiAccessDeniedError, WikiPageNotFoundError
from core.middleware.auth.company_resolver import build_service_base_url

router = APIRouter(prefix="/pages", tags=["wiki-access"])


def _to_response(access: WikiPageAccess) -> WikiAccessResponse:
    return WikiAccessResponse(
        wiki_page_id=access.wiki_page_id,
        visibility=access.visibility,
        inherited_from_page_id=access.inherited_from_page_id,
        members=access.members,
        link_enabled=access.link_enabled,
        link_permission=access.link_permission,
    )


@router.get("/{wiki_page_id}/access", response_model=WikiAccessResponse)
async def get_access(container: ContainerDep, wiki_page_id: str) -> WikiAccessResponse:
    scope = await require_scope(container)
    try:
        access = await container.wiki_service.get_access(
            scope.company_id, scope.namespace, scope.user_id, wiki_page_id
        )
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Страница не найдена") from exc
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Нет доступа к странице") from exc
    return _to_response(access)


@router.post("/{wiki_page_id}/access/members", response_model=WikiAccessResponse)
async def upsert_member(
    container: ContainerDep, wiki_page_id: str, request: WikiMemberUpsertRequest
) -> WikiAccessResponse:
    """Добавить участника.

    Первый участник переводит страницу и её поддерево в ограниченный режим:
    контент уезжает из общего knowledge-namespace в служебный.
    """
    scope = await require_scope(container)
    try:
        access = await container.wiki_service.set_member(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=wiki_page_id,
            member_user_id=request.user_id,
            permission=request.permission,
        )
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Страница не найдена") from exc
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Нет прав на изменение доступа") from exc
    return _to_response(access)


@router.delete("/{wiki_page_id}/access/members/{member_user_id}", response_model=WikiAccessResponse)
async def remove_member(
    container: ContainerDep, wiki_page_id: str, member_user_id: str
) -> WikiAccessResponse:
    scope = await require_scope(container)
    try:
        access = await container.wiki_service.remove_member(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=wiki_page_id,
            member_user_id=member_user_id,
        )
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Страница не найдена") from exc
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Нет прав на изменение доступа") from exc
    return _to_response(access)


@router.post("/{wiki_page_id}/access/link", response_model=WikiPublicLinkResponse)
async def rotate_public_link(
    container: ContainerDep,
    wiki_page_id: str,
    http_request: Request,
    body: WikiPublicLinkRequest,
) -> WikiPublicLinkResponse:
    """Включить, перевыпустить или отключить публичную ссылку."""
    scope = await require_scope(container)
    try:
        raw_token = await container.wiki_service.rotate_public_link(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            wiki_page_id=wiki_page_id,
            enabled=body.enabled,
            permission=body.permission,
        )
    except WikiPageNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Страница не найдена") from exc
    except WikiAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Нет прав на публикацию ссылки") from exc

    if raw_token is None:
        return WikiPublicLinkResponse(enabled=False, permission=body.permission, url=None)

    # Публичный origin из запроса (Host / X-Forwarded-*), не из internal service URL.
    origin = build_service_base_url(http_request).rstrip("/")
    return WikiPublicLinkResponse(
        enabled=True,
        permission=body.permission,
        url=f"{origin}/wiki/s/{raw_token}",
    )
