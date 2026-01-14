"""
WebSocket роутер для уведомлений платформы.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.websocket.manager import notification_manager
from core.websocket.auth import get_user_from_websocket
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.websocket("/ws/notifications")
async def notifications_endpoint(websocket: WebSocket):
    """Единый WebSocket endpoint для всех уведомлений платформы"""
    await websocket.accept()

    user = await get_user_from_websocket(websocket)
    if not user or not user.user_id:
        await websocket.close(code=1008, reason="Authentication required")
        logger.warning("WS подключение отклонено: требуется авторизация")
        return

    user_id = user.user_id
    await notification_manager.connect(websocket, user_id)

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.debug(f"WS отключение (нормальное): user={user_id}")
    except Exception as e:
        logger.error(f"WS ошибка: user={user_id}, error={e}", exc_info=True)
    finally:
        await notification_manager.disconnect(websocket, user_id)


@router.get("/ws/stats")
async def websocket_stats():
    """Статистика WebSocket подключений"""
    return notification_manager.get_stats()

