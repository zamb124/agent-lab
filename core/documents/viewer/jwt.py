"""JWT для viewer-stream и viewer-save (не OnlyOffice)."""

from __future__ import annotations

import time

from core.clients.onlyoffice import (
    OnlyOfficeJwtError,
    sign_onlyoffice_jwt_hs256,
    verify_onlyoffice_jwt_hs256,
)
from core.documents.viewer.models import (
    DocumentViewerHandlerId,
    OfficeViewerBindingKind,
    OfficeViewerSaveTokenClaims,
    OfficeViewerStreamTokenClaims,
)
from core.types import require_json_object


def encode_viewer_stream_token(
    *,
    handler: DocumentViewerHandlerId,
    binding_kind: OfficeViewerBindingKind,
    binding_id: str,
    file_id: str,
    company_id: str,
    content_type: str,
    secret: str,
    ttl_seconds: int,
    edit_mode: bool = False,
    public_link_token_hash: str | None = None,
) -> str:
    now = int(time.time())
    payload = require_json_object(
        OfficeViewerStreamTokenClaims(
            typ="office_view",
            handler=handler,
            binding_kind=binding_kind,
            binding_id=binding_id,
            file_id=file_id,
            company_id=company_id,
            content_type=content_type,
            edit_mode=edit_mode,
            public_link_token_hash=public_link_token_hash,
            iat=now,
            exp=now + ttl_seconds,
        ).model_dump(mode="json"),
        "office_view payload",
    )
    return sign_onlyoffice_jwt_hs256(payload, secret)


def decode_viewer_stream_token(token: str, secret: str) -> OfficeViewerStreamTokenClaims:
    data = verify_onlyoffice_jwt_hs256(token, secret)
    try:
        return OfficeViewerStreamTokenClaims.model_validate(data)
    except ValueError as exc:
        raise OnlyOfficeJwtError("Некорректный viewer stream token") from exc


def encode_viewer_save_token(
    *,
    binding_kind: OfficeViewerBindingKind,
    binding_id: str,
    file_id: str,
    company_id: str,
    secret: str,
    ttl_seconds: int,
    public_link_token_hash: str | None = None,
) -> str:
    now = int(time.time())
    payload = require_json_object(
        OfficeViewerSaveTokenClaims(
            typ="office_view_save",
            binding_kind=binding_kind,
            binding_id=binding_id,
            file_id=file_id,
            company_id=company_id,
            public_link_token_hash=public_link_token_hash,
            iat=now,
            exp=now + ttl_seconds,
        ).model_dump(mode="json"),
        "office_view_save payload",
    )
    return sign_onlyoffice_jwt_hs256(payload, secret)


def decode_viewer_save_token(token: str, secret: str) -> OfficeViewerSaveTokenClaims:
    data = verify_onlyoffice_jwt_hs256(token, secret)
    try:
        return OfficeViewerSaveTokenClaims.model_validate(data)
    except ValueError as exc:
        raise OnlyOfficeJwtError("Некорректный viewer save token") from exc
