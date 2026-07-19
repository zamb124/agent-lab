"""JWT в query callback OnlyOffice: file_id + company_id + viewer_scope."""

from __future__ import annotations

import time
from typing import Literal

from apps.office.models.api import OnlyOfficeCallbackContextClaims
from core.clients.onlyoffice import (
    OnlyOfficeJwtError,
    sign_onlyoffice_jwt_hs256,
    verify_onlyoffice_jwt_hs256,
)
from core.types import require_json_object


def encode_callback_context_token(
    *,
    file_id: str,
    company_id: str,
    viewer_scope: Literal["catalog", "file"] = "catalog",
    namespace: str | None = None,
    secret: str,
    ttl_seconds: int,
) -> str:
    if viewer_scope == "catalog" and (namespace is None or namespace == ""):
        raise ValueError("namespace обязателен для catalog callback-токена")
    now = int(time.time())
    payload = require_json_object(
        OnlyOfficeCallbackContextClaims(
            typ="office_cb",
            viewer_scope=viewer_scope,
            file_id=file_id,
            company_id=company_id,
            iat=now,
            exp=now + ttl_seconds,
            namespace=namespace,
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
