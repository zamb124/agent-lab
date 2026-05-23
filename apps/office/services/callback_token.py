"""JWT в query callback OnlyOffice: привязка binding_id + company_id."""

from __future__ import annotations

import time
from typing import Any

import jwt


def encode_callback_context_token(
    *,
    binding_id: str,
    company_id: str,
    namespace: str | None = None,
    file_id: str | None = None,
    binding_kind: str = "document",
    secret: str,
    ttl_seconds: int,
) -> str:
    if binding_kind == "document":
        if namespace is None or namespace == "":
            raise ValueError("namespace обязателен для document callback-токена")
    elif binding_kind == "file":
        if file_id is None or file_id == "":
            raise ValueError("file_id обязателен для file callback-токена")
    else:
        raise ValueError("binding_kind должен быть document или file")
    now = int(time.time())
    payload: dict[str, Any] = {
        "typ": "office_cb",
        "binding_kind": binding_kind,
        "binding_id": binding_id,
        "company_id": company_id,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    if namespace is not None:
        payload["namespace"] = namespace
    if file_id is not None:
        payload["file_id"] = file_id
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_callback_context_token(token: str, secret: str) -> dict[str, Any]:
    data = jwt.decode(token, secret, algorithms=["HS256"])
    if data.get("typ") != "office_cb":
        raise jwt.InvalidTokenError("Неверный тип callback-токена")
    binding_kind = data.get("binding_kind") or "document"
    if binding_kind == "document":
        if not data.get("binding_id") or not data.get("company_id") or not data.get("namespace"):
            raise jwt.InvalidTokenError("В document callback-токене не хватает полей")
        return data
    if binding_kind == "file":
        if not data.get("binding_id") or not data.get("company_id") or not data.get("file_id"):
            raise jwt.InvalidTokenError("В file callback-токене не хватает полей")
        return data
    raise jwt.InvalidTokenError("Неверный binding_kind callback-токена")
