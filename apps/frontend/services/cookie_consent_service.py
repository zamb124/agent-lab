"""Запись согласия на аналитические cookie (152-ФЗ ст. 9)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import assert_never

from fastapi import Request

from apps.frontend.cookie_consent import (
    COOKIE_CONSENT_TEXT_VERSION,
    COOKIE_CONSENT_USER_AGENT_MAX_LEN,
    CookieConsentDecision,
)
from apps.frontend.models import CookieConsentCreateBody, CookieConsentRecord
from core.config.models import PlatformBrandConfig, PublicSiteConfig
from core.errors.boundary import PlatformConflictError
from core.logging.context import get_log_context
from core.utils.domain import extract_base_domain
from core.websocket import WsCommandError


def analytics_configured(marketing: PublicSiteConfig) -> bool:
    ym_id = marketing.yandex_metrika_id
    ga_id = marketing.google_analytics_measurement_id
    ym_on = ym_id is not None and ym_id != ""
    ga_on = ga_id is not None and ga_id != ""
    return ym_on or ga_on


def _require_request_id() -> str:
    raw = get_log_context().get("request_id")
    if not isinstance(raw, str) or raw.strip() == "":
        raise RuntimeError("request_id is required")
    return raw.strip()


def _require_client_ip(request: Request) -> str:
    client = request.client
    if client is None:
        raise WsCommandError(
            "ws_invalid_payload",
            "client address required",
            error_code="client_address_required",
        )
    host = client.host.strip()
    if host == "":
        raise WsCommandError(
            "ws_invalid_payload",
            "client address required",
            error_code="client_address_required",
        )
    return host


def _hash_client_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


def _user_agent(request: Request) -> str:
    header = request.headers.get("user-agent")
    if header is None:
        return ""
    return header[:COOKIE_CONSENT_USER_AGENT_MAX_LEN]


def _validate_decision(
    *,
    decision: CookieConsentDecision,
    analytics_allowed: bool,
    analytics_is_configured: bool,
) -> None:
    if not analytics_is_configured and analytics_allowed:
        raise WsCommandError(
            "ws_invalid_payload",
            "analytics_allowed must be false when analytics is not configured",
            error_code="cookie_analytics_not_configured",
        )
    if decision == "accept_all":
        if analytics_is_configured and not analytics_allowed:
            raise WsCommandError(
                "ws_invalid_payload",
                "accept_all requires analytics_allowed when analytics is configured",
                error_code="cookie_accept_all_requires_analytics",
            )
        return
    if decision == "necessary_only":
        if analytics_allowed:
            raise WsCommandError(
                "ws_invalid_payload",
                "necessary_only requires analytics_allowed=false",
                error_code="cookie_necessary_only_analytics",
            )
        return
    if decision == "custom":
        return
    assert_never(decision)


class CookieConsentService:
    async def record(
        self,
        body: CookieConsentCreateBody,
        *,
        request: Request,
        brand: PlatformBrandConfig,
    ) -> CookieConsentRecord:
        if body.consent_text_version != COOKIE_CONSENT_TEXT_VERSION:
            raise PlatformConflictError(
                "consent_text_version does not match current cookie consent text",
                error_code="cookie_consent_text_stale",
            )
        host_header = request.headers.get("host")
        if host_header is None or host_header.strip() == "":
            raise WsCommandError(
                "ws_invalid_payload",
                "Host header is required",
                error_code="host_header_required",
            )
        brand_host = host_header.strip()
        analytics_is_configured = analytics_configured(brand.public_site)
        _validate_decision(
            decision=body.decision,
            analytics_allowed=body.analytics_allowed,
            analytics_is_configured=analytics_is_configured,
        )
        record = CookieConsentRecord(
            cookie_consent_id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            brand_host=brand_host,
            apex_domain=extract_base_domain(brand_host),
            decision=body.decision,
            analytics_allowed=body.analytics_allowed,
            consent_text_version=body.consent_text_version,
            locale=body.locale,
            request_id=_require_request_id(),
            user_agent=_user_agent(request),
            ip_hash=_hash_client_ip(_require_client_ip(request)),
            supersedes_cookie_consent_id=body.supersedes_cookie_consent_id,
        )
        _ = await CookieConsentRecord.set(record)
        return record
