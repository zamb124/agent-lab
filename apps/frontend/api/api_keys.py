"""REST-зеркало команд `frontend/api_keys/*`."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.frontend.di import Di
from apps.frontend.models import ApiKeyCreate, ApiKeyCreated, ApiKeyUpdate
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
from core.models.api_key import ApiKeyRecord
from core.pagination import OffsetPage

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


@router.get("", response_model=OffsetPage[ApiKeyRecord])
async def list_api_keys(
    di: Di,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[ApiKeyRecord]:
    return await op_api_keys_list(
        OffsetPayload(limit=limit, offset=offset), user=require_context().user, di=di
    )


@router.post("", response_model=ApiKeyCreated)
async def create_api_key(key_data: ApiKeyCreate, di: Di) -> ApiKeyCreated:
    return await op_api_keys_create(key_data, user=require_context().user, di=di)


@router.patch("/{key_id}", response_model=ApiKeyRenamed)
async def update_api_key(key_id: str, body: ApiKeyUpdate, di: Di) -> ApiKeyRenamed:
    return await op_api_keys_rename(
        ApiKeyRenamePayload(key_id=key_id, name=body.name), user=require_context().user, di=di
    )


@router.delete("/{key_id}", response_model=ApiKeyRevoked)
async def revoke_api_key(key_id: str, di: Di) -> ApiKeyRevoked:
    return await op_api_keys_revoke(
        ApiKeyIdPayload(key_id=key_id), user=require_context().user, di=di
    )
