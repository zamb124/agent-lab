"""
API endpoints для сессий.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel

from apps.agents.src.container import AgentContainer, get_container
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["sessions"])


class SessionResponse(BaseModel):
    """Сессия в ответе"""

    session_id: str
    channel: str
    user_id: str
    agent_id: str
    status: str
    message_count: int
    first_message: Optional[str] = None
    created_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None


class SessionsListResponse(BaseModel):
    """Список сессий с пагинацией"""

    sessions: List[SessionResponse]
    total: int
    limit: int
    offset: int


def get_container_dep() -> AgentContainer:
    """Dependency для получения контейнера"""
    return get_container()


@router.get("/", response_model=SessionsListResponse)
async def list_sessions(
    user_id: Optional[str] = Query(None, description="Фильтр по пользователю"),
    agent_id: Optional[str] = Query(None, description="Фильтр по агенту"),
    date_from: Optional[datetime] = Query(None, description="Начало периода"),
    date_to: Optional[datetime] = Query(None, description="Конец периода"),
    limit: int = Query(50, ge=1, le=500, description="Максимум записей"),
    offset: int = Query(0, ge=0, description="Смещение"),
    container: AgentContainer = Depends(get_container_dep),
) -> SessionsListResponse:
    """
    Получает список сессий с фильтрами.

    Args:
        user_id: Фильтр по пользователю
        agent_id: Фильтр по агенту
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
        agent_id=agent_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )

    return SessionsListResponse(
        sessions=[
            SessionResponse(
                session_id=s.session_id,
                channel=s.channel,
                user_id=s.user_id,
                agent_id=s.agent_id,
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
    session_id: str = Path(..., description="ID сессии для удаления"),
    container: AgentContainer = Depends(get_container_dep),
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

