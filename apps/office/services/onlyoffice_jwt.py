"""
JWT для OnlyOffice Document Server (конфиг редактора и служебные токены скачивания).
"""

from __future__ import annotations

import time
from typing import Any, Dict

import jwt


def encode_editor_config(config: Dict[str, Any], secret: str) -> str:
    """Подпись полного объекта конфигурации редактора (как ожидает OnlyOffice)."""
    if not secret.strip():
        raise ValueError("jwt_secret пуст")
    return jwt.encode(config, secret, algorithm="HS256")


def encode_download_token(
    *,
    file_id: str,
    company_id: str,
    binding_id: str,
    secret: str,
    ttl_seconds: int,
) -> str:
    now = int(time.time())
    payload = {
        "typ": "office_dl",
        "file_id": file_id,
        "company_id": company_id,
        "binding_id": binding_id,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_download_token(token: str, secret: str) -> Dict[str, Any]:
    data = jwt.decode(token, secret, algorithms=["HS256"])
    if data.get("typ") != "office_dl":
        raise jwt.InvalidTokenError("Неверный тип токена")
    if not data.get("binding_id"):
        raise jwt.InvalidTokenError("В токене скачивания нет binding_id")
    return data


def decode_callback_authorization(bearer_token: str, secret: str) -> Dict[str, Any]:
    return jwt.decode(bearer_token, secret, algorithms=["HS256"])
