"""
API для запросов на доступ.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from apps.crm.dependencies import AccessRequestServiceDep
from apps.crm.models.access_request_models import (
    AccessRequestCreate,
    AccessRequestResponse,
)

router = APIRouter()


@router.post("", response_model=AccessRequestResponse)
async def create_access_request(
    data: AccessRequestCreate,
    service: AccessRequestServiceDep,
):
    """
    Создает запрос на доступ к приватному ресурсу.
    
    Владелец ресурса получит уведомление и сможет одобрить/отклонить запрос.
    """
    try:
        return await service.create_request(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/incoming", response_model=List[AccessRequestResponse])
async def get_incoming_requests(
    service: AccessRequestServiceDep,
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    limit: int = Query(100, ge=1, le=500),
):
    """
    Получает входящие запросы на доступ к вашим ресурсам.
    """
    return await service.get_incoming_requests(status=status, limit=limit)


@router.get("/outgoing", response_model=List[AccessRequestResponse])
async def get_outgoing_requests(
    service: AccessRequestServiceDep,
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
    limit: int = Query(100, ge=1, le=500),
):
    """
    Получает исходящие запросы на доступ (ваши запросы к чужим ресурсам).
    """
    return await service.get_outgoing_requests(status=status, limit=limit)


@router.get("/pending-count")
async def get_pending_count(
    service: AccessRequestServiceDep,
):
    """
    Получает количество ожидающих входящих запросов.
    Используется для badge в UI.
    """
    count = await service.get_pending_count()
    return {"count": count}


@router.post("/{request_id}/approve", response_model=AccessRequestResponse)
async def approve_request(
    request_id: str,
    service: AccessRequestServiceDep,
):
    """
    Одобряет запрос на доступ.
    
    Только владелец ресурса может одобрить запрос.
    При одобрении запрашивающий получит доступ к ресурсу.
    """
    try:
        return await service.approve_request(request_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{request_id}/reject", response_model=AccessRequestResponse)
async def reject_request(
    request_id: str,
    service: AccessRequestServiceDep,
):
    """
    Отклоняет запрос на доступ.
    
    Только владелец ресурса может отклонить запрос.
    """
    try:
        return await service.reject_request(request_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

