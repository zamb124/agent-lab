"""Cooldown JSON, классификация ошибок провайдера и Redis roundtrip."""

from __future__ import annotations

import json

import httpx2
import pytest
from pydantic import ValidationError

from core.ai.llm_config import LLMCallConfig
from core.ai.provider_error import (
    ERROR_TEXT_MAX_CHARS,
    AIProviderErrorClass,
    classify_ai_provider_error,
    classify_ai_provider_http,
)
from core.clients.llm.candidate_cooldown import (
    candidate_cooldown_state_map,
    cooldown_redis_key,
    parse_candidate_cooldown_payload,
    set_candidate_cooldown,
)
from core.clients.llm.candidates import candidate_key
from core.clients.llm.errors import LLMStreamIdleTimeoutError
from core.clients.redis_client import RedisClient
from core.config import get_settings


def _http_status_error(status: int, body: str) -> httpx2.HTTPStatusError:
    request = httpx2.Request("POST", "https://example.test/v1/chat/completions")
    response = httpx2.Response(status, text=body, request=request)
    return httpx2.HTTPStatusError(f"HTTP {status}", request=request, response=response)


def _candidate(unique_id: str) -> LLMCallConfig:
    return LLMCallConfig(
        provider="openrouter",
        model=f"cooldown-json-{unique_id}",
        api_key=f"key-{unique_id}",
        base_url="https://openrouter.ai/api/v1",
    )


def test_classify_429_is_rate_limited() -> None:
    record = classify_ai_provider_error("openrouter", _http_status_error(429, "too many"))
    assert record.error_class == AIProviderErrorClass.RATE_LIMITED
    assert record.http_status == 429
    assert "too many" in record.error_text


def test_classify_402_and_billing_text_is_payment_required() -> None:
    by_status = classify_ai_provider_error("groq", _http_status_error(402, "pay up"))
    assert by_status.error_class == AIProviderErrorClass.PAYMENT_REQUIRED
    by_text = classify_ai_provider_error(
        "openrouter",
        _http_status_error(400, "Balance is below zero"),
    )
    assert by_text.error_class == AIProviderErrorClass.PAYMENT_REQUIRED


def test_classify_content_filter() -> None:
    record = classify_ai_provider_error(
        "openai",
        _http_status_error(400, "content_filter: ResponsibleAIPolicyViolation"),
    )
    assert record.error_class == AIProviderErrorClass.CONTENT_FILTER
    assert (
        classify_ai_provider_http("openai", 400, "ResponsibleAIPolicyViolation")
        == AIProviderErrorClass.CONTENT_FILTER
    )


def test_classify_timeout_classes() -> None:
    timeout = classify_ai_provider_error("groq", TimeoutError("deadline"))
    assert timeout.error_class == AIProviderErrorClass.TIMEOUT
    idle = classify_ai_provider_error("groq", LLMStreamIdleTimeoutError(1.5, 0))
    assert idle.error_class == AIProviderErrorClass.TIMEOUT
    assert isinstance(LLMStreamIdleTimeoutError(1.5, 0), TimeoutError)
    httpx_timeout = classify_ai_provider_error("groq", httpx2.TimeoutException("idle"))
    assert httpx_timeout.error_class == AIProviderErrorClass.TIMEOUT


def test_classify_openrouter_missing_auth_header_is_rate_limited() -> None:
    record = classify_ai_provider_error(
        "openrouter",
        _http_status_error(401, "Missing Authentication header"),
    )
    assert record.error_class == AIProviderErrorClass.RATE_LIMITED


def test_classify_redacts_api_key_and_truncates() -> None:
    secret = "sk-live-secret-value"
    long_body = "x" * (ERROR_TEXT_MAX_CHARS + 40)
    record = classify_ai_provider_error(
        "openrouter",
        _http_status_error(500, f"{secret} {long_body}"),
        api_key=secret,
    )
    assert secret not in record.error_text
    assert record.error_text.endswith("...")
    assert len(record.error_text) <= ERROR_TEXT_MAX_CHARS + 3


def test_parse_legacy_cooldown_value_raises() -> None:
    with pytest.raises(ValidationError):
        parse_candidate_cooldown_payload("1")


def test_parse_broken_cooldown_json_raises() -> None:
    with pytest.raises(ValidationError):
        parse_candidate_cooldown_payload("{not-json")


@pytest.mark.asyncio
async def test_candidate_cooldown_json_roundtrip(unique_id: str) -> None:
    candidate = _candidate(unique_id)
    redis = RedisClient(get_settings().database.redis_url)
    try:
        await set_candidate_cooldown(
            candidate,
            35,
            error=_http_status_error(429, "slow down"),
        )
        states = await candidate_cooldown_state_map([candidate])
        state = states[candidate_key(candidate)]
        assert state.record.error_class == AIProviderErrorClass.RATE_LIMITED
        assert state.record.http_status == 429
        assert "slow down" in state.record.error_text
        assert state.ttl_seconds > 0
        raw = await redis.get(cooldown_redis_key(candidate))
        assert raw is not None
        payload = json.loads(raw)
        assert payload["error_class"] == "rate_limited"
        assert payload["http_status"] == 429
    finally:
        _ = await redis.delete(cooldown_redis_key(candidate))


@pytest.mark.asyncio
async def test_candidate_cooldown_legacy_redis_value_raises(unique_id: str) -> None:
    candidate = _candidate(f"legacy-{unique_id}")
    redis = RedisClient(get_settings().database.redis_url)
    key = cooldown_redis_key(candidate)
    try:
        wrote = await redis.set(key, "1", ttl=20)
        assert wrote is True
        with pytest.raises(ValidationError):
            await candidate_cooldown_state_map([candidate])
    finally:
        _ = await redis.delete(key)


@pytest.mark.asyncio
async def test_candidate_cooldown_broken_redis_json_raises(unique_id: str) -> None:
    candidate = _candidate(f"broken-{unique_id}")
    redis = RedisClient(get_settings().database.redis_url)
    key = cooldown_redis_key(candidate)
    try:
        wrote = await redis.set(key, "{broken", ttl=20)
        assert wrote is True
        with pytest.raises(ValidationError):
            await candidate_cooldown_state_map([candidate])
    finally:
        _ = await redis.delete(key)
