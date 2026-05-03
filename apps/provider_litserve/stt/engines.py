"""Движок для локального STT в provider_litserve.

Список доступных моделей и их параметры (HF id, revision, backend) —
в ``cfg.stt_models``. Дефолт — ``cfg.stt_default_api_model_id``.

Backend выбирается полем ``entry.backend``:

* ``gigaam`` — модели семейства ``ai-sage/GigaAM-v3`` (AutoModel +
  ``trust_remote_code=True``, метод ``model.transcribe(file)`` с временным
  WAV-файлом).
* ``huggingface_ctc`` — generic CTC-модели через ``AutoModelForCTC`` +
  ``AutoProcessor`` (например wav2vec2).
* ``whisper`` — Whisper-семейство через ``AutoModelForSpeechSeq2Seq``.

Адаптеры лениво кэшируют веса по ``(hf_model_id, revision)``. Никаких
хардкодов конкретных моделей в коде — всё из ``cfg.stt_models``.
"""

from __future__ import annotations

import io
import os
import struct
import tempfile
import time
import wave
from typing import Any

import torch  # pyright: ignore[reportMissingImports]
from fastapi import HTTPException  # pyright: ignore[reportMissingImports]

from apps.provider_litserve.model_registry import find_stt_entry
from apps.provider_litserve.runtime_models import (
    allowed_api_model_ids,
    resolve_hf_model_id,
)
from core.config.models import (
    ProviderLitserveInfraConfig,
    ProviderLitserveSTTModelEntry,
)
from core.logging import get_logger

logger = get_logger(__name__)


def _require_cuda_when_selected(device: str) -> None:
    if not device.startswith("cuda"):
        return
    if not torch.cuda.is_available():
        raise RuntimeError(
            "provider_litserve STT: CUDA недоступен (torch.cuda.is_available() == False); "
            "нужны драйвер NVIDIA на хосте, NVIDIA Container Toolkit и "
            "resources.limits.nvidia.com/gpu."
        )


def parse_stt_body(raw: Any, *, default_api_model_id: str) -> dict[str, Any]:
    """Разобрать тело STT-запроса.

    Поля: ``file`` (или ``audio``) — байты аудио, ``model`` (опционально) —
    api id из ``cfg.stt_models``, ``language`` (опционально, для Whisper).
    """
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="STT: тело запроса должно быть объектом")
    audio_bytes = raw.get("file") or raw.get("audio")
    if not audio_bytes:
        raise HTTPException(status_code=422, detail="STT: поле file обязательно")
    if not isinstance(audio_bytes, bytes):
        audio_bytes = bytes(audio_bytes)

    requested_model = str(raw.get("model") or "").strip()
    if requested_model == "":
        requested_model = default_api_model_id.strip()
    if requested_model == "":
        raise HTTPException(
            status_code=422,
            detail="STT: model обязателен (либо явно в payload, либо stt_default_api_model_id в конфиге)",
        )

    language = str(raw.get("language") or "").strip() or None
    return {"audio_bytes": audio_bytes, "model": requested_model, "language": language}


def _decode_audio_to_floats(audio_bytes: bytes) -> tuple[list[float], int]:
    """Универсальный декод: пробуем soundfile (mp3/wav/ogg/flac), иначе PCM-16 16kHz.

    ``soundfile`` лежит в опциональной группе ``rag`` (ставится только в
    litserve-pod), поэтому импорт ленивый и помечен ``type: ignore``,
    чтобы статический анализатор IDE не ругался.
    """
    try:
        import soundfile as sf  # type: ignore[import-not-found]
    except ImportError:
        sf = None

    if sf is not None:
        try:
            buf = io.BytesIO(audio_bytes)
            data, sr = sf.read(buf, dtype="float32", always_2d=False)
            if data.ndim == 2:
                data = data.mean(axis=1)
            return data.tolist(), int(sr)
        except (RuntimeError, ValueError):
            pass

    n_samples = len(audio_bytes) // 2
    if n_samples == 0:
        raise ValueError("STT: пустые аудио-данные")
    samples = struct.unpack(f"<{n_samples}h", audio_bytes[: n_samples * 2])
    return [s / 32768.0 for s in samples], 16000


