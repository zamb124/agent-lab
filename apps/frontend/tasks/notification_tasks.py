"""
TaskIQ задачи для отправки уведомлений через WebSocket.
"""

import logging
from typing import Any, Dict

from core.tasks.broker import broker

logger = logging.getLogger(__name__)


@broker.task
async def send_notification_task(
    user_id: str,
    notification_type: str,
    data: Dict[str, Any],
    session_id: str = None,
) -> bool:
    """
    Отправка уведомления через WebSocket.
    
    Args:
        user_id: ID пользователя
        notification_type: Тип уведомления (AGENT_RESPONSE, TYPING, ERROR и т.д.)
        data: Данные уведомления
        session_id: ID сессии (опционально, для отправки в конкретную сессию)
    
    Returns:
        True если уведомление отправлено
    """
    from apps.frontend.core.websocket_manager import websocket_manager
    
    notification = {
        "type": notification_type,
        "data": data,
    }
    
    if session_id:
        # Отправляем в конкретную сессию
        await websocket_manager.send_to_session(session_id, notification, "chat")
        logger.debug(f"Уведомление отправлено в сессию {session_id}: {notification_type}")
    else:
        # Отправляем всем сессиям пользователя
        # TODO: реализовать send_to_user в websocket_manager
        logger.debug(f"Уведомление для пользователя {user_id}: {notification_type}")
    
    return True


@broker.task
async def send_model_update_task(
    model_type: str,
    action: str,
    model_id: str,
    data: Dict[str, Any] = None,
) -> bool:
    """
    Уведомление об изменении модели (для обновления UI).
    
    Args:
        model_type: Тип модели (agent, flow, tool и т.д.)
        action: Действие (created, updated, deleted)
        model_id: ID модели
        data: Дополнительные данные
    
    Returns:
        True если уведомление отправлено
    """
    from apps.frontend.core.websocket_manager import websocket_manager
    
    notification = {
        "type": "MODEL_UPDATE",
        "data": {
            "model_type": model_type,
            "action": action,
            "model_id": model_id,
            "data": data or {},
        },
    }
    
    await websocket_manager.send_to_all(notification, "updates")
    logger.debug(f"Model update: {model_type}/{action}/{model_id}")
    
    return True

