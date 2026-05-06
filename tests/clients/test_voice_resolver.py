"""Unit-тесты `core.clients.voice_resolver`.

Проверяем:
* `resolve_stt_settings` отдаёт корректный provider/model/language с учётом
  трёхуровневого tier-резолва (`override → company → settings`).
* `get_stt_client` пишет лог `voice_resolver.stt_resolved` со значением
  `source_provider`/`source_language`.
"""

from __future__ import annotations

import ast
import json
import logging
import time

import pytest

from core.clients.speech_override import SpeechOverride
from core.clients.voice_resolver import (
    _CompanyOverrideRow,
    _company_cache,
    get_stt_client,
    get_vad_client,
    reset_voice_resolver_for_tests,
    resolve_stt_settings,
)
from core.config import get_settings
from core.logging.scope import SystemLogScope


pytestmark = pytest.mark.timeout(15)


def _caplog_message_to_dict(raw: str) -> dict[str, object]:
    """structlog в caplog может дать JSON или repr(dict) в зависимости от рендера."""
    stripped = raw.strip()
    if stripped.startswith("{"):
        try:
            parsed: object = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    try:
        parsed = ast.literal_eval(stripped)
    except (ValueError, SyntaxError) as exc:
        raise AssertionError(
            f"voice_resolver caplog: не удалось разобрать message: {raw[:200]!r}"
        ) from exc
    if not isinstance(parsed, dict):
        raise AssertionError(
            f"voice_resolver caplog: ожидался dict, получено {type(parsed).__name__}"
        )
    return parsed


def _voice_resolver_log_dict(rec: logging.LogRecord) -> dict[str, object]:
    return _caplog_message_to_dict(rec.getMessage())


def _find_voice_resolver_caplog_record(
    caplog: pytest.LogCaptureFixture, *, event_name: str
) -> logging.LogRecord:
    for r in caplog.records:
        if r.name != "core.clients.voice_resolver":
            continue
        msg = r.getMessage()
        if event_name in msg:
            return r
        if msg.strip().startswith("{"):
            try:
                parsed = _caplog_message_to_dict(msg)
                if parsed.get("message") == event_name:
                    return r
            except AssertionError:
                continue
    raise AssertionError(f"Нет log record voice_resolver с событием {event_name!r}")


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

    assert resolved.provider == get_settings().voice.stt.provider
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

    with SystemLogScope():
        caplog.set_level("INFO", logger="core.clients.voice_resolver")
        client = await get_stt_client(
            company_id=cid,
            override=SpeechOverride(provider="mock", language="en"),
        )

    assert client is not None
    rec = _find_voice_resolver_caplog_record(caplog, event_name="voice_resolver.stt_resolved")
    payload = _voice_resolver_log_dict(rec)
    assert payload["provider"] == "mock"
    assert payload["language"] == "en"
    assert payload["source_provider"] == "override"
    assert payload["source_language"] == "override"


@pytest.mark.asyncio
async def test_get_vad_client_ignores_company_vad_row_in_cache(
    unique_id: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Устаревший кэш по kind=vad не влияет: VAD только override + deployment."""
    cid = f"company_{unique_id}"
    _stub_company_cache(
        cid,
        kind="vad",
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

    with SystemLogScope():
        caplog.set_level("INFO", logger="core.clients.voice_resolver")
        await get_vad_client(company_id=cid)

    rec = _find_voice_resolver_caplog_record(caplog, event_name="voice_resolver.vad_resolved")
    payload = _voice_resolver_log_dict(rec)
    assert payload["source_provider"] == "settings"
