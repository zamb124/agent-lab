"""PhoneChallenge — короткоживущая попытка подтверждения номера в Redis.

Переходное состояние customer-auth живёт только в Redis (TTL обязателен,
персистентность не нужна): подтверждённый результат становится
`CustomerIdentity`/`Customer` в Postgres.
"""

from __future__ import annotations

import time
from uuid import uuid4

from pydantic import Field

from core.clients.redis_client import RedisClient
from core.customers.enums import (
    ClientKind,
    DirectAuthorizationKind,
    PhoneChallengeKind,
    PhoneChallengeStatus,
    PhoneVerificationChannel,
    PhoneVerificationMethod,
)
from core.models.base import StrictBaseModel

_KEY_PREFIX = "cust_auth:ch:"


def _key(challenge_id: str) -> str:
    return f"{_KEY_PREFIX}{challenge_id}"


class ContactShareState(StrictBaseModel):
    """Ожидание контакта после deep_link в бота (polling `auth/status`)."""

    bot_link: str
    token: str


class PhoneChallenge(StrictBaseModel):
    """Одна попытка подтверждения номера."""

    challenge_id: str = Field(default_factory=lambda: f"phc_{uuid4().hex}")
    scope_company_id: str
    phone_e164: str
    status: PhoneChallengeStatus = PhoneChallengeStatus.PENDING
    kind: PhoneChallengeKind | None = None
    method: PhoneVerificationMethod | None = None
    channel: PhoneVerificationChannel | None = None
    client: ClientKind = ClientKind.MOBILE_WEB
    code_hash: str | None = None
    attempts_left: int = 5
    resend_after_ts: int = 0
    direct_kind: DirectAuthorizationKind | None = None
    oauth_state: str | None = None  # nonce для OAuth-колбэка
    contact_share: ContactShareState | None = None
    selected_methods: list[str] = Field(default_factory=list)
    flow_hint: str = "checkout"
    created_ts: int = Field(default_factory=lambda: int(time.time()))
    updated_ts: int = Field(default_factory=lambda: int(time.time()))
    confirmed_customer_id: str | None = None
    error_code: str | None = None
    provider_data: dict[str, str] = Field(default_factory=dict)

    async def save(self, redis: RedisClient, *, ttl: int) -> None:
        self.updated_ts = int(time.time())
        _ = await redis.set(_key(self.challenge_id), self.model_dump_json(), ttl=ttl)

    @classmethod
    async def load(cls, redis: RedisClient, challenge_id: str) -> "PhoneChallenge | None":
        raw = await redis.get(_key(challenge_id))
        if raw is None:
            return None
        return cls.model_validate_json(raw)

    async def delete(self, redis: RedisClient) -> None:
        _ = await redis.delete(_key(self.challenge_id))
