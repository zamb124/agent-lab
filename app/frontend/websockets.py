"""
Frontend WebSockets роутер - объединяет все websocket суброутеры
"""

from fastapi import APIRouter

# Импорт всех websocket суброутеров
from app.frontend.websockets import (
    notifications as websocket_notifications,
    chat as websocket_chat
)
from app.frontend.api import websocket_status as websocket_status_api

# Создание главного websockets роутера
router = APIRouter(tags=["websockets"])

# Включение суброутеров
router.include_router(websocket_notifications.router, tags=["websocket-notifications"], include_in_schema=False)
router.include_router(websocket_chat.router, prefix="/chat", tags=["websocket-chat"], include_in_schema=False)
router.include_router(websocket_status_api.router, tags=["websocket-status"], include_in_schema=False)
