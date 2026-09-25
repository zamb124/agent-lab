"""
API для запросов доступа к entities.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.crm.di import Di
from apps.crm.models.access_request_models import (
    AccessRequestCreate,
    AccessRequestResponse,
    AccessRequestUpdate,
)
from apps.crm.realtime.operations import (
    CrmAccessRequestIdPayload,
    CrmAccessRequestListPayload,
    CrmAccessRequestUpdatePayload,
    op_access_requests_create,
    op_access_requests_item,
    op_access_requests_list,
    op_access_requests_update,
)
from core.context import require_context
from core.pagination import OffsetPage

router = APIRouter(prefix="/access-requests", tags=["Access Requests"])


@router.post("", response_model=AccessRequestResponse)
async def request_access(
    data: AccessRequestCreate,
    di: Di,
):
    return await op_access_requests_create(
        data,
        user=require_context().user,
        di=di,
    )


@router.get("/{access_request_id}", response_model=AccessRequestResponse)
async def get_access_request(
    access_request_id: str,
    di: Di,
):
    return await op_access_requests_item(
        CrmAccessRequestIdPayload(access_request_id=access_request_id),
        user=require_context().user,
        di=di,
    )


@router.put("/{access_request_id}", response_model=AccessRequestResponse)
async def update_access_request(
    access_request_id: str,
    data: AccessRequestUpdate,
    di: Di,
):
    return await op_access_requests_update(
        CrmAccessRequestUpdatePayload(
            access_request_id=access_request_id,
            status=data.status,
        ),
        user=require_context().user,
        di=di,
    )


@router.get("", response_model=OffsetPage[AccessRequestResponse])
async def list_pending_requests(
    di: Di,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[AccessRequestResponse]:
    return await op_access_requests_list(
        CrmAccessRequestListPayload(status=status, limit=limit, offset=offset),
        user=require_context().user,
        di=di,
    )
