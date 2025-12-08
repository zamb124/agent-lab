"""
API для работы с историей выполнения flow.
Использует FlowFactory из AgentsContainer напрямую.
"""

import logging
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime

from apps.agents.container import get_agents_container
from apps.agents.models.history_models import MessageHistoryResponse, SessionListResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/history", tags=["history"])


@router.get("/sessions/{session_id}/messages", response_model=MessageHistoryResponse)
async def get_session_messages(
    session_id: str,
    limit: int = Query(100, ge=1, le=1000),
    include_checkpoints: bool = Query(False)
):
    """Получить историю сообщений для сессии"""
    flow_factory = get_agents_container().flow_factory
    
    history = await flow_factory.get_flow_history(
        session_id=session_id,
        limit=limit,
        include_checkpoints=include_checkpoints
    )
    
    return history


@router.get("/sessions", response_model=SessionListResponse)
async def get_sessions(
    platform: Optional[str] = Query(None),
    flow_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Получить список сессий"""
    flow_factory = get_agents_container().flow_factory
    
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
    
    return result

