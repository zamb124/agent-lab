"""Движок для локального TTS в provider_litserve.

Параметры моделей (``silero_bundle``, ``silero_language``, ``voice``, ``sample_rate``,
``hf_model_id``, опциональная ``revision``) берутся из ``cfg.tts_models``. Дефолт —
самой старой ready-записи каталога. Никаких хардкодов выбранной модели в коде.

Бэкенд — Silero TTS (``silero.silero_tts`` + ``apply_tts``) по ``api_model_id`` из конфига.
Один HTTP-запрос может синтезировать длинный текст: строка режется на сегменты (до 900 символов,
граница по пробелу при возможности), PCM16 от каждого ``apply_tts`` склеивается в один поток.
"""

from __future__ import annotations

import io
import time
import wave
from collections.abc import Mapping
from typing import ClassVar, Literal, Protocol, TypeAlias

import torch
from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field
from silero import silero_tts

from apps.provider_litserve.catalog import ModelCatalog
from core.config.models import (
    SILERO_V5_RU_SPEAKERS_BY_BUNDLE,
    ProviderLitserveInfraConfig,
    ProviderLitserveTTSModelEntry,
)
from core.logging import get_logger
from core.types import JsonValue
from core.utils.text_sanitize import sanitize_text_for_speech_backend
from core.utils.tts_input_steps import apply_tts_input_steps
from core.websocket import WsCommandError

logger = get_logger(__name__)

TTSRawBody: TypeAlias = Mapping[str, JsonValue]


class SileroTTSModel(Protocol):
    def apply_tts(self, *, text: str, speaker: str, sample_rate: int) -> torch.Tensor: ...


