"""REST-зеркало команд пространств Sync (`sync/namespaces/*`).

Sync space = platform namespace 1:1. Создание/удаление — CRM; Sync читает список
и пишет свою секцию `Namespace.sync_settings`.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.sync.dependencies import ContainerDep
from core.context import require_context
from core.models.base import StrictBaseModel
from core.models.identity_models import Namespace, NamespaceKind, NamespaceSyncSettings
from core.namespace.operations import (
    NamespacesListPayload,
    NamespaceSyncSettingsUpdatePayload,
    op_namespaces_list,
    op_namespaces_sync_settings_update,
)
from core.pagination import OffsetPage

router = APIRouter()


class SyncNamespaceUpdateRequest(StrictBaseModel):
    sync_settings: NamespaceSyncSettings | None = None


@router.get("", response_model=OffsetPage[Namespace])
async def list_namespaces(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[Namespace]:
    return await op_namespaces_list(
        NamespacesListPayload(limit=limit, offset=offset, kinds=frozenset({NamespaceKind.COMPANY_WORKSPACE})),
        user=require_context().user,
        container=container,
    )


@router.put("/{name}", response_model=Namespace)
async def update_namespace_sync_settings(
    container: ContainerDep,
    name: str,
    body: SyncNamespaceUpdateRequest,
) -> Namespace:
    return await op_namespaces_sync_settings_update(
        NamespaceSyncSettingsUpdatePayload(name=name, sync_settings=body.sync_settings),
        user=require_context().user,
        container=container,
    )
