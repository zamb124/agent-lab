"""Запись согласия на аналитические cookie (152-ФЗ ст. 9)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import assert_never

from fastapi import HTTPException, Request

from apps.frontend.cookie_consent import (
    COOKIE_CONSENT_TEXT_VERSION,
    COOKIE_CONSENT_USER_AGENT_MAX_LEN,
    CookieConsentDecision,
)
from apps.frontend.models import CookieConsentCreateBody, CookieConsentRecord
from apps.frontend.services.cookie_consent_repository import CookieConsentRepository
from core.config.models import PlatformBrandConfig, PublicSiteConfig
from core.logging.context import get_log_context
from core.utils.domain import extract_base_domain


def analytics_configured(marketing: PublicSiteConfig) -> bool:
    ym_id = marketing.yandex_metrika_id
    ga_id = marketing.google_analytics_measurement_id
    ym_on = ym_id is not None and ym_id != ""
    ga_on = ga_id is not None and ga_id != ""
    return ym_on or ga_on


def _require_request_id() -> str:
    raw = get_log_context().get("request_id")
    if not isinstance(raw, str) or raw.strip() == "":
        raise HTTPException(status_code=500, detail="request_id is required")
    return raw.strip()


def _require_client_ip(request: Request) -> str:
    client = request.client
    if client is None:
        raise HTTPException(status_code=400, detail="client address required")
    host = client.host.strip()
    if host == "":
        raise HTTPException(status_code=400, detail="client address required")
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
        raise HTTPException(
            status_code=422,
            detail="analytics_allowed must be false when analytics is not configured",
        )
    if decision == "accept_all":
        if analytics_is_configured and not analytics_allowed:
            raise HTTPException(
                status_code=422,
                detail="accept_all requires analytics_allowed when analytics is configured",
            )
        return
    if decision == "necessary_only":
        if analytics_allowed:
            raise HTTPException(
                status_code=422,
                detail="necessary_only requires analytics_allowed=false",
            )
        return
    if decision == "custom":
        return
    assert_never(decision)


class CookieConsentService:
    def __init__(self, repository: CookieConsentRepository) -> None:
        self._repository: CookieConsentRepository = repository

    async def record(
        self,
        body: CookieConsentCreateBody,
        *,
        request: Request,
        brand: PlatformBrandConfig,
    ) -> CookieConsentRecord:
        if body.consent_text_version != COOKIE_CONSENT_TEXT_VERSION:
            raise HTTPException(
                status_code=409,
                detail="consent_text_version does not match current cookie consent text",
            )
        host_header = request.headers.get("host")
        if host_header is None or host_header.strip() == "":
            raise HTTPException(status_code=400, detail="Host header is required")
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
        return await self._repository.create(record)
