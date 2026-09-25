"""Сводка live-проверки всех OpenAI-compatible LLM-провайдеров.

Unit-часть фиксирует формат отчёта и правила hard-fail.
Network-тест ходит в реальные API и печатает таблицу: кто отвечает, кто нет.
Прогон валится только если настроенный ключ отвергнут как невалидный (401/403 без billing).
Квота, 429, пустой catalog и smoke без маркера остаются в отчёте.
"""

from __future__ import annotations

import pytest

from core.ai.provider_error import AIProviderErrorClass
from tests.core.clients.live_llm_provider_helpers import (
    LIVE_LLM_PROVIDERS,
    LiveProbePhaseResult,
    ProviderLiveProbe,
    format_provider_live_report,
    live_model_service,
    probe_all_openai_compat_providers,
    provider_live_probe_is_hard_failure,
    provider_live_probe_is_revoked_key,
)


def _probe(
    provider: str,
    *,
    configured: bool,
    catalog: LiveProbePhaseResult,
    chat: LiveProbePhaseResult,
    catalog_model_count: int = 0,
    smoke_model: str | None = None,
    catalog_error_class: AIProviderErrorClass | None = None,
    chat_error_class: AIProviderErrorClass | None = None,
) -> ProviderLiveProbe:
    return ProviderLiveProbe(
        provider=provider,
        configured=configured,
        catalog_result=catalog,
        catalog_detail=catalog.value,
        catalog_model_count=catalog_model_count,
        catalog_error_class=catalog_error_class,
        chat_result=chat,
        chat_detail=chat.value,
        chat_error_class=chat_error_class,
        smoke_model=smoke_model,
    )


def test_provider_live_report_covers_every_openai_compat_slug() -> None:
    probes = tuple(
        _probe(
            provider,
            configured=False,
            catalog=LiveProbePhaseResult.NOT_CONFIGURED,
            chat=LiveProbePhaseResult.NOT_CONFIGURED,
        )
        for provider in LIVE_LLM_PROVIDERS
    )
    report = format_provider_live_report(probes)
    for provider in LIVE_LLM_PROVIDERS:
        assert provider in report
    assert "nvidia" in LIVE_LLM_PROVIDERS
    assert "mistral" in LIVE_LLM_PROVIDERS
    assert "zai" in LIVE_LLM_PROVIDERS
    assert "sambanova" in LIVE_LLM_PROVIDERS
    assert "hard_fail=0" in report


def test_provider_live_probe_hard_failure_rules() -> None:
    not_configured = _probe(
        "openai",
        configured=False,
        catalog=LiveProbePhaseResult.NOT_CONFIGURED,
        chat=LiveProbePhaseResult.NOT_CONFIGURED,
    )
    assert provider_live_probe_is_hard_failure(not_configured) is False

    chat_ok = _probe(
        "mistral",
        configured=True,
        catalog=LiveProbePhaseResult.OK,
        chat=LiveProbePhaseResult.OK,
        catalog_model_count=3,
        smoke_model="mistral-small-latest",
    )
    assert provider_live_probe_is_hard_failure(chat_ok) is False

    rate_limited = _probe(
        "groq",
        configured=True,
        catalog=LiveProbePhaseResult.OK,
        chat=LiveProbePhaseResult.CHAT_FAILED,
        catalog_model_count=1,
        chat_error_class=AIProviderErrorClass.RATE_LIMITED,
    )
    assert provider_live_probe_is_hard_failure(rate_limited) is False

    revoked = _probe(
        "nvidia",
        configured=True,
        catalog=LiveProbePhaseResult.CATALOG_FAILED,
        chat=LiveProbePhaseResult.SKIPPED,
        catalog_error_class=AIProviderErrorClass.AUTH_REJECTED,
    )
    assert provider_live_probe_is_hard_failure(revoked) is True

    catalog_gone = _probe(
        "huggingface",
        configured=True,
        catalog=LiveProbePhaseResult.SKIPPED,
        chat=LiveProbePhaseResult.SKIPPED,
    )
    assert provider_live_probe_is_hard_failure(catalog_gone) is False

    empty_catalog = _probe(
        "zai",
        configured=True,
        catalog=LiveProbePhaseResult.CATALOG_EMPTY,
        chat=LiveProbePhaseResult.SKIPPED,
    )
    assert provider_live_probe_is_hard_failure(empty_catalog) is True

    broken_chat = _probe(
        "sambanova",
        configured=True,
        catalog=LiveProbePhaseResult.OK,
        chat=LiveProbePhaseResult.CHAT_FAILED,
        catalog_model_count=2,
        smoke_model="gpt-oss-120b",
    )
    assert provider_live_probe_is_hard_failure(broken_chat) is True

    no_marker = _probe(
        "nvidia",
        configured=True,
        catalog=LiveProbePhaseResult.OK,
        chat=LiveProbePhaseResult.CHAT_NO_MARKER,
        catalog_model_count=81,
        smoke_model="openai/gpt-oss-20b",
    )
    assert provider_live_probe_is_hard_failure(no_marker) is False
    assert provider_live_probe_is_revoked_key(no_marker) is False

    billing = _probe(
        "bothub",
        configured=True,
        catalog=LiveProbePhaseResult.OK,
        chat=LiveProbePhaseResult.CHAT_FAILED,
        catalog_model_count=1,
        chat_error_class=AIProviderErrorClass.PAYMENT_REQUIRED,
    )
    assert provider_live_probe_is_hard_failure(billing) is False
    assert provider_live_probe_is_revoked_key(billing) is False
    assert provider_live_probe_is_revoked_key(revoked) is True


@pytest.mark.network
@pytest.mark.timeout(600)
async def test_live_all_openai_compat_providers_report() -> None:
    _ = await live_model_service()
    probes = await probe_all_openai_compat_providers()
    assert tuple(probe.provider for probe in probes) == LIVE_LLM_PROVIDERS

    report = format_provider_live_report(probes)
    print(f"\n{report}\n", flush=True)

    revoked_keys = [probe for probe in probes if provider_live_probe_is_revoked_key(probe)]
    if revoked_keys:
        pytest.fail(report, pytrace=False)
