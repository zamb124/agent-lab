"""Движок для локального TTS в provider_litserve.

Параметры моделей (``silero_bundle``, ``silero_language``, ``voice``, ``sample_rate``,
``hf_model_id``, опциональная ``revision``) берутся из ``cfg.tts_models``. Дефолт —
``cfg.tts_default_api_model_id``. Никаких хардкодов выбранной модели в коде.

Бэкенд — Silero TTS (``silero.silero_tts`` + ``apply_tts``) по ``api_model_id`` из конфига.
Один HTTP-запрос может синтезировать длинный текст: строка режется на сегменты (до 900 символов,
граница по пробелу при возможности), PCM16 от каждого ``apply_tts`` склеивается в один поток.
"""

from __future__ import annotations

import io
import time
import wave
from typing import Any

import numpy as np
import torch
from silero import silero_tts

from apps.provider_litserve.model_registry import find_tts_entry
from apps.provider_litserve.runtime_models import (
    allowed_api_model_ids,
    resolve_hf_model_id,
)
from core.config.models import (
    SILERO_V5_RU_SPEAKERS_BY_BUNDLE,
    ProviderLitserveInfraConfig,
    ProviderLitserveTTSModelEntry,
)
from core.logging import get_logger
from core.utils.text_sanitize import sanitize_text_for_speech_backend
from core.utils.tts_input_steps import apply_tts_input_steps

logger = get_logger(__name__)


def _text_contains_cyrillic(text: str) -> bool:
    return any("\u0400" <= c <= "\u04ff" for c in text)


def _normalize_silero_speaker(name: str) -> str:
    return sanitize_text_for_speech_backend(name).strip().lower()


def parse_tts_body(raw: Any, *, default_api_model_id: str) -> dict[str, Any]:
    """Разобрать тело TTS-запроса (OpenAI-совместимое).

    Поля: ``input`` (текст), ``model`` (опционально, api id из
    ``cfg.tts_models``), ``voice`` (опционально, переопределяет дефолт
    модели), ``response_format`` (``pcm``|``wav``).
    """
    if not isinstance(raw, dict):
        raise ValueError("TTS: тело запроса должно быть JSON-объектом")
    raw_input = str(raw.get("input") or "").strip()
    text = sanitize_text_for_speech_backend(raw_input).strip()
    if not text:
        if raw_input:
            raise ValueError(
                "TTS: поле input не содержит допустимых символов Unicode после нормализации"
            )
        raise ValueError("TTS: поле input обязательно и не должно быть пустым")

    requested_model = str(raw.get("model") or "").strip()
    if requested_model == "":
        requested_model = default_api_model_id.strip()
    if requested_model == "":
        raise ValueError(
            "TTS: model обязателен (либо явно в payload, либо tts_default_api_model_id в конфиге)"
        )

    raw_voice = str(raw.get("voice") or "").strip()
    voice_override: str | None
    if raw_voice:
        v = sanitize_text_for_speech_backend(raw_voice).strip()
        voice_override = _normalize_silero_speaker(v) if v else None
    else:
        voice_override = None
    response_format = str(raw.get("response_format") or "wav").strip().lower()
    if response_format not in {"pcm", "wav", "mp3"}:
        response_format = "wav"
    return {
        "text": text,
        "model": requested_model,
        "voice_override": voice_override,
        "response_format": response_format,
    }


