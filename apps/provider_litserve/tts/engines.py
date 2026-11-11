"""Движок для локального TTS в provider_litserve.

Бэкенд — Qwen3-TTS CustomVoice (``qwen_tts.Qwen3TTSModel.generate_custom_voice``):
пресетные спикеры checkpoint-а, опциональная стилевая инструкция ``instruct``
и 10 языков, включая русский. Параметры моделей (``voice``, ``synthesis_locale``,
``sample_rate``, ``instruct``, ``hf_model_id``, ``revision``) берутся из записей
каталога ``ProviderLitserveTTSModelEntry``. Дефолт — самая старая ready-запись.

Один HTTP-запрос может синтезировать длинный текст: строка режется на сегменты
(до 900 символов, граница по пробелу при возможности), waveform от каждого вызова
склеивается в один поток. Нативный выход модели — float32 @ 24 kHz; при запросе
другой частоты применяется ``torchaudio.functional.resample``.
"""

from __future__ import annotations

import io
import time
import wave
from collections.abc import Mapping
from typing import ClassVar, Literal, Protocol, TypeAlias

import numpy as np
import torch
import torchaudio  # pyright: ignore[reportMissingTypeStubs] — пакет без stub-ов
from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field
from qwen_tts import Qwen3TTSModel  # pyright: ignore[reportMissingTypeStubs] — пакет без stub-ов

