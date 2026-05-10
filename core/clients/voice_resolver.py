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
2. **Per-company** — запись в таблице `company_voice_providers` (только `stt` / `tts`).
3. **Deployment-default** — `settings.voice.<kind>` (`STTProvidersConfig`,
   `TTSProvidersConfig`, `VADProvidersConfig`).

4. **LitServe api id по каталогу** — если итоговый провайдер `litserve`, а поле
   `model` после шагов 1–3 пустое, подставляется
   `provider_litserve.infra.<stt|tts|vad>_default_api_model_id` (должно
   совпадать с моделью в конфиге процесса `provider_litserve`).

5. **TTS LitServe + язык сессии** — если задан `SpeechOverride.language` (query
   `language` на WebSocket voice или поле company для `tts`) и в каталоге
   `provider_litserve.infra.tts_models` есть запись с тем же `synthesis_locale`
   (ISO 639-1), её `api_model_id` подменяет результат шагов 1–4 для выбора
   модели Silero TTS по локали.

Если итоговое значение обязательного поля после всех шагов отсутствует —
`raise ValueError` без маскировки.

## Кэш per-company записей

Записи `company_voice_providers` кэшируются в памяти процесса с TTL
(``_COMPANY_CACHE_TTL_S``). Вручную сбросить кэш для конкретной компании
— `invalidate_company_overrides_cache(company_id)`. В тестах:
``reset_voice_resolver_for_tests()``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal, Optional

from core.clients.speech_override import SpeechOverride
from core.clients.stt_client import (
    BaseSTTClient,
    STTClientFactory,
)
from core.clients.stt_streaming import BaseSTTStreamer, BufferedSTTStreamer
from core.clients.tts_client import (
    BaseTTSClient,
    PronunciationAwareTTSClient,
    TTSClientFactory,
)
from core.clients.tts_pronunciation.models import (
    CompiledPronunciation,
    NormalizationConfig,
    PronunciationRule,
    PronunciationRuleSet,
)
from core.clients.tts_streaming import BaseTTSStreamer, BatchBackedTTSStreamer
from core.clients.vad_client import (
    BaseVADClient,
    VADClientFactory,
)
from core.config import get_settings
from core.config.models import ProviderLitserveTTSModelEntry
from core.db.repositories.company_voice_provider_repository import (
    CompanyVoiceProviderRepository,
    VoiceKind,
)
from core.db.repositories.pronunciation_rule_repository import (
    CompanyPronunciationRuleRepository,
    PlatformPronunciationRuleRepository,
)
from core.logging import get_logger

logger = get_logger(__name__)


_COMPANY_CACHE_TTL_S: float = 60.0
_company_cache: dict[
    tuple[str, VoiceKind], tuple[float, Optional["_CompanyOverrideRow"]]
] = {}

_PRONUNCIATION_CACHE_TTL_S: float = 300.0
_pronunciation_platform_cache: Optional[tuple[float, CompiledPronunciation]] = None
_pronunciation_company_cache: dict[str, tuple[float, CompiledPronunciation]] = {}


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


@dataclass(frozen=True)
class ResolvedSttSettings:
    """Финальный результат tier-резолва STT (`override → company → settings`).

    Используется одновременно для создания `BaseSTTClient` (`get_stt_client`)
    и для синхронизации `language` в `StreamingSTTProvider` (apps/voice).
    """

    provider: str
    model: Optional[str]
    language: str
    source_provider: Literal["override", "company", "settings"]
    source_language: Literal["override", "company", "settings"]


def _value_source(
    *,
    override_value: Optional[str],
    company_value: Optional[str],
) -> Literal["override", "company", "settings"]:
    if override_value is not None and override_value != "":
        return "override"
    if company_value is not None and company_value != "":
        return "company"
    return "settings"


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
    *, company_id: str, kind: Literal["stt", "tts"]
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
    """Снять in-memory-кэш для stt/tts одной компании (VAD — только deployment)."""
    if company_id == "":
        raise ValueError("company_id не может быть пустым.")
    for kind in ("stt", "tts"):
        _company_cache.pop((company_id, kind), None)  # type: ignore[arg-type]
    _pronunciation_company_cache.pop(company_id, None)


