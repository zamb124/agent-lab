"""
API endpoints для инспекции чекпоинтеров
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Query

from app.core.state_inspector import StateInspector

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/checkpoints/timeline/{thread_id}")
async def get_checkpoint_timeline(
    thread_id: str,
    include_values: bool = Query(True, description="Включать детальные значения сообщений")
) -> Dict[str, Any]:
    """
    Получить timeline данные чекпоинтеров для thread_id.

    Args:
        thread_id: ID потока выполнения
        include_values: Включать ли детальные значения сообщений
        
    Returns:
        Словарь с данными дерева чекпоинтеров
    """
    logger.info(f"🔍 Запрос timeline для thread_id: {thread_id}")
    
    inspector = StateInspector()
    timeline_data = await inspector.get_timeline(thread_id, include_values=include_values)
    
    logger.info(f"📊 Получены данные timeline: tree={len(timeline_data.get('tree', []))} элементов, summary={timeline_data.get('summary', {})}")
    
    # Преобразование данных для фронтенда
    result = {
        "thread_id": thread_id,
        "tree": timeline_data.get("tree", []),
        "summary": timeline_data.get("summary", {})
    }
    
    logger.info(f"✅ Возвращаем результат: {result}")
    return result


@router.get("/checkpoints/history/{thread_id}")
async def get_checkpoint_history(thread_id: str) -> Dict[str, Any]:
    """
    Получить историю чекпоинтеров для thread_id.
    
    Args:
        thread_id: ID потока выполнения
        
    Returns:
        Список чекпоинтеров с метаданными
    """
    inspector = StateInspector()
    history = await inspector.get_state_history(thread_id)
    return {"thread_id": thread_id, "history": history}


@router.get("/checkpoints/connections/{thread_id}")
async def get_checkpoint_connections(thread_id: str) -> Dict[str, Any]:
    """
    Получить связи между чекпоинтерами для thread_id.
    
    Args:
        thread_id: ID потока выполнения
        
    Returns:
        Словарь с информацией о связях чекпоинтеров
    """
    inspector = StateInspector()
    connections = await inspector.get_state_connections(thread_id)
    return connections

