"""
JWT для OnlyOffice Document Server (конфиг редактора и служебные токены скачивания).
"""

from __future__ import annotations

import time

from apps.office.models.api import OnlyOfficeDownloadTokenClaims
from core.clients.onlyoffice import (
    OnlyOfficeJwtError,
    sign_onlyoffice_jwt_hs256,
    verify_onlyoffice_jwt_hs256,
)
from core.types import JsonObject, require_json_object


def encode_editor_config(config: JsonObject, secret: str) -> str:
    """Подпись полного объекта конфигурации редактора (как ожидает OnlyOffice)."""
    return sign_onlyoffice_jwt_hs256(config, secret)


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
    if binding_kind == "document":
        binding_kind_value = "document"
    else:
        binding_kind_value = "file"
    now = int(time.time())
    payload = require_json_object(
        OnlyOfficeDownloadTokenClaims(
            typ="office_dl",
            binding_kind=binding_kind_value,
            file_id=file_id,
            company_id=company_id,
            binding_id=binding_id,
            iat=now,
            exp=now + ttl_seconds,
        ).model_dump(mode="json"),
        "office_dl payload",
    )
    return sign_onlyoffice_jwt_hs256(payload, secret)


def decode_download_token(token: str, secret: str) -> OnlyOfficeDownloadTokenClaims:
    data = verify_onlyoffice_jwt_hs256(token, secret)
    try:
        return OnlyOfficeDownloadTokenClaims.model_validate(data)
    except ValueError as exc:
        raise OnlyOfficeJwtError("Некорректный токен скачивания") from exc


def decode_callback_authorization(bearer_token: str, secret: str) -> JsonObject:
    return verify_onlyoffice_jwt_hs256(bearer_token, secret)
