"""REST-зеркало команды `sync/platform_namespaces/list_requested`."""

from fastapi import APIRouter, Query

from apps.sync.dependencies import ContainerDep
from apps.sync.realtime.operations import (
    PlatformNamespaceItem,
    PlatformNamespacesListPayload,
    op_platform_namespaces_list,
)
from core.context import get_context
from core.pagination import OffsetPage

router = APIRouter()


@router.get("", response_model=OffsetPage[PlatformNamespaceItem])
async def list_platform_namespaces(
    container: ContainerDep,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> OffsetPage[PlatformNamespaceItem]:
    user = get_context().user
    result = await op_platform_namespaces_list(
        PlatformNamespacesListPayload(limit=limit, offset=offset),
        user=user,
        container=container,
    )
    return OffsetPage[PlatformNamespaceItem](
        items=result.items, total=result.total, limit=result.limit, offset=result.offset
    )