def _pcm_to_wav(pcm_bytes: bytes, *, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _audio_to_pcm16_le(audio: Any) -> bytes:
    if audio is None:
        raise ValueError("TTS: apply_tts вернул None")
    arr = audio
    if hasattr(audio, "detach"):
        arr = audio.detach().cpu().numpy()
    else:
        arr = np.asarray(arr)
    if arr.dtype == np.int16:
        return arr.tobytes()
    if arr.dtype in (np.float32, np.float64):
        arr_f = arr.astype(np.float32, copy=False)
        pcm16 = (arr_f * 32767.0).clip(-32768, 32767).astype(np.int16)
        return pcm16.tobytes()
    raise ValueError(f"TTS: неподдерживаемый dtype аудио: {arr.dtype}")


def _pcm16_silence(*, sample_rate: int, duration_ms: int = 40) -> bytes:
    frames = max(1, int(sample_rate * duration_ms / 1000))
    return b"\x00\x00" * frames


# Silero предупреждает при >1000 символов; внутри TorchScript падает pos_encoder (5000 vs длиннее).
_SILERO_APPLY_TTS_MAX_CHARS = 900


def _split_text_for_silero_apply(text: str, *, max_chars: int) -> list[str]:
    if max_chars < 1:
        raise ValueError("TTS: max_chars для сегментации должен быть >= 1")
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
    """Multi-model TTS: загрузка Silero по записи ``cfg.tts_models``."""

    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        self._cfg = cfg
        self._models: dict[tuple[str, str, str, str], Any] = {}
        self._device: str = "cpu"

    def setup(self, device: str | None) -> None:
        self._device = device or "cpu"

    def _torch_device(self) -> torch.device:
        d = (self._device or "cpu").strip()
        if d == "cpu" or d == "":
            return torch.device("cpu")
        if d == "mps":
            return torch.device("mps")
        if d.startswith("cuda"):
            return torch.device(d)
        return torch.device(d)

    def _resolve_entry(self, requested_api_model_id: str) -> ProviderLitserveTTSModelEntry:
        allowed = allowed_api_model_ids("tts", self._cfg)
        hf = resolve_hf_model_id("tts", requested_api_model_id, self._cfg)
        if hf is None:
            raise ValueError(
                f"TTS: неизвестная модель {requested_api_model_id!r}; "
                f"доступные: {sorted(allowed)}"
            )
        entry = find_tts_entry(self._cfg, requested_api_model_id)
        if entry is None:
            raise ValueError(
                f"TTS: для api_model_id={requested_api_model_id!r} нет entry в cfg.tts_models "
                "(должна быть синхронизация с реестром)"
            )
        return entry

    def _cache_key(self, entry: ProviderLitserveTTSModelEntry) -> tuple[str, str, str, str]:
        return (
            entry.silero_language,
            entry.silero_bundle,
            entry.revision or "",
            self._device,
        )

    def _ensure_model(self, entry: ProviderLitserveTTSModelEntry) -> Any:
        key = self._cache_key(entry)
        if key in self._models:
            return self._models[key]

        logger.info(
            "Загрузка Silero TTS: api=%s bundle=%s lang=%s device=%s",
            entry.api_model_id,
            entry.silero_bundle,
            entry.silero_language,
            self._device,
        )
        started = time.monotonic()
        silero_result = silero_tts(
            language=entry.silero_language,
            speaker=entry.silero_bundle,
            device=self._torch_device(),
        )
        if not isinstance(silero_result, tuple) or len(silero_result) < 2:
            raise RuntimeError("silero_tts вернул некорректный результат")
        model = silero_result[0]
        self._models[key] = model
        logger.info(
            "Silero TTS %s загружен за %.2fs",
            entry.api_model_id,
            time.monotonic() - started,
        )
        return model

    def warmup_pipeline(self, api_model_id: str | None) -> dict[str, Any]:
        """Загрузить веса Silero TTS без синтеза речи (только torch-модель).

        Вызывается из ``TTSLitAPI.setup`` для ``tts_default_api_model_id`` при старте воркера.
        ``api_model_id`` — api id из ``cfg.tts_models``; ``None`` — дефолт из конфига.
        """
        mid = (api_model_id or "").strip() or self._cfg.tts_default_api_model_id.strip()
        if mid == "":
            raise ValueError(
                "TTS warmup: задайте tts_default_api_model_id и непустой список tts_models в infra"
            )
        entry = self._resolve_entry(mid)
        key = self._cache_key(entry)
        cached_before = key in self._models
        started = time.monotonic()
        self._ensure_model(entry)
        elapsed = time.monotonic() - started
        return {
            "api_model_id": entry.api_model_id,
            "hf_model_id": entry.hf_model_id,
            "silero_bundle": entry.silero_bundle,
            "silero_language": entry.silero_language,
            "cached_before": cached_before,
            "load_seconds": round(elapsed, 3),
        }

    def synthesize(
        self,
        *,
        text: str,
        api_model_id: str,
        voice_override: str | None,
        response_format: str,
    ) -> bytes:
        entry = self._resolve_entry(api_model_id)
        model = self._ensure_model(entry)
        voice_src = (
            voice_override if voice_override is not None else (entry.voice or "")
        )
        if not voice_src:
            raise ValueError(
                f"TTS: voice не задан (ни в payload, ни в cfg.tts_models[{api_model_id}].voice)"
            )
        voice = _normalize_silero_speaker(voice_src)
        if not voice:
            raise ValueError("TTS: voice пуст после нормализации Unicode")
        allowed_spk = SILERO_V5_RU_SPEAKERS_BY_BUNDLE[entry.silero_bundle]
        if voice not in allowed_spk:
            opts = ", ".join(sorted(allowed_spk))
            raise ValueError(
                f"TTS: speaker={voice!r} не из допустимых для silero_bundle={entry.silero_bundle!r}: {opts}"
            )
        sample_rate = entry.sample_rate
        if not sample_rate:
            raise ValueError(
                f"TTS: sample_rate не задан в cfg.tts_models[{api_model_id}].sample_rate"
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
            elif entry.silero_language == "ru" and not _text_contains_cyrillic(text):
                silence_reason = "no_cyrillic_ru"

        if silence_reason is not None:
            logger.info(
                "TTS тишина вместо синтеза: model=%s reason=%s preview=%r",
                api_model_id,
                silence_reason,
                (text[:72] if text else ""),
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
                        raise ValueError(
                            "TTS Silero: не удалось разобрать текст для модели "
                            "(нет допустимых символов после фильтрации по алфавиту модели)."
                        ) from exc
                    raise
                except Exception as exc:
                    logger.exception(
                        "TTS ошибка синтеза (model=%s): %s", api_model_id, exc
                    )
                    raise
                raw_pcm = b"".join(pcm_parts)

        if response_format == "pcm":
            payload = raw_pcm
        else:
            payload = _pcm_to_wav(raw_pcm, sample_rate=sample_rate)

        logger.info(
            "TTS синтез: model=%s chars=%d segments=%d bytes=%d silence_reason=%s",
            api_model_id,
            len(text) if text else 0,
            segment_count,
            len(payload),
            silence_reason or "-",
        )
        return payload


_shared_tts_engine: LocalTTSEngine | None = None
_shared_tts_engine_cfg_id: int | None = None


def get_local_tts_engine(cfg: ProviderLitserveInfraConfig) -> LocalTTSEngine:
    """Один ``LocalTTSEngine`` на процесс воркера LitServe (кэш моделей общий)."""
    global _shared_tts_engine, _shared_tts_engine_cfg_id
    cid = id(cfg)
    if _shared_tts_engine is None or _shared_tts_engine_cfg_id != cid:
        _shared_tts_engine = LocalTTSEngine(cfg)
        _shared_tts_engine_cfg_id = cid
    return _shared_tts_engine


def reset_local_tts_engine_for_tests() -> None:
    """Только для тестов: сбросить singleton (изолировать процессы)."""
    global _shared_tts_engine, _shared_tts_engine_cfg_id
    _shared_tts_engine = None
    _shared_tts_engine_cfg_id = None
