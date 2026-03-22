"""
API для получения трейсов.

Позволяет получить все spans по сессии, task_id, user_id или flow_id.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from apps.flows.src.container import get_container
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["Traces"])


@router.get("/session/{session_id}")
async def get_traces_by_session(
    session_id: str,
    limit: int = Query(default=100, le=1000),
) -> Dict[str, Any]:
    """
    Получает все трейсы для сессии выполнения flow.
    
    Args:
        session_id: Идентификатор сессии выполнения (как хранится в span/session)
        limit: Максимальное количество spans
        
    Returns:
        Список spans с иерархией
    """
    container = get_container()
    spans = await container.span_repository.get_spans_by_session(session_id, limit)
    
    return {
        "session_id": session_id,
        "spans_count": len(spans),
        "spans": _build_span_tree(spans),
    }


@router.get("/task/{task_id}")
async def get_traces_by_task(task_id: str) -> Dict[str, Any]:
    """
    Получает все трейсы для конкретного task.
    
    Args:
        task_id: ID задачи A2A
        
    Returns:
        Список spans с иерархией
    """
    container = get_container()
    spans = await container.span_repository.get_spans_by_task(task_id)
    
    return {
        "task_id": task_id,
        "spans_count": len(spans),
        "spans": _build_span_tree(spans),
    }


@router.get("/trace/{trace_id}")
async def get_trace(trace_id: str) -> Dict[str, Any]:
    """
    Получает все spans для trace_id.
    
    Args:
        trace_id: ID трейса
        
    Returns:
        Полное дерево spans
    """
    container = get_container()
    spans = await container.span_repository.get_trace(trace_id)
    
    return {
        "trace_id": trace_id,
        "spans_count": len(spans),
        "spans": _build_span_tree(spans),
    }


@router.get("/user/{user_id}")
async def get_traces_by_user(
    user_id: str,
    from_time: Optional[datetime] = None,
    to_time: Optional[datetime] = None,
    limit: int = Query(default=100, le=1000),
) -> Dict[str, Any]:
    """
    Получает трейсы для пользователя.
    
    Args:
        user_id: ID пользователя
        from_time: Начало периода
        to_time: Конец периода
        limit: Максимальное количество spans
        
    Returns:
        Список spans
    """
    container = get_container()
    spans = await container.span_repository.get_spans_by_user(
        user_id, from_time, to_time, limit
    )
    
    return {
        "user_id": user_id,
        "spans_count": len(spans),
        "spans": spans,
    }


@router.get("/flow/{flow_id}")
async def get_traces_by_flow(
    flow_id: str,
    from_time: Optional[datetime] = None,
    to_time: Optional[datetime] = None,
    limit: int = Query(default=100, le=1000),
) -> Dict[str, Any]:
    """
    Получает трейсы для агента.
    
    Args:
        flow_id: ID агента
        from_time: Начало периода
        to_time: Конец периода
        limit: Максимальное количество spans
        
    Returns:
        Список spans
    """
    container = get_container()
    spans = await container.span_repository.get_spans_by_flow(
        flow_id, from_time, to_time, limit
    )
    
    return {
        "flow_id": flow_id,
        "spans_count": len(spans),
        "spans": spans,
    }


@router.get("/search")
async def search_traces(
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    flow_id: Optional[str] = None,
    from_time: Optional[datetime] = None,
    to_time: Optional[datetime] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    """
    Поиск трейсов с фильтрами.
    
    Args:
        user_id: Фильтр по пользователю
        session_id: Фильтр по сессии
        flow_id: Фильтр по агенту
        from_time: Начало периода
        to_time: Конец периода
        limit: Максимальное количество результатов
        offset: Смещение для пагинации
        
    Returns:
        Список trace с деревом spans для каждого trace и общее количество
    """
    container = get_container()
    traces, total_count = await container.span_repository.search_traces(
        user_id=user_id,
        session_id=session_id,
        flow_id=flow_id,
        from_time=from_time,
        to_time=to_time,
        limit=limit,
        offset=offset,
    )
    
    return {
        "traces_count": len(traces),
        "total_count": total_count,
        "traces": traces,
    }


def _build_span_tree(spans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Строит дерево spans из плоского списка.
    
    Root spans (parent_span_id is None) становятся корнями,
    остальные spans вкладываются в children.
    """
    if not spans:
        return []
    
    # Индекс spans по span_id
    span_map = {s["span_id"]: {**s, "children": []} for s in spans}
    
    # Корневые spans
    roots = []
    
    for span in spans:
        span_id = span["span_id"]
        parent_id = span.get("parent_span_id")
        
        if parent_id and parent_id in span_map:
            # Добавляем как child
            span_map[parent_id]["children"].append(span_map[span_id])
        else:
            # Root span
            roots.append(span_map[span_id])
    
    return roots

