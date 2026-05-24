"""
Утилиты для работы с авторизацией.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import TypedDict

import bcrypt
from jose import JWTError, jwt

from core.logging import get_logger
from core.types import JsonObject, JsonValue, require_json_object

logger = get_logger(__name__)


class RefreshTokenData(TypedDict):
    refresh_token: str
    expires_at: datetime


def _string_claim_list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def get_token_info(
    token: str,
    jwt_secret: str,
    jwt_algorithm: str,
) -> JsonObject | None:
    """Валидирует access token и возвращает хранящуюся в нем информацию"""
    try:
        decoded_payload: object = jwt.decode(
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

    try:
        payload = require_json_object(decoded_payload, "jwt.payload")
    except ValueError as e:
        logger.warning(f"Invalid JWT payload: {e}")
        return None

    user_id = payload.get("id")
    issuer = payload.get("iss")
    email = payload.get("email")
    session_id = payload.get("session_id")
    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, (str, int))
        or not isinstance(issuer, str)
        or not isinstance(email, str)
        or not isinstance(session_id, str)
    ):
        logger.warning("Invalid JWT payload claims")
        return None

    # grps - claim из Blitz IDP (AddGroupsToToken flow)
    grps = _string_claim_list(payload.get("grps"))

    return {
        "id": user_id,
        "iss": issuer,
        "email": email,
        "session_id": session_id,
        "grps": grps,
    }


def generate_access_token(
    user: dict[str, object],
    session_id: str,
    jwt_secret: str,
    jwt_algorithm: str,
    token_exp_minutes: int,
    grps: list[str] | None = None,
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


def compare_passwords(incoming_password: str, password_hash: str | None) -> bool:
    """Сравнивает входящий пароль и хэш через bcrypt"""
    if not password_hash:
        return False
    return bcrypt.checkpw(incoming_password.encode(), password_hash.encode())


def generate_refresh_token(token_exp_days: int) -> RefreshTokenData:
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
