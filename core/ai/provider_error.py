"""Единая классификация ошибок AI-провайдера.

HTTP-таблица, маркеры billing/content-filter и IO-кортеж живут только здесь.
Cooldown, Settings, live-пробы и agent читают ``AIProviderErrorClass``, не дублируют правила.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import StrEnum

import httpx2

from core.models import StrictBaseModel

ERROR_TEXT_MAX_CHARS = 180

BILLING_ERROR_MARKERS: tuple[str, ...] = (
    "Balance is below zero",
    "NOT_ENOUGH_TOKENS",
    "Insufficient balance",
    "Please recharge",
    "PAYMENT_METHOD_REQUIRED",
    "payment_required",
    "Payment required",
    "no resource package",
)

CONTENT_FILTER_MARKERS: tuple[str, ...] = (
    "content_filter",
    "ResponsibleAIPolicyViolation",
)

AUTH_HTTP_STATUSES: tuple[int, ...] = (401, 403)
TRANSIENT_HTTP_STATUSES: tuple[int, ...] = (500, 502, 503, 504)
PAYMENT_HTTP_STATUS = 402
RATE_LIMIT_HTTP_STATUS = 429
OPENROUTER_POST_ROUTE_RATE_LIMIT_MARKER = "Missing Authentication header"

AI_PROVIDER_IO_ERRORS: tuple[type[BaseException], ...] = (
    TimeoutError,
    OSError,
    ValueError,
    json.JSONDecodeError,
    httpx2.HTTPError,
)


class AIProviderErrorClass(StrEnum):
    RATE_LIMITED = "rate_limited"
    PAYMENT_REQUIRED = "payment_required"
    AUTH_REJECTED = "auth_rejected"
    TIMEOUT = "timeout"
    TRANSIENT = "transient"
    HTTP_ERROR = "http_error"
    TRANSPORT = "transport"
    CONTENT_FILTER = "content_filter"
    UNSPECIFIED = "unspecified"


class AIProviderErrorRecord(StrictBaseModel):
    error_class: AIProviderErrorClass
    http_status: int | None
    error_text: str
    set_at: datetime


def truncate_llm_provider_error_text(detail: str) -> str:
    stripped = " ".join(detail.split())
    if len(stripped) <= ERROR_TEXT_MAX_CHARS:
        return stripped
    return f"{stripped[:ERROR_TEXT_MAX_CHARS]}..."


def redact_secret_from_text(detail: str, secret: str | None) -> str:
    if secret is None or secret == "" or secret not in detail:
        return detail
    return detail.replace(secret, "***")


def response_is_billing_error(response_text: str) -> bool:
    return any(marker in response_text for marker in BILLING_ERROR_MARKERS)


def response_is_content_filter(response_text: str) -> bool:
    return any(marker in response_text for marker in CONTENT_FILTER_MARKERS)


def classify_ai_provider_http(
    provider: str,
    status_code: int,
    response_text: str,
) -> AIProviderErrorClass:
    if response_is_billing_error(response_text) or status_code == PAYMENT_HTTP_STATUS:
        return AIProviderErrorClass.PAYMENT_REQUIRED
    if status_code == RATE_LIMIT_HTTP_STATUS:
        return AIProviderErrorClass.RATE_LIMITED
    if (
        provider == "openrouter"
        and status_code == 401
        and OPENROUTER_POST_ROUTE_RATE_LIMIT_MARKER in response_text
    ):
        return AIProviderErrorClass.RATE_LIMITED
    if status_code in AUTH_HTTP_STATUSES:
        return AIProviderErrorClass.AUTH_REJECTED
    if status_code in TRANSIENT_HTTP_STATUSES:
        return AIProviderErrorClass.TRANSIENT
    if status_code == 400 and response_is_content_filter(response_text):
        return AIProviderErrorClass.CONTENT_FILTER
    return AIProviderErrorClass.HTTP_ERROR


def _http_error_text(exc: httpx2.HTTPStatusError) -> str:
    return truncate_llm_provider_error_text(
        f"HTTP {exc.response.status_code}: {exc.response.text}"
    )


def classify_ai_provider_error(
    provider: str,
    error: BaseException | None,
    *,
    api_key: str | None = None,
) -> AIProviderErrorRecord:
    set_at = datetime.now(timezone.utc)
    if error is None:
        return AIProviderErrorRecord(
            error_class=AIProviderErrorClass.UNSPECIFIED,
            http_status=None,
            error_text="",
            set_at=set_at,
        )
    if isinstance(error, httpx2.HTTPStatusError):
        error_class = classify_ai_provider_http(
            provider,
            error.response.status_code,
            error.response.text,
        )
        return AIProviderErrorRecord(
            error_class=error_class,
            http_status=error.response.status_code,
            error_text=redact_secret_from_text(_http_error_text(error), api_key),
            set_at=set_at,
        )
    if isinstance(error, (TimeoutError, httpx2.TimeoutException)):
        return AIProviderErrorRecord(
            error_class=AIProviderErrorClass.TIMEOUT,
            http_status=None,
            error_text=redact_secret_from_text(
                truncate_llm_provider_error_text(str(error)),
                api_key,
            ),
            set_at=set_at,
        )
    if isinstance(error, (httpx2.HTTPError, OSError)):
        return AIProviderErrorRecord(
            error_class=AIProviderErrorClass.TRANSPORT,
            http_status=None,
            error_text=redact_secret_from_text(
                truncate_llm_provider_error_text(f"{type(error).__name__}: {error}"),
                api_key,
            ),
            set_at=set_at,
        )
    if isinstance(error, (json.JSONDecodeError, ValueError)):
        return AIProviderErrorRecord(
            error_class=AIProviderErrorClass.HTTP_ERROR,
            http_status=None,
            error_text=redact_secret_from_text(
                truncate_llm_provider_error_text(f"{type(error).__name__}: {error}"),
                api_key,
            ),
            set_at=set_at,
        )
    return AIProviderErrorRecord(
        error_class=AIProviderErrorClass.UNSPECIFIED,
        http_status=None,
        error_text=redact_secret_from_text(
            truncate_llm_provider_error_text(f"{type(error).__name__}: {error}"),
            api_key,
        ),
        set_at=set_at,
    )


__all__ = [
    "AI_PROVIDER_IO_ERRORS",
    "AIProviderErrorClass",
    "AIProviderErrorRecord",
    "AUTH_HTTP_STATUSES",
    "BILLING_ERROR_MARKERS",
    "CONTENT_FILTER_MARKERS",
    "ERROR_TEXT_MAX_CHARS",
    "OPENROUTER_POST_ROUTE_RATE_LIMIT_MARKER",
    "PAYMENT_HTTP_STATUS",
    "RATE_LIMIT_HTTP_STATUS",
    "TRANSIENT_HTTP_STATUSES",
    "classify_ai_provider_error",
    "classify_ai_provider_http",
    "redact_secret_from_text",
    "response_is_billing_error",
    "response_is_content_filter",
    "truncate_llm_provider_error_text",
]