def invalidate_platform_pronunciation_cache() -> None:
    """Сбросить кэш платформенных правил произношения (после их изменения суперадмином)."""
    global _pronunciation_platform_cache
    _pronunciation_platform_cache = None


def reset_voice_resolver_for_tests() -> None:
    """Полная очистка in-memory кэша. Только для тестов."""
    global _pronunciation_platform_cache
    _company_cache.clear()
    _pronunciation_company_cache.clear()
    _pronunciation_platform_cache = None


def _validate_company_id(company_id: str) -> None:
    if company_id == "":
        raise ValueError("voice_resolver: company_id не может быть пустым.")


def _validate_override(override: Optional[SpeechOverride]) -> SpeechOverride:
    if override is None:
        return SpeechOverride()
    return override


def _fallback_litserve_api_model_id(
    *,
    resolved: Optional[str],
    kind: Literal["stt", "tts", "vad"],
) -> Optional[str]:
    """Если ``voice.<kind>.default_model`` и override/company пусты, берём api id каталога LitServe."""
    if resolved is not None and resolved != "":
        return resolved
    infra = get_settings().provider_litserve.infra
    if kind == "stt":
        return infra.stt_default_api_model_id
    if kind == "tts":
        return infra.tts_default_api_model_id
    return infra.vad_default_api_model_id


