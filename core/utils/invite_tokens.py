"""
Одноразовые инвайт-токены для приглашения пользователей в компанию.

Отдельный тип JWT (typ="invite") — не смешивать с сессионным TokenData.
Одноразовость обеспечивается Redis SET NX по jti.
"""

import uuid
from collections.abc import Awaitable
from datetime import datetime, timedelta, timezone
from typing import Protocol, cast

import jwt
import redis.asyncio as aioredis
from pydantic import BaseModel, Field

from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)
INVITE_TOKEN_TYPE = "invite"
INVITE_TOKEN_AUDIENCE = "invite"
INVITE_EXPIRES_SECONDS = 60 * 60 * 24 * 7  # 7 дней
INVITE_REDIS_KEY_PREFIX = "invite:used:"


class _InviteRedisClient(Protocol):
    def set(
        self,
        name: str,
        value: str,
        *,
        nx: bool,
        ex: int,
    ) -> Awaitable[bool | None]: ...

    def get(self, name: str) -> Awaitable[str | None]: ...

    def aclose(self) -> Awaitable[None]: ...


class _InviteRedisFromUrl(Protocol):
    def __call__(
        self,
        url: str,
        *,
        decode_responses: bool,
        socket_connect_timeout: int,
        socket_timeout: int,
    ) -> _InviteRedisClient: ...


def _invite_redis_client() -> _InviteRedisClient:
    settings = get_settings()
    redis_from_url = cast(_InviteRedisFromUrl, aioredis.from_url)
    return redis_from_url(
        settings.database.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


class InviteTokenData(BaseModel):
    """Данные инвайт-токена"""

    company_id: str = Field(description="ID компании")
    role: str = Field(description="Роль приглашённого в компании")
    invited_by: str = Field(description="user_id инициатора приглашения")
    jti: str = Field(description="Уникальный ID токена (для одноразовости)")
    exp: datetime = Field(description="Время истечения")
    iat: datetime = Field(description="Время создания")
    typ: str = Field(default=INVITE_TOKEN_TYPE)
    aud: str = Field(default=INVITE_TOKEN_AUDIENCE)

class InviteTokenService:
    """Сервис создания и проверки инвайт-токенов"""

    def __init__(self) -> None:
        settings = get_settings()
        secret = settings.auth.jwt_secret_key
        if not secret:
            raise ValueError("JWT secret key не настроен (auth.jwt_secret_key)")
        self._secret: str = secret
        self._algorithm: str = "HS256"

    def create(self, company_id: str, role: str, *, invited_by: str) -> tuple[str, str]:
        """
        Создаёт одноразовый инвайт-токен.

        Возвращает:
            (jwt_string, jti) — строка токена и его уникальный ID
        """
        if invited_by == "":
            raise ValueError("invited_by must be non-empty string")

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=INVITE_EXPIRES_SECONDS)
        jti = str(uuid.uuid4())

        payload = {
            "typ": INVITE_TOKEN_TYPE,
            "aud": INVITE_TOKEN_AUDIENCE,
            "company_id": company_id,
            "role": role,
            "invited_by": invited_by,
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }

        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        logger.info(
            f"Создан инвайт-токен jti={jti} для компании {company_id}, роль={role}, invited_by={invited_by}"
        )
        return token, jti

    def validate(self, token: str) -> InviteTokenData:
        """
        Проверяет подпись и содержимое инвайт-токена.

        Исключения:
            jwt.ExpiredSignatureError: токен истёк
            jwt.InvalidTokenError: неверная подпись или формат
            ValueError: неверный typ/aud или нет invited_by
        """
        payload = jwt.decode(
            token,
            self._secret,
            algorithms=[self._algorithm],
            audience=INVITE_TOKEN_AUDIENCE,
        )
        data = InviteTokenData.model_validate(payload)

        if data.typ != INVITE_TOKEN_TYPE:
            raise ValueError(f"Неверный тип токена: {data.typ!r}")

        if data.invited_by == "":
            raise ValueError("Инвайт-токен без invited_by")

        return data

async def burn_invite_token(jti: str, ttl_seconds: int) -> bool:
    """
    Атомарно «сжигает» инвайт-токен в Redis (SET NX).

    Возвращает:
        True — токен успешно записан (ещё не использовался)
        False — токен уже был использован ранее
    """
    key = f"{INVITE_REDIS_KEY_PREFIX}{jti}"

    client = _invite_redis_client()
    try:
        result = await client.set(key, "1", nx=True, ex=ttl_seconds)
        return result is True
    finally:
        await client.aclose()

async def invite_jti_already_used(jti: str) -> bool:
    """True, если jti отмечен использованным в Redis (одноразовый инвайт израсходован)."""
    key = f"{INVITE_REDIS_KEY_PREFIX}{jti}"
    client = _invite_redis_client()
    try:
        val = await client.get(key)
        return val is not None
    finally:
        await client.aclose()

_invite_token_service: InviteTokenService | None = None

def get_invite_token_service() -> InviteTokenService:
    """Получает глобальный экземпляр сервиса инвайт-токенов"""
    global _invite_token_service
    if _invite_token_service is None:
        _invite_token_service = InviteTokenService()
    return _invite_token_service
