"""
API для запросов доступа к entities.

User Story: Запрос доступа к чужим entities с указанием причины.
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.crm.dependencies import ContainerDep
from apps.crm.models.access_request_models import (
    AccessRequestCreate,
    AccessRequestResponse,
    AccessRequestUpdate,
)
from core.context import get_context
from core.pagination import OffsetPage

router = APIRouter(prefix="/access-requests", tags=["Access Requests"])


@router.post("", response_model=AccessRequestResponse)
async def request_access(
    data: AccessRequestCreate,
    container: ContainerDep,
):
    """Создать запрос на доступ к entity"""
    ctx = get_context()
    if not ctx or not ctx.user:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        access_request = await container.access_request_service.create_access_request(
            entity_id=data.resource_id,
            requester_user_id=ctx.user.user_id,
            requester_company_id=ctx.active_company.company_id if ctx.active_company else "system",
            message=data.message,
            include_dependencies=data.include_dependencies,
            max_depth=data.max_depth,
        )
        return AccessRequestResponse.model_validate(access_request)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/{access_request_id}", response_model=AccessRequestResponse)
async def get_access_request(
    access_request_id: str,
    container: ContainerDep,
):
    """Получить статус запроса на доступ"""
    access_request = await container.access_request_service.get_access_request(access_request_id)
    if not access_request:
        raise HTTPException(status_code=404, detail="Request not found")

    return AccessRequestResponse.model_validate(access_request)


@router.put("/{access_request_id}", response_model=AccessRequestResponse)
async def update_access_request(
    access_request_id: str,
    data: AccessRequestUpdate,
    container: ContainerDep,
):
    """Одобрить/отклонить запрос на доступ"""
    ctx = get_context()
    if not ctx or not ctx.user:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        if data.status == "approved":
            access_request = await container.access_request_service.approve_access_request(
                access_request_id, ctx.user.user_id
            )
        elif data.status == "rejected":
            access_request = await container.access_request_service.reject_access_request(
                access_request_id, ctx.user.user_id
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid status")

        return AccessRequestResponse.model_validate(access_request)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("", response_model=OffsetPage[AccessRequestResponse])
async def list_pending_requests(
    container: ContainerDep,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[AccessRequestResponse]:
    ctx = get_context()
    if not ctx or not ctx.user:
        raise HTTPException(status_code=401, detail="Authentication required")

    company_id = ctx.active_company.company_id if ctx.active_company else "system"

    access_requests, total = await asyncio.gather(
        container.access_request_service.list_access_requests(
            company_id=company_id, status=status, limit=limit, offset=offset
        ),
        container.access_request_service.count_access_requests(
            company_id=company_id, status=status
        ),
    )
    return OffsetPage[AccessRequestResponse](
        items=[AccessRequestResponse.model_validate(r) for r in access_requests],
        total=total,
        limit=limit,
        offset=offset,
    )