def _write_temp_wav(floats: list[float], sample_rate: int) -> str:
    """Сохраняет PCM-16 WAV во временный файл и возвращает путь."""
    fd, path = tempfile.mkstemp(suffix=".wav", prefix="stt_in_")
    os.close(fd)
    pcm16 = bytearray()
    for f in floats:
        v = max(-1.0, min(1.0, f))
        pcm16 += int(v * 32767).to_bytes(2, "little", signed=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(pcm16))
    return path


class _BaseSTTAdapter:
    backend: str = ""

    def __init__(self, cfg: ProviderLitserveInfraConfig, device: str) -> None:
        self._cfg = cfg
        self._device = device

    def load(self, hf_model_id: str, revision: str | None) -> Any:
        raise NotImplementedError

    def transcribe(self, model_obj: Any, audio_bytes: bytes, language: str | None) -> str:
        raise NotImplementedError


class _GigaAMAdapter(_BaseSTTAdapter):
    backend = "gigaam"

    def load(self, hf_model_id: str, revision: str | None) -> Any:
        try:
            from transformers import AutoModel  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "STT gigaam: установите transformers (uv sync --group rag)"
            ) from exc
        _require_cuda_when_selected(self._device)
        logger.info("STT gigaam: загрузка hf=%s revision=%s device=%s", hf_model_id, revision, self._device)
        started = time.monotonic()
        model = AutoModel.from_pretrained(
            hf_model_id,
            revision=revision,
            trust_remote_code=True,
            token=self._cfg.hf_token,
        )
        try:
            model.to(self._device)
        except Exception:  # noqa: BLE001 - GigaAM сам управляет device через .transcribe
            pass
        logger.info("STT gigaam: %s загружен за %.2fs", hf_model_id, time.monotonic() - started)
        return model

    def transcribe(self, model_obj: Any, audio_bytes: bytes, language: str | None) -> str:
        floats, sr = _decode_audio_to_floats(audio_bytes)
        wav_path = _write_temp_wav(floats, sr if sr in (8000, 16000) else 16000)
        try:
            text = model_obj.transcribe(wav_path)
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass
        return str(text).strip()


class _HuggingfaceCTCAdapter(_BaseSTTAdapter):
    backend = "huggingface_ctc"

    def load(self, hf_model_id: str, revision: str | None) -> tuple[Any, Any]:
        try:
            from transformers import AutoModelForCTC, AutoProcessor  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "STT huggingface_ctc: установите transformers (uv sync --group rag)"
            ) from exc
        _require_cuda_when_selected(self._device)
        logger.info(
            "STT huggingface_ctc: загрузка hf=%s revision=%s device=%s",
            hf_model_id, revision, self._device,
        )
        started = time.monotonic()
        processor = AutoProcessor.from_pretrained(hf_model_id, revision=revision, token=self._cfg.hf_token)
        model = AutoModelForCTC.from_pretrained(
            hf_model_id,
            revision=revision,
            token=self._cfg.hf_token,
            torch_dtype=torch.float16 if self._device.startswith("cuda") else torch.float32,
        )
        model.to(self._device)
        model.eval()
        logger.info("STT huggingface_ctc: %s загружен за %.2fs", hf_model_id, time.monotonic() - started)
        return processor, model

    def transcribe(self, model_obj: tuple[Any, Any], audio_bytes: bytes, language: str | None) -> str:
        processor, model = model_obj
        floats, sr = _decode_audio_to_floats(audio_bytes)
        inputs = processor(floats, sampling_rate=sr, return_tensors="pt", padding=True)
        input_values = inputs.input_values.to(self._device)
        attn = inputs.get("attention_mask")
        if attn is not None:
            attn = attn.to(self._device)
        with torch.no_grad():
            logits = model(input_values=input_values, attention_mask=attn).logits
        ids = torch.argmax(logits, dim=-1)
        return processor.batch_decode(ids)[0].strip()


