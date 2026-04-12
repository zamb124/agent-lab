"""JWT в query callback OnlyOffice: привязка binding_id + company_id."""

from __future__ import annotations

import time
from typing import Any, Dict

import jwt


def encode_callback_context_token(
    *,
    binding_id: str,
    company_id: str,
    namespace: str,
    secret: str,
    ttl_seconds: int,
) -> str:
    now = int(time.time())
    payload: Dict[str, Any] = {
        "typ": "office_cb",
        "binding_id": binding_id,
        "company_id": company_id,
        "namespace": namespace,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_callback_context_token(token: str, secret: str) -> Dict[str, Any]:
    data = jwt.decode(token, secret, algorithms=["HS256"])
    if data.get("typ") != "office_cb":
        raise jwt.InvalidTokenError("Неверный тип callback-токена")
    if not data.get("binding_id") or not data.get("company_id") or not data.get("namespace"):
        raise jwt.InvalidTokenError("В токене callback не хватает полей")
    return data
