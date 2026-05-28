"""
API endpoints для сессий.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import SessionConfig
from core.logging import get_logger
from core.pagination import OffsetPage

logger = get_logger(__name__)

router = APIRouter(tags=["sessions"])


@router.get("/", response_model=OffsetPage[SessionConfig])
async def list_sessions(
    container: ContainerDep,
    user_id: Annotated[str | None, Query(description="Фильтр по пользователю")] = None,
    flow_id: Annotated[str | None, Query(description="Фильтр по flow")] = None,
    branch_id: Annotated[str | None, Query(description="Фильтр по ветке (branch_id)")] = None,
    date_from: Annotated[datetime | None, Query(description="Начало периода")] = None,
    date_to: Annotated[datetime | None, Query(description="Конец периода")] = None,
    limit: Annotated[int, Query(ge=1, le=200, description="Максимум записей")] = 50,
    offset: Annotated[int, Query(ge=0, description="Смещение")] = 0,
) -> OffsetPage[SessionConfig]:
    """
    Получает список сессий с фильтрами.

    Аргументы:
        user_id: Фильтр по пользователю
        flow_id: Фильтр по агенту
        date_from: Начало периода
        date_to: Конец периода
        limit: Максимум записей
        offset: Смещение
        container: Контейнер платформы

    Возвращает:
        Список сессий с пагинацией
    """
    sessions, total = await container.workflow_runtime.search_sessions(
        user_id=user_id,
        flow_id=flow_id,
        branch_id=branch_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )

    return OffsetPage[SessionConfig](
        items=sessions,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/{session_id}")
async def delete_session(
    container: ContainerDep,
    session_id: Annotated[str, Path(description="ID сессии для удаления")],
) -> dict[str, bool | str]:
    """
    Удаляет сессию по ID.

    Аргументы:
        session_id: ID сессии
        container: Контейнер платформы

    Возвращает:
        Результат удаления
    """
    deleted = await container.workflow_runtime.delete_state(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True, "session_id": session_id}