class _WhisperAdapter(_BaseSTTAdapter):
    backend = "whisper"

    def load(self, hf_model_id: str, revision: str | None) -> Any:
        try:
            from transformers import (  # type: ignore[import-not-found]
                AutoModelForSpeechSeq2Seq,
                AutoProcessor,
                pipeline,
            )
        except ImportError as exc:
            raise RuntimeError(
                "STT whisper: установите transformers (uv sync --group rag)"
            ) from exc
        _require_cuda_when_selected(self._device)
        logger.info("STT whisper: загрузка hf=%s revision=%s device=%s", hf_model_id, revision, self._device)
        started = time.monotonic()
        processor = AutoProcessor.from_pretrained(hf_model_id, revision=revision, token=self._cfg.hf_token)
        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            hf_model_id,
            revision=revision,
            token=self._cfg.hf_token,
            torch_dtype=torch.float16 if self._device.startswith("cuda") else torch.float32,
        )
        model.to(self._device)
        pipe = pipeline(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            device=self._device,
        )
        logger.info("STT whisper: %s загружен за %.2fs", hf_model_id, time.monotonic() - started)
        return pipe

    def transcribe(self, model_obj: Any, audio_bytes: bytes, language: str | None) -> str:
        floats, sr = _decode_audio_to_floats(audio_bytes)
        kwargs: dict[str, Any] = {"sampling_rate": sr}
        if language:
            kwargs["generate_kwargs"] = {"language": language}
        result = model_obj({"raw": floats, "sampling_rate": sr}, **{k: v for k, v in kwargs.items() if k != "sampling_rate"})
        return str(result.get("text", "")).strip()


_ADAPTERS: dict[str, type[_BaseSTTAdapter]] = {
    "gigaam": _GigaAMAdapter,
    "huggingface_ctc": _HuggingfaceCTCAdapter,
    "whisper": _WhisperAdapter,
}


class LocalSTTEngine:
    """Multi-backend STT-движок: загружает требуемую модель из ``cfg.stt_models``."""

    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        self._cfg = cfg
        self._device = "cpu"
        self._loaded: dict[tuple[str, str, str], Any] = {}  # (backend, hf_id, revision) -> model_obj

    def setup(self, device: str | None) -> None:
        self._device = device or "cpu"

    def _resolve_entry(self, requested_api_model_id: str) -> ProviderLitserveSTTModelEntry:
        allowed = allowed_api_model_ids("stt", self._cfg)
        hf = resolve_hf_model_id("stt", requested_api_model_id, self._cfg)
        if hf is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "reason": "unknown_stt_model",
                    "model": requested_api_model_id,
                    "allowed": sorted(allowed),
                },
            )
        entry = find_stt_entry(self._cfg, requested_api_model_id)
        if entry is None:
            raise HTTPException(
                status_code=422,
                detail=f"STT: для api_model_id={requested_api_model_id!r} нет entry в cfg.stt_models",
            )
        return entry

    def _ensure_loaded(self, entry: ProviderLitserveSTTModelEntry) -> tuple[_BaseSTTAdapter, Any]:
        adapter_cls = _ADAPTERS.get(entry.backend)
        if adapter_cls is None:
            raise HTTPException(
                status_code=422,
                detail=f"STT: неизвестный backend={entry.backend!r} (доступно: {sorted(_ADAPTERS)})",
            )
        adapter = adapter_cls(self._cfg, self._device)
        cache_key = (entry.backend, entry.hf_model_id, entry.revision or "")
        if cache_key in self._loaded:
            return adapter, self._loaded[cache_key]
        model_obj = adapter.load(entry.hf_model_id, entry.revision)
        self._loaded[cache_key] = model_obj
        return adapter, model_obj

    def transcribe_batch(self, items: list[dict[str, Any]]) -> list[str]:
        results: list[str] = []
        for item in items:
            audio_bytes: bytes = item["audio_bytes"]
            requested_model: str = item["model"]
            language: str | None = item.get("language")
            started = time.monotonic()

            entry = self._resolve_entry(requested_model)
            adapter, model_obj = self._ensure_loaded(entry)
            text = adapter.transcribe(model_obj, audio_bytes, language)
            results.append(text)
            logger.info(
                "STT транскрипция: model=%s backend=%s chars=%d duration=%.2fs",
                requested_model,
                entry.backend,
                len(text),
                time.monotonic() - started,
            )
        return results
