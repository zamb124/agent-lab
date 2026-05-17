"""API для namespace в Sync.

Sync space = platform namespace 1:1. Создание/удаление namespace — задача
CRM (`apps/crm/api/namespaces.py`); Sync только читает список и пишет свою
секцию настроек `Namespace.sync_settings` через PUT. Всё остальное (имя,
описание, `crm_settings`) принадлежит CRM.
"""

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from apps.sync.dependencies import ContainerDep
from apps.sync.realtime.context import require_current_user
from core.logging import get_logger
from core.models.identity_models import NamespaceSyncSettings
from core.pagination import OffsetPage

logger = get_logger(__name__)

router = APIRouter()


class SyncNamespaceResponse(BaseModel):
    """Namespace в формате для UI Sync (срез нужных полей)."""

    name: str = Field(description="Slug namespace.")
    company_id: str = Field(description="ID компании-владельца.")
    description: str | None = Field(default=None, description="Описание namespace.")
    is_default: bool = Field(default=False, description="Дефолтный namespace компании.")
    sync_settings: NamespaceSyncSettings | None = Field(
        default=None,
        description="Sync-настройки namespace (транскрипция голосовых, речь в ленту).",
    )


class SyncNamespaceUpdateRequest(BaseModel):
    """Обновление sync-настроек namespace.

    `sync_settings: null` сбрасывает настройки к дефолту (фабричное
    выключенное состояние). Имя/описание/crm_settings меняются через CRM.
    """

    sync_settings: NamespaceSyncSettings | None = Field(
        default=None,
        description="Полная новая секция sync-настроек либо null для сброса.",
    )


@router.get("", response_model=OffsetPage[SyncNamespaceResponse])
async def list_namespaces(
    container: ContainerDep,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> OffsetPage[SyncNamespaceResponse]:
    """Список namespace текущей компании (источник — shared `NamespaceRepository`)."""
    namespace_repo = container.namespace_repository
    namespaces, total = await asyncio.gather(
        namespace_repo.list(limit=limit, offset=offset),
        namespace_repo.count_all(),
    )
    return OffsetPage[SyncNamespaceResponse](
        items=[
            SyncNamespaceResponse(
                name=ns.name,
                company_id=ns.company_id,
                description=ns.description,
                is_default=ns.is_default,
                sync_settings=ns.sync_settings,
            )
            for ns in namespaces
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put("/{namespace_name}", response_model=SyncNamespaceResponse)
async def update_namespace_sync_settings(
    container: ContainerDep,
    namespace_name: str,
    body: SyncNamespaceUpdateRequest,
) -> SyncNamespaceResponse:
    """Обновляет только секцию `sync_settings` namespace.

    Создание namespace выполняется CRM. 404, если namespace не существует
    в shared `NamespaceRepository` для текущей компании.
    """
    _ = require_current_user()
    namespace_repo = container.namespace_repository
    existing = await namespace_repo.get(namespace_name)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Namespace '{namespace_name}' не найден")
    existing.sync_settings = body.sync_settings
    await namespace_repo.set(existing)
    return SyncNamespaceResponse(
        name=existing.name,
        company_id=existing.company_id,
        description=existing.description,
        is_default=existing.is_default,
        sync_settings=existing.sync_settings,
    )
