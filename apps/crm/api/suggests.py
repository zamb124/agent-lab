from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from apps.crm.dependencies import ContainerDep
from apps.crm.types import JsonObject
from core.context import get_context
from core.pagination import OffsetPage

router = APIRouter(prefix="/namespaces/{namespace}/suggests", tags=["Suggests"])


class SuggestResponse(BaseModel):
    id: str
    suggest_type: str
    status: str
    target_entity_ids: list[str]
    payload: JsonObject


@router.get("", response_model=OffsetPage[SuggestResponse])
async def list_suggests(
    namespace: str,
    container: ContainerDep,
    status: Annotated[str | None, Query()] = "pending",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    ctx = get_context()
    if not ctx or not ctx.user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    ns_obj = await container.namespace_repository.get(namespace)
    if not ns_obj:
        raise HTTPException(status_code=404, detail="Namespace not found")

    page = await container.suggest_service.list_suggests(namespace, status, limit, offset)
    items = [
        SuggestResponse(
            id=s.id,
            suggest_type=s.suggest_type,
            status=s.status,
            target_entity_ids=s.target_entity_ids,
            payload=s.payload,
        )
        for s in page.items
    ]
    return OffsetPage(items=items, total=page.total, limit=page.limit, offset=page.offset)


@router.post("/{suggest_id}/resolve", response_model=SuggestResponse)
async def resolve_suggest(
    namespace: str,
    suggest_id: str,
    container: ContainerDep,
):
    ctx = get_context()
    if not ctx or not ctx.user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    ns_obj = await container.namespace_repository.get(namespace)
    if not ns_obj:
        raise HTTPException(status_code=404, detail="Namespace not found")

    try:
        s = await container.suggest_service.resolve_suggest(suggest_id, namespace=namespace)
        return SuggestResponse(
            id=s.id,
            suggest_type=s.suggest_type,
            status=s.status,
            target_entity_ids=s.target_entity_ids,
            payload=s.payload,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{suggest_id}/dismiss", response_model=SuggestResponse)
async def dismiss_suggest(
    namespace: str,
    suggest_id: str,
    container: ContainerDep,
):
    ctx = get_context()
    if not ctx or not ctx.user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    ns_obj = await container.namespace_repository.get(namespace)
    if not ns_obj:
        raise HTTPException(status_code=404, detail="Namespace not found")

    try:
        s = await container.suggest_service.dismiss_suggest(suggest_id, namespace=namespace)
        return SuggestResponse(
            id=s.id,
            suggest_type=s.suggest_type,
            status=s.status,
            target_entity_ids=s.target_entity_ids,
            payload=s.payload,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
