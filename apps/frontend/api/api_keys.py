"""REST-зеркало команд `frontend/api_keys/*`."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import ApiKey, ApiKeyCreate, ApiKeyCreated, ApiKeyUpdate
from apps.frontend.realtime.company_operations import (
    ApiKeyIdPayload,
    ApiKeyRenamed,
    ApiKeyRenamePayload,
    ApiKeyRevoked,
    OffsetPayload,
    op_api_keys_create,
    op_api_keys_list,
    op_api_keys_rename,
    op_api_keys_revoke,
)
from core.context import require_context
from core.pagination import OffsetPage

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


@router.get("", response_model=OffsetPage[ApiKey])
async def list_api_keys(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[ApiKey]:
    return await op_api_keys_list(
        OffsetPayload(limit=limit, offset=offset), user=require_context().user, container=container
    )


@router.post("", response_model=ApiKeyCreated)
async def create_api_key(key_data: ApiKeyCreate, container: ContainerDep) -> ApiKeyCreated:
    return await op_api_keys_create(key_data, user=require_context().user, container=container)


@router.patch("/{key_id}", response_model=ApiKeyRenamed)
async def update_api_key(key_id: str, body: ApiKeyUpdate, container: ContainerDep) -> ApiKeyRenamed:
    return await op_api_keys_rename(
        ApiKeyRenamePayload(key_id=key_id, name=body.name), user=require_context().user, container=container
    )


@router.delete("/{key_id}", response_model=ApiKeyRevoked)
async def revoke_api_key(key_id: str, container: ContainerDep) -> ApiKeyRevoked:
    return await op_api_keys_revoke(
        ApiKeyIdPayload(key_id=key_id), user=require_context().user, container=container
    )
