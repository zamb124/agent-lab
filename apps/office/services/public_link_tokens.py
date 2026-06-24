"""Генерация raw token и hash для публичных ссылок catalog/binding."""

from __future__ import annotations

import hashlib
import secrets


def create_share_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return token, token_hash
