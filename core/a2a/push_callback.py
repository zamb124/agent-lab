"""Callback-контракт A2A push: URL внутреннего endpoint'а и bearer-токен.

Токен — случайный секрет на строку `PlatformA2APendingCall`; в Redis живёт
только sha256-хеш. Провод — `TaskPushNotificationConfig.token` A2A 1.0:
доставка (`send_webhook`) выставляет `Authorization: Bearer <token>`.
"""

from __future__ import annotations

import hashlib
import secrets

from core.config import get_settings

A2A_PUSH_INTERNAL_PATH = "internal/a2a/push"

_CALLBACK_TOKEN_BYTES = 32


def a2a_push_callback_url(service: str) -> str:
    """``{service_url}/{service}/api/v1/internal/a2a/push`` — куда слать push."""
    base = get_settings().server.get_service_url(service).rstrip("/")
    return f"{base}/{service}/api/v1/{A2A_PUSH_INTERNAL_PATH}"


def mint_callback_token() -> tuple[str, str]:
    """(token, sha256-hex). Token уходит в push config, хеш — в pending-ряд."""
    token = secrets.token_urlsafe(_CALLBACK_TOKEN_BYTES)
    return token, hash_callback_token(token)


def hash_callback_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


__all__ = [
    "A2A_PUSH_INTERNAL_PATH",
    "a2a_push_callback_url",
    "hash_callback_token",
    "mint_callback_token",
]
