"""Движок для локального TTS в provider_litserve.

Список доступных моделей и их параметры (для Kokoro поле конфига ``lang`` —
``lang_code`` у ``kokoro.KPipeline``, не ISO; см. README hexgrad/kokoro), ``voice``, ``sample_rate``,
HF-id, опциональная ``revision``) берутся из ``cfg.tts_models``. Дефолт —
``cfg.tts_default_api_model_id``. Никаких хардкодов модели в коде.

Реализация бэкенда (Kokoro) выбирается через дефолт из конфига; в дальнейшем
при добавлении новых TTS-моделей в ``cfg.tts_models`` сюда же подключаются
их адаптеры — диспатч по api_model_id.
"""

from __future__ import annotations

import io
import time
import wave
from typing import Any

from apps.provider_litserve.model_registry import find_tts_entry
from apps.provider_litserve.runtime_models import (
    allowed_api_model_ids,
    resolve_hf_model_id,
)
from core.config.models import (
    ProviderLitserveInfraConfig,
    ProviderLitserveTTSModelEntry,
)
from core.logging import get_logger

logger = get_logger(__name__)


def parse_tts_body(raw: Any, *, default_api_model_id: str) -> dict[str, Any]:
    """Разобрать тело TTS-запроса (OpenAI-совместимое).

    Поля: ``input`` (текст), ``model`` (опционально, api id из
    ``cfg.tts_models``), ``voice`` (опционально, переопределяет дефолт
    модели), ``response_format`` (``pcm``|``wav``).
    """
    if not isinstance(raw, dict):
        raise ValueError("TTS: тело запроса должно быть JSON-объектом")
    text = str(raw.get("input") or "").strip()
    if not text:
        raise ValueError("TTS: поле input обязательно и не должно быть пустым")

    requested_model = str(raw.get("model") or "").strip()
    if requested_model == "":
        requested_model = default_api_model_id.strip()
    if requested_model == "":
        raise ValueError(
            "TTS: model обязателен (либо явно в payload, либо tts_default_api_model_id в конфиге)"
        )

    voice_override = str(raw.get("voice") or "").strip() or None
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


class LocalTTSEngine:
    """Multi-model TTS-движок: загружает требуемую модель из ``cfg.tts_models``."""

    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        self._cfg = cfg
        self._pipelines: dict[tuple[str, str, str | None], Any] = {}
        self._device = "cpu"

    def setup(self, device: str | None) -> None:
        self._device = device or "cpu"

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

    def _ensure_pipeline(self, entry: ProviderLitserveTTSModelEntry) -> Any:
        cache_key = (entry.hf_model_id, entry.lang or "", entry.revision or "")
        if cache_key in self._pipelines:
            return self._pipelines[cache_key]
        if not entry.lang:
            raise ValueError(
                f"TTS: для api_model_id={entry.api_model_id!r} не указан lang в cfg.tts_models"
            )
        try:
            from kokoro import KPipeline
        except ImportError as exc:
            raise RuntimeError(
                "TTS: установите зависимость kokoro (uv add kokoro --group rag)"
            ) from exc

        logger.info(
            "Загрузка TTS-pipeline: api=%s hf=%s lang=%s device=%s",
            entry.api_model_id,
            entry.hf_model_id,
            entry.lang,
            self._device,
        )
        started = time.monotonic()
        pipeline = KPipeline(
            lang_code=entry.lang,
            repo_id=entry.hf_model_id,
            device=self._device if self._device else None,
        )
        self._pipelines[cache_key] = pipeline
        logger.info(
            "TTS-pipeline %s загружен за %.2fs",
            entry.api_model_id,
            time.monotonic() - started,
        )
        return pipeline

    def warmup_pipeline(self, api_model_id: str | None) -> dict[str, Any]:
        """Загрузить KPipeline в память без синтеза речи.

        Вызывается из ``TTSLitAPI.setup`` для ``tts_default_api_model_id`` при старте воркера.
        ``api_model_id`` — api id из ``cfg.tts_models``; ``None`` — дефолт из конфига.
        """
        mid = (api_model_id or "").strip() or self._cfg.tts_default_api_model_id.strip()
        if mid == "":
            raise ValueError(
                "TTS warmup: задайте tts_default_api_model_id и непустой список tts_models в infra"
            )
        entry = self._resolve_entry(mid)
        cache_key = (entry.hf_model_id, entry.lang or "", entry.revision or "")
        cached_before = cache_key in self._pipelines
        started = time.monotonic()
        self._ensure_pipeline(entry)
        elapsed = time.monotonic() - started
        return {
            "api_model_id": entry.api_model_id,
            "hf_model_id": entry.hf_model_id,
            "lang": entry.lang,
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
        pipeline = self._ensure_pipeline(entry)
        voice = voice_override or entry.voice
        if not voice:
            raise ValueError(
                f"TTS: voice не задан (ни в payload, ни в cfg.tts_models[{api_model_id}].voice)"
            )
        sample_rate = entry.sample_rate
        if not sample_rate:
            raise ValueError(
                f"TTS: sample_rate не задан в cfg.tts_models[{api_model_id}].sample_rate"
            )

        started = time.monotonic()
        audio_chunks: list[bytes] = []
        try:
            for _, _, audio in pipeline(text, voice=voice):
                if audio is None:
                    continue
                try:
                    import numpy as np
                    if hasattr(audio, "numpy"):
                        arr = audio.numpy()
                    else:
                        arr = np.array(audio, dtype=np.float32)
                    pcm16 = (arr * 32767).clip(-32768, 32767).astype(np.int16)
                    audio_chunks.append(pcm16.tobytes())
                except Exception:
                    audio_chunks.append(bytes(audio))
        except Exception as exc:
            logger.exception("TTS ошибка синтеза (model=%s): %s", api_model_id, exc)
            raise

        if not audio_chunks:
            raise ValueError(f"TTS: модель {api_model_id} не вернула аудио для текста: {text[:50]!r}")

        raw_pcm = b"".join(audio_chunks)
        if response_format == "pcm":
            payload = raw_pcm
        else:
            payload = _pcm_to_wav(raw_pcm, sample_rate=sample_rate)

        logger.info(
            "TTS синтез: model=%s chars=%d bytes=%d duration=%.2fs",
            api_model_id,
            len(text),
            len(payload),
            time.monotonic() - started,
        )
        return payload


_shared_tts_engine: LocalTTSEngine | None = None
_shared_tts_engine_cfg_id: int | None = None


def get_local_tts_engine(cfg: ProviderLitserveInfraConfig) -> LocalTTSEngine:
    """Один ``LocalTTSEngine`` на процесс воркера LitServe (кэш KPipeline общий для speech и warmup)."""
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
