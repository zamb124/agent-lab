"""Единственная точка входа для получения STT/TTS/VAD клиентов.

Любой сервис платформы (apps/voice, apps/flows, apps/sync, apps/crm, eval-
sandbox внутри flows tools и т.д.) **обязан** получать клиента речи через
функции этого модуля. Прямой импорт классов из `core.clients.stt_client`,
`core.clients.tts_client`, `core.clients.vad_client` в `apps/**` запрещён
CI (`scripts/check_voice_resolver_usage.py`).

## Tier-резолв (Zero-Guess)

Для каждого поля проверяем источники в строгом порядке (первый не-None
побеждает):

1. **Per-call/per-process** — поле из `SpeechOverride`, переданного в вызов.
2. **Per-company** — запись в таблице `company_voice_providers`.
3. **Deployment-default** — `settings.voice.<kind>` (`STTProvidersConfig`,
   `TTSProvidersConfig`, `VADProvidersConfig`).

Если итоговое значение обязательного поля отсутствует — `raise ValueError`
без неявных дефолтов и фолбеков.

## Кэш per-company записей

Записи `company_voice_providers` кэшируются в памяти процесса с TTL
(``_COMPANY_CACHE_TTL_S``). Вручную сбросить кэш для конкретной компании
— `invalidate_company_overrides_cache(company_id)`. В тестах:
``reset_voice_resolver_for_tests()``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from core.clients.speech_override import SpeechOverride
from core.clients.stt_client import (
    BaseSTTClient,
    STTClientFactory,
)
from core.clients.tts_client import (
    BaseTTSClient,
    TTSClientFactory,
)
from core.clients.vad_client import (
    BaseVADClient,
    VADClientFactory,
)
from core.config import get_settings
from core.db.repositories.company_voice_provider_repository import (
    CompanyVoiceProviderRepository,
    VoiceKind,
)
from core.logging import get_logger


logger = get_logger(__name__)


_COMPANY_CACHE_TTL_S: float = 60.0
_company_cache: dict[
    tuple[str, VoiceKind], tuple[float, Optional["_CompanyOverrideRow"]]
] = {}


@dataclass(frozen=True)
class _CompanyOverrideRow:
    """In-memory представление одной строки `company_voice_providers`."""

    provider: str
    model: Optional[str]
    voice: Optional[str]
    language: Optional[str]
    sample_rate: Optional[int]
    threshold: Optional[float]
    response_format: Optional[str]
    secrets: Optional[dict[str, str]]


def _coerce_company_voice_secrets(raw: object | None) -> Optional[dict[str, str]]:
    """Нормализует JSONB `secrets`: только строковые ключи и значения."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(
            "voice_resolver: поле secrets в company_voice_providers должно быть "
            "JSON-объектом или null."
        )
    out: dict[str, str] = {}
    for key, val in raw.items():
        if not isinstance(key, str):
            raise ValueError("voice_resolver: ключ secrets должен быть str.")
        if not isinstance(val, str):
            raise ValueError(f"voice_resolver: значение secrets[{key!r}] должно быть str.")
        out[key] = val
    return out if out else None


def _get_repo() -> CompanyVoiceProviderRepository:
    settings = get_settings()
    db_url = settings.database.shared_url
    if db_url == "":
        raise ValueError(
            "voice_resolver: settings.database.shared_url не задан — "
            "невозможно прочитать company_voice_providers."
        )
    return CompanyVoiceProviderRepository(db_url=db_url)


async def _load_company_override(
    *, company_id: str, kind: VoiceKind
) -> Optional[_CompanyOverrideRow]:
    """Прочитать запись `company_voice_providers` с TTL-кэшем."""
    cache_key = (company_id, kind)
    now = time.monotonic()
    cached = _company_cache.get(cache_key)
    if cached is not None and (now - cached[0]) < _COMPANY_CACHE_TTL_S:
        return cached[1]

    repo = _get_repo()
    record = await repo.get(company_id=company_id, kind=kind)
    row: Optional[_CompanyOverrideRow]
    if record is None:
        row = None
    else:
        row = _CompanyOverrideRow(
            provider=record.provider,
            model=record.model,
            voice=record.voice,
            language=record.language,
            sample_rate=record.sample_rate,
            threshold=record.threshold,
            response_format=record.response_format,
            secrets=_coerce_company_voice_secrets(record.secrets),
        )
    _company_cache[cache_key] = (now, row)
    return row


def invalidate_company_overrides_cache(company_id: str) -> None:
    """Снять in-memory-кэш для всех видов (stt/tts/vad) одной компании."""
    if company_id == "":
        raise ValueError("company_id не может быть пустым.")
    for kind in ("stt", "tts", "vad"):
        _company_cache.pop((company_id, kind), None)  # type: ignore[arg-type]


def reset_voice_resolver_for_tests() -> None:
    """Полная очистка in-memory кэша. Только для тестов."""
    _company_cache.clear()


def _validate_company_id(company_id: str) -> None:
    if company_id == "":
        raise ValueError("voice_resolver: company_id не может быть пустым.")


def _validate_override(override: Optional[SpeechOverride]) -> SpeechOverride:
    if override is None:
        return SpeechOverride()
    return override


def _resolve_str(
    *,
    override_value: Optional[str],
    company_value: Optional[str],
    default_value: str,
) -> str:
    if override_value is not None and override_value != "":
        return override_value
    if company_value is not None and company_value != "":
        return company_value
    return default_value


