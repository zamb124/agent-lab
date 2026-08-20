"""Канон текста согласия на аналитические cookie (152-ФЗ ст. 9)."""

from __future__ import annotations

from typing import Literal

COOKIE_CONSENT_TEXT_VERSION = "2026-08-20.1"
COOKIE_CONSENT_USER_AGENT_MAX_LEN = 512

CookieConsentDecision = Literal["accept_all", "necessary_only", "custom"]
CookieConsentLocale = Literal["ru", "en"]
