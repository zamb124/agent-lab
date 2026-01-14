"""
Авторизация для WebSocket подключений.

Использует ту же логику что и AuthMiddleware для HTTP запросов.
"""

from typing import Optional
from fastapi import WebSocket

from core.models.identity_models import User
from core.logging import get_logger

logger = get_logger(__name__)


async def get_user_from_websocket(websocket: WebSocket) -> Optional[User]:
    """
    Извлекает пользователя из WebSocket подключения через cookies.
    
    Использует ту же логику что и AuthMiddleware._extract_token() + _get_user()
    
    Args:
        websocket: WebSocket подключение
        
    Returns:
        User если авторизован, None если нет
    """
    from core.utils.tokens import get_token_service
    
    try:
        # Извлекаем auth_token из cookies (как в AuthMiddleware._extract_token)
        auth_token = websocket.cookies.get("auth_token")
        if not auth_token:
            logger.debug("WebSocket: нет auth_token cookie")
            return None
        
        # Валидируем токен
        token_service = get_token_service()
        token_data = token_service.validate_token(auth_token)
        if not token_data or not token_data.user_id:
            logger.debug("WebSocket: невалидный токен")
            return None
        
        # Для WebSocket достаточно user_id для группировки соединений
        # Создаем минимальный User объект
        user = User(
            user_id=token_data.user_id,
            name=token_data.user_id,
            email="",
            companies={},
            active_company_id=token_data.company_id or "default"
        )
        
        return user
            
    except Exception as e:
        logger.warning(f"Ошибка извлечения user из WebSocket cookies: {e}")
    
    return None

