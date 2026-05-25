"""JWT в query callback OnlyOffice: привязка binding_id + company_id."""

from __future__ import annotations

import time

from apps.office.models.api import OnlyOfficeCallbackContextClaims
from core.clients.onlyoffice import (
    OnlyOfficeJwtError,
    sign_onlyoffice_jwt_hs256,
    verify_onlyoffice_jwt_hs256,
)
from core.types import require_json_object


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
    if binding_kind == "document":
        binding_kind_value = "document"
    else:
        binding_kind_value = "file"
    now = int(time.time())
    payload = require_json_object(
        OnlyOfficeCallbackContextClaims(
            typ="office_cb",
            binding_kind=binding_kind_value,
            binding_id=binding_id,
            company_id=company_id,
            iat=now,
            exp=now + ttl_seconds,
            namespace=namespace,
            file_id=file_id,
        ).model_dump(mode="json", exclude_none=True),
        "office_cb payload",
    )
    return sign_onlyoffice_jwt_hs256(payload, secret)


def decode_callback_context_token(token: str, secret: str) -> OnlyOfficeCallbackContextClaims:
    data = verify_onlyoffice_jwt_hs256(token, secret)
    try:
        return OnlyOfficeCallbackContextClaims.model_validate(data)
    except ValueError as exc:
        raise OnlyOfficeJwtError("Некорректный callback-токен") from exc