def _normalize_iso639_1_session_locale(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip().lower()
    if s == "":
        return None
    dash = s.find("-")
    under = s.find("_")
    cut = len(s)
    if dash >= 0:
        cut = min(cut, dash)
    if under >= 0:
        cut = min(cut, under)
    base = s[:cut]
    if len(base) < 2:
        return None
    return base[:2]


def _pick_tts_api_model_for_synthesis_locale(
    *,
    tts_models: list[ProviderLitserveTTSModelEntry],
    session_locale: str,
    tier_model: str,
) -> str:
    norm = _normalize_iso639_1_session_locale(session_locale)
    if norm is None:
        return tier_model
    for e in tts_models:
        if e.synthesis_locale is None:
            continue
        if e.synthesis_locale == norm:
            return e.api_model_id
    return tier_model


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


async def resolve_effective_tts_voice_for_ws(
    *,
    company_id: str | None,
    flow_tts: SpeechOverride,
) -> str | None:
    """Итоговый ``voice`` для URL WebSocket (те же шаги 1–3, что в ``get_tts_client``).

    Сначала нормализованное ``flow_tts.voice`` (профиль flow/ветки), затем запись
    ``company_voice_providers`` (kind=tts), затем ``settings.voice.tts.default_voice``.
    Пустая строка в профиле трактуется как отсутствие override (как на WS после
    нормализации query).
    """
    tts = _validate_override(flow_tts)
    cfg = get_settings().voice.tts
    raw_v = tts.voice
    if isinstance(raw_v, str):
        stripped = raw_v.strip()
        flow_voice: str | None = stripped if stripped != "" else None
    else:
        flow_voice = raw_v
    company_row = None
    if company_id is not None and company_id.strip() != "":
        company_row = await _load_company_override(company_id=company_id, kind="tts")
    return _resolve_optional_str(
        override_value=flow_voice,
        company_value=company_row.voice if company_row else None,
        default_value=cfg.default_voice,
    )


async def resolve_stt_settings(
    *,
    company_id: str,
    override: Optional[SpeechOverride] = None,
) -> ResolvedSttSettings:
    """Tier-резолв STT (`override → company → settings`) без создания клиента.

    Используется в `apps/voice` для синхронизации `language` между
    батч-клиентом (`get_stt_client`) и стриминговым адаптером
    (`StreamingSTTProvider`), чтобы не было рассинхрона из-за
    `cfg.default_language`.
    """
    _validate_company_id(company_id)
    override = _validate_override(override)
    settings_voice_stt = get_settings().voice.stt
    company_row = await _load_company_override(company_id=company_id, kind="stt")

    company_provider = company_row.provider if company_row else None
    company_model = company_row.model if company_row else None
    company_language = company_row.language if company_row else None

    provider_name = _resolve_str(
        override_value=override.provider,
        company_value=company_provider,
        default_value=settings_voice_stt.provider,
    )
    model = _resolve_optional_str(
        override_value=override.model,
        company_value=company_model,
        default_value=settings_voice_stt.default_model,
    )
    if provider_name == "litserve":
        model = _fallback_litserve_api_model_id(resolved=model, kind="stt")
    language = _resolve_str(
        override_value=override.language,
        company_value=company_language,
        default_value=settings_voice_stt.default_language,
    )
    return ResolvedSttSettings(
        provider=provider_name,
        model=model,
        language=language,
        source_provider=_value_source(
            override_value=override.provider, company_value=company_provider
        ),
        source_language=_value_source(
            override_value=override.language, company_value=company_language
        ),
    )


async def get_stt_client(
    *,
    company_id: str,
    override: Optional[SpeechOverride] = None,
) -> BaseSTTClient:
    """Получить STT-клиента с применённым tier-резолвом.

    Для `litserve` допускается финальный api id модели из каталога LitServe
    (см. модульный докстринг), если `voice.stt.default_model` и override/company
    пусты. Если итоговый провайдер не реализован или ключи отсутствуют —
    `raise ValueError`/`NotImplementedError`.
    """
    resolved = await resolve_stt_settings(company_id=company_id, override=override)
    settings_voice_stt = get_settings().voice.stt
    override_obj = _validate_override(override)
    company_row = await _load_company_override(company_id=company_id, kind="stt")
    timeout_s = override_obj.timeout_s
    sec = company_row.secrets if company_row else None

    logger.info(
        "voice_resolver.stt_resolved",
        company_id=company_id,
        provider=resolved.provider,
        model=resolved.model,
        language=resolved.language,
        source_provider=resolved.source_provider,
        source_language=resolved.source_language,
    )

    return STTClientFactory.create_for_voice(
        cfg=settings_voice_stt,
        provider_name=resolved.provider,
        model=resolved.model,
        default_language=resolved.language,
        timeout_s=timeout_s,
        secrets=sec,
    )


def _get_pronunciation_repo() -> tuple[PlatformPronunciationRuleRepository, CompanyPronunciationRuleRepository]:
    settings = get_settings()
    db_url = settings.database.shared_url
    if not db_url:
        raise ValueError(
            "voice_resolver: settings.database.shared_url не задан — "
            "невозможно прочитать pronunciation_rules."
        )
    return (
        PlatformPronunciationRuleRepository(db_url=db_url),
        CompanyPronunciationRuleRepository(db_url=db_url),
    )


def _db_row_to_pronunciation_rule(row: object) -> PronunciationRule:
    return PronunciationRule(
        id=row.id,  # type: ignore[attr-defined]
        kind=row.kind,  # type: ignore[attr-defined]
        pattern=row.pattern,  # type: ignore[attr-defined]
        replacement=row.replacement,  # type: ignore[attr-defined]
        language=row.language,  # type: ignore[attr-defined]
        case_sensitive=row.case_sensitive,  # type: ignore[attr-defined]
        word_boundary=row.word_boundary,  # type: ignore[attr-defined]
        providers=list(row.providers) if row.providers else None,  # type: ignore[attr-defined]
        voices=list(row.voices) if row.voices else None,  # type: ignore[attr-defined]
        enabled=row.enabled,  # type: ignore[attr-defined]
        note=row.note,  # type: ignore[attr-defined]
    )


async def _load_platform_pronunciation() -> CompiledPronunciation:
    """Загрузить платформенные правила произношения с TTL-кэшем."""
    global _pronunciation_platform_cache
    now = time.monotonic()
    if _pronunciation_platform_cache is not None:
        ts, cached = _pronunciation_platform_cache
        if (now - ts) < _PRONUNCIATION_CACHE_TTL_S:
            return cached

    platform_repo, _ = _get_pronunciation_repo()
    rows = await platform_repo.list_enabled()
    rules = [_db_row_to_pronunciation_rule(r) for r in rows]
    rule_set = PronunciationRuleSet(rules=rules, normalization=NormalizationConfig())
    compiled = CompiledPronunciation.from_rule_set(
        rule_set,
        ssml_subset_enabled=get_settings().voice.tts.pronunciation.ssml_subset_enabled
        if hasattr(get_settings().voice.tts, "pronunciation")
        else False,
    )
    _pronunciation_platform_cache = (now, compiled)
    return compiled


async def _load_company_pronunciation(company_id: str) -> CompiledPronunciation:
    """Загрузить per-company правила произношения с TTL-кэшем."""
    now = time.monotonic()
    cached = _pronunciation_company_cache.get(company_id)
    if cached is not None and (now - cached[0]) < _PRONUNCIATION_CACHE_TTL_S:
        return cached[1]

    _, company_repo = _get_pronunciation_repo()
    rows = await company_repo.list_enabled(company_id=company_id)
    rules = [_db_row_to_pronunciation_rule(r) for r in rows]
    rule_set = PronunciationRuleSet(rules=rules, normalization=NormalizationConfig())
    compiled = CompiledPronunciation.from_rule_set(rule_set)
    _pronunciation_company_cache[company_id] = (now, compiled)
    return compiled


async def resolve_tts_pronunciation(
    *,
    company_id: str,
    override: Optional[SpeechOverride] = None,
) -> CompiledPronunciation:
    """Каскадный резолв правил произношения TTS для данной компании и call-override.

    Порядок: platform → company → per-call (SpeechOverride.pronunciation_rules).
    Если ``override.pronunciation_replace=True`` — per-call заменяет все предыдущие.
    """
    _validate_company_id(company_id)
    override = _validate_override(override)

    platform_compiled = await _load_platform_pronunciation()
    company_compiled = await _load_company_pronunciation(company_id)

    if override.pronunciation_rules is not None and override.pronunciation_replace:
        per_call_rule_set = PronunciationRuleSet(
            rules=override.pronunciation_rules,
            normalization=NormalizationConfig(),
        )
        return CompiledPronunciation.from_rule_set(per_call_rule_set)

    base = platform_compiled.merge(company_compiled)

    if override.pronunciation_rules:
        per_call_rule_set = PronunciationRuleSet(
            rules=override.pronunciation_rules,
            normalization=NormalizationConfig(),
        )
        per_call_compiled = CompiledPronunciation.from_rule_set(per_call_rule_set)
        return base.merge(per_call_compiled)

    return base


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
    locale_for_tts = _resolve_optional_str(
        override_value=override.language,
        company_value=company_row.language if company_row else None,
        default_value=None,
    )
    if provider_name == "litserve":
        model = _fallback_litserve_api_model_id(resolved=model, kind="tts")
        if locale_for_tts:
            infra = get_settings().provider_litserve.infra
            model = _pick_tts_api_model_for_synthesis_locale(
                tts_models=infra.tts_models,
                session_locale=locale_for_tts,
                tier_model=model or "",
            )
            model = _fallback_litserve_api_model_id(resolved=model, kind="tts")
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

    logger.info(
        "voice_resolver.tts_resolved",
        company_id=company_id,
        provider=provider_name,
        model=model,
        synthesis_locale_hint=_normalize_iso639_1_session_locale(locale_for_tts)
        if locale_for_tts
        else None,
        voice=voice,
        response_format=response_format,
        sample_rate=sample_rate,
        source_provider=_value_source(
            override_value=override.provider,
            company_value=company_row.provider if company_row else None,
        ),
    )

    base_client = TTSClientFactory.create_for_voice(
        cfg=cfg,
        provider_name=provider_name,
        model=model,
        default_voice=voice,
        default_response_format=response_format,
        default_sample_rate=sample_rate,
        timeout_s=timeout_s,
        secrets=sec,
    )

    pronunciation = await resolve_tts_pronunciation(
        company_id=company_id,
        override=override,
    )

    return PronunciationAwareTTSClient(
        base_client,
        pronunciation,
        provider_name=provider_name,
        default_voice=voice,
        default_language=locale_for_tts,
    )


async def get_vad_client(
    *,
    company_id: str,
    override: Optional[SpeechOverride] = None,
) -> BaseVADClient:
    """Получить VAD-клиента. Per-company override для VAD не используется — только
    `SpeechOverride` (per-call) и `settings.voice.vad`.
    """
    _validate_company_id(company_id)
    override = _validate_override(override)
    cfg = get_settings().voice.vad

    provider_name = _resolve_str(
        override_value=override.provider,
        company_value=None,
        default_value=cfg.provider,
    )
    model = _resolve_optional_str(
        override_value=override.model,
        company_value=None,
        default_value=cfg.default_model,
    )
    if provider_name == "litserve":
        model = _fallback_litserve_api_model_id(resolved=model, kind="vad")
    sample_rate = _resolve_int(
        override_value=override.sample_rate,
        company_value=None,
        default_value=cfg.default_sample_rate,
    )
    threshold = _resolve_float(
        override_value=override.threshold,
        company_value=None,
        default_value=cfg.default_threshold,
    )
    timeout_s = override.timeout_s

    logger.info(
        "voice_resolver.vad_resolved",
        company_id=company_id,
        provider=provider_name,
        model=model,
        sample_rate=sample_rate,
        threshold=threshold,
        source_provider=_value_source(
            override_value=override.provider,
            company_value=None,
        ),
    )

    return VADClientFactory.create_for_voice(
        cfg=cfg,
        provider_name=provider_name,
        model=model,
        sample_rate=sample_rate,
        threshold=threshold,
        timeout_s=timeout_s,
        secrets=None,
    )


_TTS_MIME_BY_FORMAT: dict[str, str] = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "pcm": "audio/L16",
    "lpcm": "audio/L16",
}


