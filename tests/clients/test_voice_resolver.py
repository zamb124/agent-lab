"""Unit-тесты `core.clients.voice_resolver`.

Проверяем:
* `resolve_stt_settings` отдаёт корректный provider/model/language с учётом
  трёхуровневого tier-резолва (`override → company → settings`).
* `get_stt_client` пишет лог `voice_resolver.stt_resolved` со значением
  `source_provider`/`source_language`.
"""

from __future__ import annotations

import time

import pytest

from core.clients.speech_override import SpeechOverride
from core.clients.voice_resolver import (
    _CompanyOverrideRow,
    _company_cache,
    get_stt_client,
    reset_voice_resolver_for_tests,
    resolve_stt_settings,
)


pytestmark = pytest.mark.timeout(15)


def _stub_company_cache(company_id: str, *, kind: str, row: _CompanyOverrideRow | None) -> None:
    """Положить готовое значение в TTL-кэш, чтобы не ходить в БД."""
    _company_cache[(company_id, kind)] = (time.monotonic() + 3600, row)


@pytest.fixture(autouse=True)
def _reset_resolver_cache():
    reset_voice_resolver_for_tests()
    yield
    reset_voice_resolver_for_tests()


@pytest.mark.asyncio
async def test_resolve_stt_settings_uses_settings_when_no_company_override(
    unique_id: str,
) -> None:
    cid = f"company_{unique_id}"
    _stub_company_cache(cid, kind="stt", row=None)

    resolved = await resolve_stt_settings(company_id=cid)

    assert resolved.provider == "litserve"
    assert resolved.source_provider == "settings"
    assert resolved.source_language == "settings"


@pytest.mark.asyncio
async def test_resolve_stt_settings_company_override_wins(unique_id: str) -> None:
    cid = f"company_{unique_id}"
    _stub_company_cache(
        cid,
        kind="stt",
        row=_CompanyOverrideRow(
            provider="cloud_ru",
            model="openai/whisper-large-v3",
            voice=None,
            language="en",
            sample_rate=None,
            threshold=None,
            response_format=None,
            secrets=None,
        ),
    )

    resolved = await resolve_stt_settings(company_id=cid)

    assert resolved.provider == "cloud_ru"
    assert resolved.model == "openai/whisper-large-v3"
    assert resolved.language == "en"
    assert resolved.source_provider == "company"
    assert resolved.source_language == "company"


@pytest.mark.asyncio
async def test_resolve_stt_settings_override_beats_company(unique_id: str) -> None:
    cid = f"company_{unique_id}"
    _stub_company_cache(
        cid,
        kind="stt",
        row=_CompanyOverrideRow(
            provider="cloud_ru",
            model="openai/whisper-large-v3",
            voice=None,
            language="en",
            sample_rate=None,
            threshold=None,
            response_format=None,
            secrets=None,
        ),
    )

    resolved = await resolve_stt_settings(
        company_id=cid,
        override=SpeechOverride(provider="mock", language="ru"),
    )

    assert resolved.provider == "mock"
    assert resolved.language == "ru"
    assert resolved.source_provider == "override"
    assert resolved.source_language == "override"


@pytest.mark.asyncio
async def test_get_stt_client_logs_resolved_fields(
    unique_id: str, caplog: pytest.LogCaptureFixture
) -> None:
    """get_stt_client пишет info-лог `voice_resolver.stt_resolved` с провайдером, моделью и language."""
    cid = f"company_{unique_id}"
    _stub_company_cache(cid, kind="stt", row=None)

    caplog.set_level("INFO", logger="core.clients.voice_resolver")
    client = await get_stt_client(
        company_id=cid,
        override=SpeechOverride(provider="mock", language="en"),
    )

    assert client is not None
    rec = next(
        (r for r in caplog.records if r.message == "voice_resolver.stt_resolved"),
        None,
    )
    assert rec is not None
    extra = getattr(rec, "provider", None)
    assert extra == "mock"
    assert getattr(rec, "language", None) == "en"
    assert getattr(rec, "source_provider", None) == "override"
    assert getattr(rec, "source_language", None) == "override"
