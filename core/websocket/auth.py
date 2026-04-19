"""
Авторизация WebSocket-подключений по cookie auth_token.
"""

from typing import Optional

from fastapi import WebSocket

from core.logging import get_logger
from core.models.identity_models import User

logger = get_logger(__name__)


async def get_user_from_websocket(websocket: WebSocket) -> Optional[User]:
    """Извлечь пользователя из cookie auth_token; вернуть None при отсутствии/невалидности."""
    from core.utils.tokens import get_token_service

    auth_token = websocket.cookies.get("auth_token")
    if not auth_token:
        logger.debug("WebSocket: no auth_token cookie")
        return None

    token_service = get_token_service()
    token_data = token_service.validate_token(auth_token)
    if not token_data or not token_data.user_id:
        logger.debug("WebSocket: invalid token")
        return None

    return User(
        user_id=token_data.user_id,
        name=token_data.user_id,
        email="",
        companies={},
        active_company_id=token_data.company_id or "default",
    )