from apps.provider_litserve.catalog import ModelCatalog
from core.config.models import (
    LITSERVE_TTS_SAMPLE_RATE_IDS,
    QWEN3_TTS_CUSTOM_VOICE_SPEAKERS,
    QWEN3_TTS_LANGUAGE_BY_LOCALE,
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


_qwen_tts_encoder_compat_applied = False


def _apply_qwen_tts_encoder_compat() -> None:
    """Обход read-only @property ``MimiModel`` на transformers 5.x.

    Вендорный ``Qwen3TTSTokenizerV2Encoder.__init__`` присваивает ``None`` в
    ``self.upsample``/``self.decoder_transformer`` — на transformers>=5 это
    deprecated read-only @property (делегируют в ``self.decoder.*``), и
    присваивание падает с ``AttributeError``. Здесь повторяем исходный
    смысл — освободить decoder-половину Mimi, построенную ``super().__init__``:
    ``decoder_transformer`` вынимается из ``_modules``, ``self.decoder``
    зануляется. Upstream: vendored tokenizer_12hz пакета ``qwen-tts-compat``.
    """
    global _qwen_tts_encoder_compat_applied
    if _qwen_tts_encoder_compat_applied:
        return
    from qwen_tts.core.tokenizer_12hz.modeling_qwen3_tts_tokenizer_v2 import (  # pyright: ignore[reportMissingTypeStubs] — пакет без stub-ов
        Qwen3TTSTokenizerV2Encoder,
    )
    from transformers.models.mimi.configuration_mimi import MimiConfig
    from transformers.models.mimi.modeling_mimi import MimiModel

    def _init(self: Qwen3TTSTokenizerV2Encoder, config: MimiConfig) -> None:
        MimiModel.__init__(self, config)
        self.config = config
        _ = self._modules.pop("decoder_transformer", None)  # pyright: ignore[reportPrivateUsage] — обход read-only property transformers 5.x
        self.decoder = None
        self.post_init()

    Qwen3TTSTokenizerV2Encoder.__init__ = _init
    _qwen_tts_encoder_compat_applied = True


class LocalTTSModel(Protocol):
    """Срез ``qwen_tts.Qwen3TTSModel``, используемый движком."""

    def generate_custom_voice(
        self,
        text: str,
        speaker: str,
        language: str,
        instruct: str | None = None,
    ) -> tuple[list[np.ndarray], int]: ...


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
    cached_before: bool
    load_seconds: float


def _normalize_speaker_id(name: str) -> str:
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
        voice_override = _normalize_speaker_id(v) if v else None
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


# Верхняя граница текста на один вызов синтеза: держит латентность и KV-память генерации
# в разумных пределах; сегменты склеиваются в один поток.
_TTS_MAX_SEGMENT_CHARS = 900


def _split_text_for_synthesis(text: str, *, max_chars: int) -> list[str]:
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
        self._models: dict[tuple[str, str, str], LocalTTSModel] = {}
        self._device: str = "cpu"

    def setup(self, device: str | None) -> None:
        self._device = device or "cpu"

    def _resolve_entry(self, requested_api_model_id: str) -> ProviderLitserveTTSModelEntry:
        entry = self._catalog.find_typed("tts", requested_api_model_id)
        if entry is None:
            message = (
                f"TTS: неизвестная модель {requested_api_model_id!r}; "
                + f"доступные: {sorted(self._catalog.allowed_ids('tts'))}"
            )
            raise ValueError(message)
        return entry

    def _cache_key(self, entry: ProviderLitserveTTSModelEntry) -> tuple[str, str, str]:
        return (entry.api_model_id, entry.hf_model_id, entry.revision or "")

    def _ensure_model(self, entry: ProviderLitserveTTSModelEntry) -> LocalTTSModel:
        key = self._cache_key(entry)
        if key in self._models:
            return self._models[key]

        logger.info(
            "provider_litserve.qwen.tts.api.device",
            api=entry.api_model_id,
            hf_model_id=entry.hf_model_id,
            device=self._device,
        )
        _apply_qwen_tts_encoder_compat()
        started = time.monotonic()
        model = Qwen3TTSModel.from_pretrained(  # pyright: ignore[reportUnknownMemberType] — пакет без stub-ов
            entry.hf_model_id,
            revision=entry.revision,
            device_map=self._device,
            dtype=torch.bfloat16 if self._device.startswith("cuda") else torch.float32,
            token=self._cfg.hf_token,
        )
        self._models[key] = model
        logger.info(
            "provider_litserve.qwen.tts.s",
            api_model_id=entry.api_model_id,
            value_1=time.monotonic() - started,
        )
        return model

    def warmup_pipeline(self, api_model_id: str | None) -> TTSWarmupInfo:
        """Загрузить веса TTS без синтеза речи.

        Вызывается из ``TTSLitAPI.setup`` для дефолтной модели каталога при старте воркера.
        ``api_model_id`` — api id записи каталога; ``None`` — дефолтная запись.
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
        voice_src = (
            voice_override if voice_override is not None else (entry.voice or "")
        )
        if not voice_src:
            raise ValueError(
                f"TTS: voice is not set (neither in payload nor in tts entry {api_model_id!r}.voice)"
            )
        voice = _normalize_speaker_id(voice_src)
        if not voice:
            raise ValueError("TTS: voice is empty after Unicode normalization")
        if voice not in QWEN3_TTS_CUSTOM_VOICE_SPEAKERS:
            opts = ", ".join(sorted(QWEN3_TTS_CUSTOM_VOICE_SPEAKERS))
            raise ValueError(f"TTS: speaker={voice!r} is not a CustomVoice speaker: {opts}")
        sample_rate = sample_rate_override if sample_rate_override is not None else entry.sample_rate
        if not sample_rate:
            raise ValueError(
                f"TTS: sample_rate is not set in tts entry {api_model_id!r}.sample_rate"
            )
        if sample_rate not in LITSERVE_TTS_SAMPLE_RATE_IDS:
            allowed = ", ".join(str(sr) for sr in LITSERVE_TTS_SAMPLE_RATE_IDS)
            raise ValueError(f"TTS: sample_rate={sample_rate}: allowed: {allowed}")
        language = (
            QWEN3_TTS_LANGUAGE_BY_LOCALE[entry.synthesis_locale]
            if entry.synthesis_locale is not None
            else "Auto"
        )
        silence_reason: str | None = None
        segment_count = 0
        text = sanitize_text_for_speech_backend(text).strip()
        if not text:
            silence_reason = "empty_after_unicode"
        else:
            text = apply_tts_input_steps(text, entry.tts_input_steps).strip()
            if not text:
                silence_reason = "empty_after_input_steps"

        if silence_reason is not None:
            logger.info(
                "provider_litserve.tts.model.reason.preview",
                model=api_model_id,
                reason=silence_reason,
                preview=text[:72] if text else '',
            )
            raw_pcm = _pcm16_silence(sample_rate=sample_rate)
        else:
            segments = _split_text_for_synthesis(text, max_chars=_TTS_MAX_SEGMENT_CHARS)
            if not segments:
                silence_reason = "empty_after_segmentation"
                raw_pcm = _pcm16_silence(sample_rate=sample_rate)
            else:
                segment_count = len(segments)
                model = self._ensure_model(entry)
                wav_parts: list[torch.Tensor] = []
                model_sample_rate = 0
                try:
                    for seg in segments:
                        wavs, fs = model.generate_custom_voice(
                            text=seg,
                            speaker=voice,
                            language=language,
                            instruct=entry.instruct,
                        )
                        model_sample_rate = fs
                        wav_parts.append(
                            torch.from_numpy(  # pyright: ignore[reportUnknownMemberType] — стабы torch не типизируют from_numpy
                                np.concatenate(wavs)
                            )
                        )
                except Exception as exc:
                    logger.exception("provider_litserve.tts.model", model=api_model_id, exc=exc)
                    raise
                audio = torch.cat(wav_parts).float()
                if model_sample_rate != sample_rate:
                    audio = torchaudio.functional.resample(
                        audio.unsqueeze(0), model_sample_rate, sample_rate
                    ).squeeze(0)
                raw_pcm = _audio_to_pcm16_le(audio)

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
