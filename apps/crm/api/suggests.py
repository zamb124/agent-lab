from typing import Annotated

from fastapi import APIRouter, Query

from apps.crm.dependencies import ContainerDep
from apps.crm.models.api import SuggestResponse
from apps.crm.realtime.operations import (
    CrmSuggestKeyPayload,
    CrmSuggestsListPayload,
    op_suggests_dismiss,
    op_suggests_list,
    op_suggests_resolve,
)
from core.context import require_context
from core.pagination import OffsetPage

router = APIRouter(prefix="/namespaces/{namespace}/suggests", tags=["Suggests"])


@router.get("", response_model=OffsetPage[SuggestResponse])
async def list_suggests(
    namespace: str,
    container: ContainerDep,
    status: Annotated[str | None, Query()] = "pending",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await op_suggests_list(
        CrmSuggestsListPayload(
            namespace=namespace, status=status, limit=limit, offset=offset
        ),
        user=require_context().user,
        container=container,
    )


@router.post("/{suggest_id}/resolve", response_model=SuggestResponse)
async def resolve_suggest(
    namespace: str,
    suggest_id: str,
    container: ContainerDep,
):
    return await op_suggests_resolve(
        CrmSuggestKeyPayload(namespace=namespace, suggest_id=suggest_id),
        user=require_context().user,
        container=container,
    )


@router.post("/{suggest_id}/dismiss", response_model=SuggestResponse)
async def dismiss_suggest(
    namespace: str,
    suggest_id: str,
    container: ContainerDep,
):
    return await op_suggests_dismiss(
        CrmSuggestKeyPayload(namespace=namespace, suggest_id=suggest_id),
        user=require_context().user,
        container=container,
    )
