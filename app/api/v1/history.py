"""
API для работы с историей выполнения flow
"""

import logging
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Query

from app.core.flow_factory import FlowFactory
from app.models.history_models import MessageHistoryResponse, SessionListResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/history",
    tags=["История и аналитика"],
    responses={
        404: {"description": "Сессия не найдена"},
        500: {"description": "Ошибка получения данных"}
    }
)


@router.get("/sessions", response_model=SessionListResponse, summary="Список диалогов")
async def get_sessions(
    platform: Optional[str] = Query(None, description="Фильтр по платформе (web, telegram, whatsapp, api)"),
    flow_id: Optional[str] = Query(None, description="Фильтр по боту"),
    user_id: Optional[str] = Query(None, description="Фильтр по пользователю"),
    status: Optional[str] = Query(None, description="Фильтр по статусу (active, inactive)"),
    date_from: Optional[datetime] = Query(None, description="Начало периода (ISO 8601)"),
    date_to: Optional[datetime] = Query(None, description="Конец периода (ISO 8601)"),
    limit: int = Query(50, description="Максимальное количество результатов", ge=1, le=500),
    offset: int = Query(0, description="Смещение для пагинации", ge=0),
):
    """
    Получает список всех диалогов (сессий) с возможностью фильтрации.
    
    **Фильтры:**
    Все фильтры опциональные, можно комбинировать:
    - По платформе (web, telegram, whatsapp, api)
    - По конкретному боту
    - По пользователю
    - По статусу (active/inactive)
    - По периоду времени
    
    **Пагинация:**
    Используйте limit и offset для постраничной навигации.
    
    **Для аналитики:**
    Этот endpoint позволяет получить статистику использования ботов.
    
    Args:
        platform: Платформа (web, telegram, whatsapp, api)
        flow_id: ID бота
        user_id: ID пользователя
        status: Статус сессии (active, inactive)
        date_from: Начало периода
        date_to: Конец периода
        limit: Количество результатов (максимум 500)
        offset: Смещение для пагинации
        
    Returns:
        Массив сессий с количеством сообщений, первым сообщением, временными метками
    """
    logger.info(
        f"📋 API: Запрос списка сессий (platform={platform}, flow={flow_id}, limit={limit}, offset={offset})"
    )
    
    flow_factory = FlowFactory()
    
    result = await flow_factory.get_flow_sessions(
        platform=platform,
        flow_id=flow_id,
        user_id=user_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset
    )
    
    logger.info(f"✅ API: Возвращаем {len(result.sessions)} сессий из {result.total}")
    return result


@router.get("/sessions/{session_id}/messages", response_model=MessageHistoryResponse)
async def get_session_messages(
    session_id: str,
    limit: int = Query(100, description="Максимальное количество checkpoint'ов", ge=1, le=1000),
    include_checkpoints: bool = Query(False, description="Включать детали checkpoint'ов")
):
    """
    Получает историю сообщений для конкретной сессии.
    
    Args:
        session_id: ID сессии
        limit: Максимальное количество checkpoint'ов
        include_checkpoints: Включать ли детали checkpoint'ов
        
    Returns:
        Полная история сообщений с вызовами инструментов
    """
    logger.info(f"📜 API: Запрос истории для сессии {session_id}")
    
    flow_factory = FlowFactory()
    
    history = await flow_factory.get_flow_history(
        session_id=session_id,
        limit=limit,
        include_checkpoints=include_checkpoints
    )
    
    if history.total_messages == 0:
        logger.warning(f"⚠️ API: История для {session_id} пуста")
    else:
        logger.info(f"✅ API: Возвращаем {history.total_messages} сообщений для {session_id}")
    
    return history
