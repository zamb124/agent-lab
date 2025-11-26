"""
Frontend WebSockets роутер - объединяет все websocket суброутеры
"""

from fastapi import APIRouter

# Импорт websocket суброутеров (кроме notifications, который подключается напрямую)
import apps.frontend.websockets.chat as websocket_chat
import apps.frontend.api.websocket_status as websocket_status_api

# Создание главного websockets роутера
router = APIRouter(tags=["websockets"])

# Включение суброутеров
router.include_router(websocket_chat.router, prefix="/chat", tags=["websocket-chat"], include_in_schema=False)
router.include_router(websocket_status_api.router, tags=["websocket-status"], include_in_schema=False)