async def get_stt_streamer(
    *,
    company_id: str,
    override: Optional[SpeechOverride] = None,
    sample_rate: int = 16000,
) -> BaseSTTStreamer:
    """Получить streaming STT-клиента (tier-резолв как у ``get_stt_client``).

    Возвращает ``BaseSTTStreamer``. Для провайдеров без native streaming
    под капотом — ``BufferedSTTStreamer`` поверх batch-клиента.

    ``sample_rate`` обязателен: PCM от источника должен быть на известной
    частоте дискретизации (обычно 16000 для voice-сессии).
    """
    if sample_rate <= 0:
        raise ValueError("voice_resolver.get_stt_streamer: sample_rate должен быть > 0.")

    stt_client = await get_stt_client(company_id=company_id, override=override)
    language = None
    if override is not None and override.language:
        language = override.language
    else:
        language = get_settings().voice.stt.default_language
    return BufferedSTTStreamer(
        stt_client=stt_client,
        sample_rate=sample_rate,
        language=language,
    )


async def get_tts_streamer(
    *,
    company_id: str,
    override: Optional[SpeechOverride] = None,
) -> BaseTTSStreamer:
    """Получить streaming TTS-клиента (tier-резолв как у ``get_tts_client``).

    Возвращает ``BaseTTSStreamer``. Для провайдеров без native streaming
    — ``BatchBackedTTSStreamer`` поверх batch-клиента + ``VoiceChunker``.
    """
    _validate_company_id(company_id)
    override = _validate_override(override)
    cfg = get_settings().voice.tts
    company_row = await _load_company_override(company_id=company_id, kind="tts")

    provider_name = _resolve_str(
        override_value=override.provider,
        company_value=company_row.provider if company_row else None,
        default_value=cfg.provider,
    )
    response_format = _resolve_str(
        override_value=override.response_format,
        company_value=company_row.response_format if company_row else None,
        default_value=cfg.default_response_format,
    )
    sample_rate = _resolve_int(
        override_value=override.sample_rate,
        company_value=company_row.sample_rate if company_row else None,
        default_value=cfg.default_sample_rate,
    )
    if response_format not in _TTS_MIME_BY_FORMAT:
        raise ValueError(
            f"voice_resolver.get_tts_streamer: неизвестный response_format={response_format!r} "
            f"(допустимые: {sorted(_TTS_MIME_BY_FORMAT)})"
        )
    mime_type = _TTS_MIME_BY_FORMAT[response_format]

    tts_client = await get_tts_client(company_id=company_id, override=override)
    return BatchBackedTTSStreamer(
        tts_client=tts_client,
        response_format=response_format,
        sample_rate=sample_rate,
        provider_name=provider_name,
        mime_type=mime_type,
    )


__all__ = [
    "ResolvedSttSettings",
    "resolve_effective_tts_voice_for_ws",
    "resolve_stt_settings",
    "resolve_tts_pronunciation",
    "get_stt_client",
    "get_tts_client",
    "get_vad_client",
    "get_stt_streamer",
    "get_tts_streamer",
    "invalidate_company_overrides_cache",
    "invalidate_platform_pronunciation_cache",
    "reset_voice_resolver_for_tests",
]
