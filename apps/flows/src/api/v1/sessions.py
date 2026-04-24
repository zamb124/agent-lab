"""
API endpoints для сессий.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

from apps.flows.src.dependencies import ContainerDep
from core.logging import get_logger
from core.pagination import OffsetPage

logger = get_logger(__name__)

router = APIRouter(tags=["sessions"])


class SessionResponse(BaseModel):
    """Сессия в ответе"""

    session_id: str
    channel: str
    user_id: str
    flow_id: str
    status: str
    message_count: int
    first_message: Optional[str] = None
    created_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None


@router.get("/", response_model=OffsetPage[SessionResponse])
async def list_sessions(
    container: ContainerDep,
    user_id: Optional[str] = Query(None, description="Фильтр по пользователю"),
    flow_id: Optional[str] = Query(None, description="Фильтр по flow"),
    skill_id: Optional[str] = Query(None, description="Фильтр по skill"),
    date_from: Optional[datetime] = Query(None, description="Начало периода"),
    date_to: Optional[datetime] = Query(None, description="Конец периода"),
    limit: int = Query(50, ge=1, le=200, description="Максимум записей"),
    offset: int = Query(0, ge=0, description="Смещение"),
) -> OffsetPage[SessionResponse]:
    """
    Получает список сессий с фильтрами.

    Args:
        user_id: Фильтр по пользователю
        flow_id: Фильтр по агенту
        date_from: Начало периода
        date_to: Конец периода
        limit: Максимум записей
        offset: Смещение
        container: Контейнер платформы

    Returns:
        Список сессий с пагинацией
    """
    sessions, total = await container.state_repository.search_sessions(
        user_id=user_id,
        flow_id=flow_id,
        skill_id=skill_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )

    return OffsetPage[SessionResponse](
        items=[
            SessionResponse(
                session_id=s.session_id,
                channel=s.channel,
                user_id=s.user_id,
                flow_id=s.flow_id,
                status=s.status.value if hasattr(s.status, "value") else str(s.status),
                message_count=s.message_count,
                first_message=s.first_message,
                created_at=s.created_at,
                last_activity=s.last_activity,
            )
            for s in sessions
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/{session_id}")
async def delete_session(
    container: ContainerDep,
    session_id: str = Path(..., description="ID сессии для удаления"),
) -> dict:
    """
    Удаляет сессию по ID.

    Args:
        session_id: ID сессии
        container: Контейнер платформы

    Returns:
        Результат удаления
    """
    deleted = await container.state_repository.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True, "session_id": session_id}

