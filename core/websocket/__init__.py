"""
WebSocket менеджер для всех сервисов.
"""

from core.websocket.manager import (
    websocket_manager,
    WebSocketManager,
    ConnectionType,
    REDIS_CHANNEL,
    router,
    notify_model_updated,
)

__all__ = [
    "websocket_manager",
    "WebSocketManager",
    "ConnectionType",
    "REDIS_CHANNEL",
    "router",
    "notify_model_updated",
]

