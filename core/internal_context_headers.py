"""Signed platform context headers for trusted service-to-service calls."""

from __future__ import annotations

import hmac
import time
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256

from core.config import get_settings

HEADER_COMPANY_ID = "X-Platform-Context-Company-Id"
HEADER_USER_ID = "X-Platform-Context-User-Id"
HEADER_ISSUED_AT = "X-Platform-Context-Iat"
HEADER_SIGNATURE = "X-Platform-Context-Signature"

_TTL_SECONDS = 300


@dataclass(frozen=True, slots=True)
class InternalContextHeaders:
    company_id: str
    user_id: str
    issued_at: int


def _secret() -> str:
    auth = get_settings().auth
    secret = auth.jwt_secret_key or auth.secret_key
    if secret is None or not secret.strip():
        raise ValueError("auth.jwt_secret_key or auth.secret_key is required for internal context headers")
    return secret


def _message(company_id: str, user_id: str, issued_at: int) -> bytes:
    return f"{issued_at}.{company_id}.{user_id}".encode("utf-8")


def _signature(company_id: str, user_id: str, issued_at: int) -> str:
    return hmac.new(_secret().encode("utf-8"), _message(company_id, user_id, issued_at), sha256).hexdigest()


def build_internal_context_headers(*, company_id: str, user_id: str) -> dict[str, str]:
    cid = company_id.strip()
    uid = user_id.strip()
    if not cid:
        raise ValueError("company_id is required for internal context headers")
    if not uid:
        raise ValueError("user_id is required for internal context headers")
    issued_at = int(time.time())
    return {
        HEADER_COMPANY_ID: cid,
        HEADER_USER_ID: uid,
        HEADER_ISSUED_AT: str(issued_at),
        HEADER_SIGNATURE: _signature(cid, uid, issued_at),
    }


def parse_internal_context_headers(headers: Mapping[str, str]) -> InternalContextHeaders | None:
    company_id = (headers.get(HEADER_COMPANY_ID) or "").strip()
    user_id = (headers.get(HEADER_USER_ID) or "").strip()
    issued_at_raw = (headers.get(HEADER_ISSUED_AT) or "").strip()
    signature = (headers.get(HEADER_SIGNATURE) or "").strip()
    present_count = sum(1 for value in (company_id, user_id, issued_at_raw, signature) if value)
    if present_count == 0:
        return None
    if present_count != 4:
        raise ValueError("Incomplete internal context headers")
    try:
        issued_at = int(issued_at_raw)
    except ValueError as exc:
        raise ValueError("Invalid internal context header timestamp") from exc
    now = int(time.time())
    if issued_at < now - _TTL_SECONDS or issued_at > now + 30:
        raise ValueError("Expired internal context headers")
    expected = _signature(company_id, user_id, issued_at)
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid internal context header signature")
    return InternalContextHeaders(company_id=company_id, user_id=user_id, issued_at=issued_at)