def _resolve_optional_str(
    *,
    override_value: Optional[str],
    company_value: Optional[str],
    default_value: Optional[str],
) -> Optional[str]:
    if override_value is not None and override_value != "":
        return override_value
    if company_value is not None and company_value != "":
        return company_value
    return default_value


def _resolve_int(
    *,
    override_value: Optional[int],
    company_value: Optional[int],
    default_value: int,
) -> int:
    if override_value is not None:
        return override_value
    if company_value is not None:
        return company_value
    return default_value


def _resolve_float(
    *,
    override_value: Optional[float],
    company_value: Optional[float],
    default_value: float,
) -> float:
    if override_value is not None:
        return override_value
    if company_value is not None:
        return company_value
    return default_value


def _resolve_optional_float(
    *,
    override_value: Optional[float],
    company_value: Optional[float],
) -> Optional[float]:
    if override_value is not None:
        return override_value
    return company_value


async def get_stt_client(
    *,
    company_id: str,
    override: Optional[SpeechOverride] = None,
) -> BaseSTTClient:
    """Получить STT-клиента с применённым tier-резолвом.

    Возвращает готовый клиент — никаких неявных дефолтов сверх того, что
    зафиксировано в `STTProvidersConfig`. Если итоговый провайдер не
    реализован или ключи отсутствуют — `raise ValueError`/`NotImplementedError`.
    """
    _validate_company_id(company_id)
    override = _validate_override(override)
    settings_voice_stt = get_settings().voice.stt
    company_row = await _load_company_override(company_id=company_id, kind="stt")

    provider_name = _resolve_str(
        override_value=override.provider,
        company_value=company_row.provider if company_row else None,
        default_value=settings_voice_stt.provider,
    )
    model = _resolve_optional_str(
        override_value=override.model,
        company_value=company_row.model if company_row else None,
        default_value=settings_voice_stt.default_model,
    )
    language = _resolve_str(
        override_value=override.language,
        company_value=company_row.language if company_row else None,
        default_value=settings_voice_stt.default_language,
    )
    timeout_s = override.timeout_s
    sec = company_row.secrets if company_row else None

    return STTClientFactory.create_for_voice(
        cfg=settings_voice_stt,
        provider_name=provider_name,
        model=model,
        default_language=language,
        timeout_s=timeout_s,
        secrets=sec,
    )


async def get_tts_client(
    *,
    company_id: str,
    override: Optional[SpeechOverride] = None,
) -> BaseTTSClient:
    """Получить TTS-клиента с применённым tier-резолвом."""
    _validate_company_id(company_id)
    override = _validate_override(override)
    cfg = get_settings().voice.tts
    company_row = await _load_company_override(company_id=company_id, kind="tts")

    provider_name = _resolve_str(
        override_value=override.provider,
        company_value=company_row.provider if company_row else None,
        default_value=cfg.provider,
    )
    model = _resolve_optional_str(
        override_value=override.model,
        company_value=company_row.model if company_row else None,
        default_value=cfg.default_model,
    )
    voice = _resolve_optional_str(
        override_value=override.voice,
        company_value=company_row.voice if company_row else None,
        default_value=cfg.default_voice,
    )
    response_format = _resolve_optional_str(
        override_value=override.response_format,
        company_value=company_row.response_format if company_row else None,
        default_value=cfg.default_response_format,
    )
    sample_rate = _resolve_int(
        override_value=override.sample_rate,
        company_value=company_row.sample_rate if company_row else None,
        default_value=cfg.default_sample_rate,
    )
    timeout_s = override.timeout_s
    sec = company_row.secrets if company_row else None

    return TTSClientFactory.create_for_voice(
        cfg=cfg,
        provider_name=provider_name,
        model=model,
        default_voice=voice,
        default_response_format=response_format,
        default_sample_rate=sample_rate,
        timeout_s=timeout_s,
        secrets=sec,
    )


async def get_vad_client(
    *,
    company_id: str,
    override: Optional[SpeechOverride] = None,
) -> BaseVADClient:
    """Получить VAD-клиента с применённым tier-резолвом."""
    _validate_company_id(company_id)
    override = _validate_override(override)
    cfg = get_settings().voice.vad
    company_row = await _load_company_override(company_id=company_id, kind="vad")

    provider_name = _resolve_str(
        override_value=override.provider,
        company_value=company_row.provider if company_row else None,
        default_value=cfg.provider,
    )
    model = _resolve_optional_str(
        override_value=override.model,
        company_value=company_row.model if company_row else None,
        default_value=cfg.default_model,
    )
    sample_rate = _resolve_int(
        override_value=override.sample_rate,
        company_value=company_row.sample_rate if company_row else None,
        default_value=cfg.default_sample_rate,
    )
    threshold = _resolve_float(
        override_value=override.threshold,
        company_value=company_row.threshold if company_row else None,
        default_value=cfg.default_threshold,
    )
    timeout_s = override.timeout_s
    sec = company_row.secrets if company_row else None

    return VADClientFactory.create_for_voice(
        cfg=cfg,
        provider_name=provider_name,
        model=model,
        sample_rate=sample_rate,
        threshold=threshold,
        timeout_s=timeout_s,
        secrets=sec,
    )


__all__ = [
    "get_stt_client",
    "get_tts_client",
    "get_vad_client",
    "invalidate_company_overrides_cache",
    "reset_voice_resolver_for_tests",
]