class TTSSynthesisInput(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    text: str
    model: str
    voice_override: str | None = None
    response_format: Literal["pcm", "wav"]
    sample_rate_override: int | None = Field(default=None, gt=0)


class TTSWarmupInfo(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    api_model_id: str
    hf_model_id: str
    silero_bundle: str
    silero_language: str
    cached_before: bool
    load_seconds: float


def _text_contains_cyrillic(text: str) -> bool:
    return any("\u0400" <= c <= "\u04ff" for c in text)


def _normalize_silero_speaker(name: str) -> str:
    return sanitize_text_for_speech_backend(name).strip().lower()


def parse_tts_body(
    raw: TTSRawBody | Request,
    *,
    default_api_model_id: str,
) -> TTSSynthesisInput:
    """Разобрать тело TTS-запроса (OpenAI-совместимое).

    Поля: ``input`` (текст), ``model`` (опционально, api id из
    ``cfg.tts_models``), ``voice`` (опционально, переопределяет дефолт
    модели), ``response_format`` (``pcm``|``wav``).
    """
    if isinstance(raw, Request):
        raise WsCommandError("unprocessable", "TTS: LitServe must pass a prepared request body", error_code="ws_invalid_payload")

    input_raw = raw.get("input")
    if not isinstance(input_raw, str):
        raise WsCommandError("unprocessable", "TTS: input must be a string", error_code="ws_invalid_payload")
    raw_input = input_raw.strip()
    text = sanitize_text_for_speech_backend(raw_input).strip()
    if not text:
        if raw_input:
            raise WsCommandError(
                "unprocessable",
                "TTS: input field has no valid Unicode characters after normalization",
                error_code="ws_invalid_payload",
            )
        raise WsCommandError("unprocessable", "TTS: input field is required and must not be empty", error_code="ws_invalid_payload")

    model_raw = raw.get("model")
    if model_raw is None:
        requested_model = ""
    elif isinstance(model_raw, str):
        requested_model = model_raw.strip()
    else:
        raise WsCommandError("unprocessable", "TTS: model must be a string", error_code="ws_invalid_payload")
    if requested_model == "":
        requested_model = default_api_model_id.strip()
    if requested_model == "":
        raise WsCommandError(
            "unprocessable",
            "TTS: model is required (explicitly or default catalog entry)",
            error_code="ws_invalid_payload",
        )

    voice_raw = raw.get("voice")
    voice_override: str | None
    if voice_raw is None:
        voice_override = None
    elif isinstance(voice_raw, str):
        v = sanitize_text_for_speech_backend(voice_raw.strip()).strip()
        voice_override = _normalize_silero_speaker(v) if v else None
    else:
        raise WsCommandError("unprocessable", "TTS: voice must be a string", error_code="ws_invalid_payload")

    response_format_raw = raw.get("response_format")
    if response_format_raw is None:
        response_format = "wav"
    elif isinstance(response_format_raw, str):
        response_format = response_format_raw.strip().lower()
    else:
        raise WsCommandError("unprocessable", "TTS: response_format must be a string", error_code="ws_invalid_payload")
    if response_format not in ("pcm", "wav"):
        raise WsCommandError("unprocessable", "TTS: response_format supports only pcm or wav", error_code="ws_invalid_payload")

    sample_rate_raw = raw.get("sample_rate")
    if sample_rate_raw is None:
        sample_rate_override = None
    elif isinstance(sample_rate_raw, int) and not isinstance(sample_rate_raw, bool):
        sample_rate_override = sample_rate_raw
    else:
        raise WsCommandError("unprocessable", "TTS: sample_rate must be an integer", error_code="ws_invalid_payload")

    return TTSSynthesisInput(
        text=text,
        model=requested_model,
        voice_override=voice_override,
        response_format=response_format,
        sample_rate_override=sample_rate_override,
    )


def _pcm_to_wav(pcm_bytes: bytes, *, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _audio_to_pcm16_le(audio: torch.Tensor) -> bytes:
    samples = audio.detach().cpu().flatten()
    if str(samples.dtype) == "torch.int16":
        pcm16 = samples.short()
    else:
        pcm16 = (samples.float() * 32767.0).clamp(-32768, 32767).short()
    return pcm16.numpy().tobytes()


def _pcm16_silence(*, sample_rate: int, duration_ms: int = 40) -> bytes:
    frames = max(1, int(sample_rate * duration_ms / 1000))
    return b"\x00\x00" * frames


# Silero предупреждает при >1000 символов; внутри TorchScript падает pos_encoder (5000 vs длиннее).
_SILERO_APPLY_TTS_MAX_CHARS = 900


def _split_text_for_silero_apply(text: str, *, max_chars: int) -> list[str]:
    if max_chars < 1:
        raise ValueError("TTS: max_chars for segmentation must be >= 1")
    t = text.strip()
    if not t:
        return []
    if len(t) <= max_chars:
        return [t]
    parts: list[str] = []
    i = 0
    n = len(t)
    while i < n:
        end = min(i + max_chars, n)
        if end >= n:
            chunk = t[i:n].strip()
            if chunk:
                parts.append(chunk)
            break
        window = t[i:end]
        cut = window.rfind(" ")
        if cut <= 0:
            chunk = t[i:end].strip()
            if chunk:
                parts.append(chunk)
            i = end
            continue
        split_at = i + cut
        chunk = t[i:split_at].strip()
        if chunk:
            parts.append(chunk)
        i = split_at + 1
        while i < n and t[i].isspace():
            i += 1
    return parts


class LocalTTSEngine:
    """Multi-model TTS: модели и их параметры — из ``ModelCatalog``."""

    def __init__(self, cfg: ProviderLitserveInfraConfig, catalog: ModelCatalog) -> None:
        self._cfg: ProviderLitserveInfraConfig = cfg
        self._catalog: ModelCatalog = catalog
        self._models: dict[tuple[str, str, str, str], SileroTTSModel] = {}
        self._device: str = "cpu"

    def setup(self, device: str | None) -> None:
        self._device = device or "cpu"

    def _torch_device(self) -> str:
        d = (self._device or "cpu").strip()
        if d == "cpu" or d == "":
            return "cpu"
        if d == "mps":
            return "mps"
        if d.startswith("cuda"):
            return d
        return d

    def _resolve_entry(self, requested_api_model_id: str) -> ProviderLitserveTTSModelEntry:
        entry = self._catalog.find_typed("tts", requested_api_model_id)
        if entry is None:
            message = (
                f"TTS: неизвестная модель {requested_api_model_id!r}; "
                + f"доступные: {sorted(self._catalog.allowed_ids('tts'))}"
            )
            raise ValueError(message)
        return entry

    def _cache_key(self, entry: ProviderLitserveTTSModelEntry) -> tuple[str, str, str, str]:
        return (
            entry.silero_language,
            entry.silero_bundle,
            entry.revision or "",
            self._device,
        )

    def _ensure_model(self, entry: ProviderLitserveTTSModelEntry) -> SileroTTSModel:
        key = self._cache_key(entry)
        if key in self._models:
            return self._models[key]

        logger.info(
            "provider_litserve.silero.tts.api.bundle.lang",
            api=entry.api_model_id,
            bundle=entry.silero_bundle,
            lang=entry.silero_language,
            device=self._device,
        )
        started = time.monotonic()
        model, _example_text = silero_tts(
            language=entry.silero_language,
            speaker=entry.silero_bundle,
            device=self._torch_device(),
        )
        self._models[key] = model
        logger.info("provider_litserve.silero.tts.s", api_model_id=entry.api_model_id, value_1=time.monotonic() - started)
        return model

    def warmup_pipeline(self, api_model_id: str | None) -> TTSWarmupInfo:
        """Загрузить веса Silero TTS без синтеза речи (только torch-модель).

        Вызывается из ``TTSLitAPI.setup`` для дефолтной модели каталога при старте воркера.
        ``api_model_id`` — api id из ``cfg.tts_models``; ``None`` — дефолт из конфига.
        """
        mid = (api_model_id or "").strip() or self._catalog.default_api_model_id("tts")
        if mid == "":
            raise ValueError(
                "TTS warmup: no ready tts entries in catalog"
            )
        entry = self._resolve_entry(mid)
        key = self._cache_key(entry)
        cached_before = key in self._models
        started = time.monotonic()
        _ = self._ensure_model(entry)
        elapsed = time.monotonic() - started
        return TTSWarmupInfo(
            api_model_id=entry.api_model_id,
            hf_model_id=entry.hf_model_id,
            silero_bundle=entry.silero_bundle,
            silero_language=entry.silero_language,
            cached_before=cached_before,
            load_seconds=round(elapsed, 3),
        )

    def synthesize(
        self,
        *,
        text: str,
        api_model_id: str,
        voice_override: str | None,
        response_format: Literal["pcm", "wav"],
        sample_rate_override: int | None,
    ) -> bytes:
        entry = self._resolve_entry(api_model_id)
        model = self._ensure_model(entry)
        voice_src = (
            voice_override if voice_override is not None else (entry.voice or "")
        )
        if not voice_src:
            raise ValueError(
                f"TTS: voice is not set (neither in payload nor in cfg.tts_models[{api_model_id}].voice)"
            )
        voice = _normalize_silero_speaker(voice_src)
        if not voice:
            raise ValueError("TTS: voice is empty after Unicode normalization")
        allowed_spk = SILERO_V5_RU_SPEAKERS_BY_BUNDLE[entry.silero_bundle]
        if voice not in allowed_spk:
            opts = ", ".join(sorted(allowed_spk))
            raise ValueError(
                f"TTS: speaker={voice!r} is not allowed for silero_bundle={entry.silero_bundle!r}: {opts}"
            )
        sample_rate = sample_rate_override if sample_rate_override is not None else entry.sample_rate
        if not sample_rate:
            raise ValueError(
                f"TTS: sample_rate is not set in cfg.tts_models[{api_model_id}].sample_rate"
            )
        if sample_rate not in (8000, 24000, 48000):
            raise ValueError("TTS: Silero ru v5 allows only sample_rate 8000, 24000 or 48000")

        silence_reason: str | None = None
        segment_count = 0
        text = sanitize_text_for_speech_backend(text).strip()
        if not text:
            silence_reason = "empty_after_unicode"
        else:
            text = apply_tts_input_steps(text, entry.tts_input_steps).strip()
            if not text:
                silence_reason = "empty_after_input_steps"
            elif entry.silero_language == "ru" and not _text_contains_cyrillic(text):
                silence_reason = "no_cyrillic_ru"

        if silence_reason is not None:
            logger.info(
                "provider_litserve.tts.model.reason.preview",
                model=api_model_id,
                reason=silence_reason,
                preview=text[:72] if text else '',
            )
            raw_pcm = _pcm16_silence(sample_rate=sample_rate)
        else:
            segments = _split_text_for_silero_apply(
                text, max_chars=_SILERO_APPLY_TTS_MAX_CHARS
            )
            if not segments:
                silence_reason = "empty_after_segmentation"
                raw_pcm = _pcm16_silence(sample_rate=sample_rate)
                segment_count = 0
            else:
                segment_count = len(segments)
                pcm_parts: list[bytes] = []
                try:
                    for seg in segments:
                        audio = model.apply_tts(
                            text=seg, speaker=voice, sample_rate=sample_rate
                        )
                        pcm_parts.append(_audio_to_pcm16_le(audio))
                except ValueError as exc:
                    if not exc.args:
                        message = (
                            "TTS Silero: не удалось разобрать текст для модели "
                            + "(нет допустимых символов после фильтрации по алфавиту модели)."
                        )
                        raise ValueError(message) from exc
                    raise
                except Exception as exc:
                    logger.exception("provider_litserve.tts.model", model=api_model_id, exc=exc)
                    raise
                raw_pcm = b"".join(pcm_parts)

        if response_format == "pcm":
            payload = raw_pcm
        else:
            payload = _pcm_to_wav(raw_pcm, sample_rate=sample_rate)

        logger.info(
            "provider_litserve.tts.model.chars.segments.bytes",
            model=api_model_id,
            chars=len(text) if text else 0,
            segments=segment_count,
            bytes=len(payload),
            silence_reason=silence_reason or '-',
        )
        return payload


_shared_tts_engine: LocalTTSEngine | None = None
_shared_tts_engine_key: tuple[int, int] | None = None


def get_local_tts_engine(cfg: ProviderLitserveInfraConfig, catalog: ModelCatalog) -> LocalTTSEngine:
    """Один ``LocalTTSEngine`` на процесс воркера LitServe (кэш моделей общий)."""
    global _shared_tts_engine, _shared_tts_engine_key
    key = (id(cfg), id(catalog))
    if _shared_tts_engine is None or _shared_tts_engine_key != key:
        _shared_tts_engine = LocalTTSEngine(cfg, catalog)
        _shared_tts_engine_key = key
    return _shared_tts_engine


def reset_local_tts_engine_for_tests() -> None:
    """Только для тестов: сбросить singleton (изолировать процессы)."""
    global _shared_tts_engine, _shared_tts_engine_key
    _shared_tts_engine = None
    _shared_tts_engine_key = None
