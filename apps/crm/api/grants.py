"""Гранты: тонкая REST-обвязка тех же `op_*`."""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from apps.crm.di import Di
from apps.crm.models.grant_models import AccessGrantResponse
from apps.crm.realtime.operations import (
    CrmGrantCreatePayload,
    CrmGrantIdPayload,
    CrmGrantsListPayload,
    op_grants_create,
    op_grants_item,
    op_grants_list,
    op_grants_remove,
)
from core.context import require_context
from core.pagination import OffsetPage

router = APIRouter(prefix="/grants", tags=["Grants"])


@router.get("", response_model=OffsetPage[AccessGrantResponse])
async def list_grants(
    payload: Annotated[CrmGrantsListPayload, Query()],
    di: Di,
) -> OffsetPage[AccessGrantResponse]:
    return await op_grants_list(
        payload,
        user=require_context().user,
        di=di,
    )


@router.post("", response_model=AccessGrantResponse)
async def create_grant(
    payload: CrmGrantCreatePayload,
    di: Di,
) -> AccessGrantResponse:
    return await op_grants_create(
        payload,
        user=require_context().user,
        di=di,
    )


@router.delete("/{grant_id}", status_code=204)
async def revoke_grant(
    grant_id: str,
    di: Di,
) -> Response:
    await op_grants_remove(
        CrmGrantIdPayload(grant_id=grant_id),
        user=require_context().user,
        di=di,
    )
    return Response(status_code=204)


@router.get("/{grant_id}", response_model=AccessGrantResponse)
async def get_grant(
    grant_id: str,
    di: Di,
) -> AccessGrantResponse:
    return await op_grants_item(
        CrmGrantIdPayload(grant_id=grant_id),
        user=require_context().user,
        di=di,
    )
