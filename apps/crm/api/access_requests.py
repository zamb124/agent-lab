"""
API для запросов доступа к entities.

User Story: Запрос доступа к чужим entities с указанием причины.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query

from apps.crm.services.access_request_service import AccessRequestService
from apps.crm.models.access_request_models import (
    AccessRequestCreate,
    AccessRequestUpdate,
    AccessRequestResponse
)
from apps.crm.dependencies import get_access_request_service
from core.context import get_context

router = APIRouter(prefix="/access-requests", tags=["Access Requests"])


@router.post("", response_model=AccessRequestResponse)
async def request_access(
    data: AccessRequestCreate,
    service: AccessRequestService = Depends(get_access_request_service)
):
    """Создать запрос на доступ к entity"""
    ctx = get_context()
    if not ctx or not ctx.user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        request = await service.create_request(
            entity_id=data.resource_id,
            requester_user_id=ctx.user.user_id,
            requester_company_id=ctx.active_company.company_id if ctx.active_company else "system",
            message=data.message,
            include_dependencies=data.include_dependencies,
            max_depth=data.max_depth
        )
        return AccessRequestResponse.model_validate(request)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/{request_id}", response_model=AccessRequestResponse)
async def get_access_request(
    request_id: str,
    service: AccessRequestService = Depends(get_access_request_service)
):
    """Получить статус запроса на доступ"""
    request = await service.get_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    return AccessRequestResponse.model_validate(request)


@router.put("/{request_id}", response_model=AccessRequestResponse)
async def update_access_request(
    request_id: str,
    data: AccessRequestUpdate,
    service: AccessRequestService = Depends(get_access_request_service)
):
    """Одобрить/отклонить запрос на доступ"""
    ctx = get_context()
    if not ctx or not ctx.user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        if data.status == "approved":
            await service.approve_request(request_id, ctx.user.user_id)
        elif data.status == "rejected":
            await service.reject_request(request_id, ctx.user.user_id)
        else:
            raise HTTPException(status_code=400, detail="Invalid status")
        
        request = await service.get_request(request_id)
        return AccessRequestResponse.model_validate(request)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("", response_model=List[AccessRequestResponse])
async def list_pending_requests(
    status: Optional[str] = Query(None),
    service: AccessRequestService = Depends(get_access_request_service)
):
    """Получить список ожидающих запросов"""
    ctx = get_context()
    if not ctx or not ctx.user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    company_id = ctx.active_company.company_id if ctx.active_company else "system"
    
    requests = await service.list_requests(
        company_id=company_id,
        status=status
    )
    
    return [AccessRequestResponse.model_validate(r) for r in requests]

