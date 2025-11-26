"""
WebSocket для уведомлений - использует универсальный менеджер
"""

from apps.frontend.core.websocket_manager import (
    router,
    notify_model_updated
)

# Re-export для обратной совместимости
__all__ = ["router", "notify_model_updated"]

