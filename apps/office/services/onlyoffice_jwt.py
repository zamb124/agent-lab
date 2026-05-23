"""
JWT для OnlyOffice Document Server (конфиг редактора и служебные токены скачивания).
"""

from __future__ import annotations

import time
from typing import Any

import jwt


def encode_editor_config(config: dict[str, Any], secret: str) -> str:
    """Подпись полного объекта конфигурации редактора (как ожидает OnlyOffice)."""
    if not secret.strip():
        raise ValueError("jwt_secret пуст")
    return jwt.encode(config, secret, algorithm="HS256")


def encode_download_token(
    *,
    file_id: str,
    company_id: str,
    binding_id: str,
    binding_kind: str = "document",
    secret: str,
    ttl_seconds: int,
) -> str:
    if binding_kind not in {"document", "file"}:
        raise ValueError("binding_kind должен быть document или file")
    now = int(time.time())
    payload = {
        "typ": "office_dl",
        "binding_kind": binding_kind,
        "file_id": file_id,
        "company_id": company_id,
        "binding_id": binding_id,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_download_token(token: str, secret: str) -> dict[str, Any]:
    data = jwt.decode(token, secret, algorithms=["HS256"])
    if data.get("typ") != "office_dl":
        raise jwt.InvalidTokenError("Неверный тип токена")
    binding_kind = data.get("binding_kind") or "document"
    if binding_kind not in {"document", "file"}:
        raise jwt.InvalidTokenError("Неверный binding_kind токена")
    if not data.get("binding_id") or not data.get("file_id") or not data.get("company_id"):
        raise jwt.InvalidTokenError("В токене скачивания не хватает полей")
    return data


def decode_callback_authorization(bearer_token: str, secret: str) -> dict[str, Any]:
    return jwt.decode(bearer_token, secret, algorithms=["HS256"])
