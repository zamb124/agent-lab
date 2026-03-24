"""Генерация временных TURN credentials по протоколу coturn REST API (HMAC-SHA1)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from core.calls.models import TurnCredentials


def generate_turn_credentials(
    *,
    user_id: str,
    turn_host: str,
    turn_port: int,
    turn_secret: str,
    ttl: int,
) -> TurnCredentials:
    """
    Генерирует временные TURN credentials для пользователя.

    Алгоритм совместим с coturn --use-auth-secret:
    - username = "<expires_timestamp>:<user_id>"
    - credential = base64(HMAC-SHA1(secret, username))
    """
    if not turn_host:
        raise ValueError("turn_host не задан в конфигурации")
    if not turn_secret:
        raise ValueError("turn_secret не задан в конфигурации")

    expires = int(time.time()) + ttl
    username = f"{expires}:{user_id}"

    raw_credential = hmac.new(
        turn_secret.encode("utf-8"),
        username.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    credential = base64.b64encode(raw_credential).decode("utf-8")

    uris = [
        f"stun:{turn_host}:{turn_port}",
        f"turn:{turn_host}:{turn_port}?transport=udp",
        f"turn:{turn_host}:{turn_port}?transport=tcp",
    ]

    return TurnCredentials(
        username=username,
        credential=credential,
        ttl=ttl,
        uris=uris,
    )
