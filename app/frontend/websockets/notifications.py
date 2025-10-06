"""
WebSocket для уведомлений - использует универсальный менеджер
"""

from typing import Optional
from app.frontend.core.websocket_manager import (
    websocket_manager, 
    router,
    notify_model_updated
)

# Re-export для обратной совместимости
__all__ = ["router", "notify_model_updated"]

