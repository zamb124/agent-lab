"""
Утилиты для работы с авторизацией.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from jose import JWTError, jwt

from core.logging import get_logger

logger = get_logger(__name__)


def get_token_info(
    token: str,
    jwt_secret: str,
    jwt_algorithm: str,
) -> Optional[dict[str, Any]]:
    """Валидирует access token и возвращает хранящуюся в нем информацию"""
    try:
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=[jwt_algorithm],
            options={
                "require": [
                    "id",
                    "exp",
                    "iss",
                    "email",
                    "session_id",
                ]
            },
        )
    except JWTError as e:
        logger.warning(f"Invalid JWT: {e}")
        return None

    # grps - claim из Blitz IDP (AddGroupsToToken flow)
    grps = payload.get("grps", [])
    if not isinstance(grps, list):
        grps = []

    return {
        "id": payload.get("id"),
        "iss": payload.get("iss"),
        "email": payload.get("email"),
        "session_id": payload.get("session_id"),
        "grps": grps,
    }


def generate_access_token(
    user: dict[str, object],
    session_id: str,
    jwt_secret: str,
    jwt_algorithm: str,
    token_exp_minutes: int,
    grps: Optional[list[str]] = None,
) -> str:
    """Генерирует access token"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=token_exp_minutes)
    payload = {
        "id": user["id"],
        "iss": user["iss"],
        "email": user["email"],
        "session_id": session_id,
        "exp": expire,
    }

    if grps:
        payload["grps"] = grps

    token = jwt.encode(payload, jwt_secret, algorithm=jwt_algorithm)

    return token


def hash_token(token: str) -> str:
    """Хеширует токен"""
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    """Хеширует пароль с bcrypt"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def compare_passwords(incoming_password: str, password_hash: Optional[str]) -> bool:
    """Сравнивает входящий пароль и хэш через bcrypt"""
    if not password_hash:
        return False
    return bcrypt.checkpw(incoming_password.encode(), password_hash.encode())


def generate_refresh_token(token_exp_days: int) -> dict[str, Any]:
    """Генерирует refresh token"""
    return {
        "refresh_token": secrets.token_urlsafe(64),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=token_exp_days),
    }


def get_cache_token_key(
    access_token: str,
    cache_key_prefix: str,
) -> str:
    """Возвращает ключ кэша токена"""
    return f"{cache_key_prefix}{hash_token(access_token)}"


def get_cache_session_key(
    user_id: int,
    cache_session_key_prefix: str,
) -> str:
    """Возвращает ключ кэша сессии"""
    return f"{cache_session_key_prefix}{user_id}"


def generate_session_id() -> str:
    """Генерирует ID сессии"""
    return str(uuid.uuid4())
