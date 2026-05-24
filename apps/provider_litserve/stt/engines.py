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
import tempfile
import time
import wave
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import (
    ClassVar,
    Generic,
    Literal,
    Protocol,
    TypeAlias,
    TypedDict,
    TypeVar,
    cast,
    override,
)

import soundfile as sf
import torch
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict
from transformers import (
    AutoModel,
    AutoModelForCTC,
    AutoModelForSpeechSeq2Seq,
    AutoProcessor,
    pipeline,
)

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
from core.types import JsonValue

logger = get_logger(__name__)

STTRawValue: TypeAlias = JsonValue | bytes | bytearray | memoryview
STTRawBody: TypeAlias = Mapping[str, STTRawValue]
STTBackend: TypeAlias = Literal["gigaam", "huggingface_ctc", "whisper"]
STTModelCacheKey: TypeAlias = tuple[str, str]
STTModelDTypeName: TypeAlias = Literal["float16", "float32"]
ModelT = TypeVar("ModelT")


class GigaAMModel(Protocol):
    def to(self, device: str) -> "GigaAMModel": ...

    def transcribe(self, wav_path: str) -> str: ...


class CTCProcessorBatch(Protocol):
    input_values: torch.Tensor

    def get(self, key: Literal["attention_mask"]) -> torch.Tensor | None: ...


class CTCProcessor(Protocol):
    def __call__(
        self,
        audio: Sequence[float],
        *,
        sampling_rate: int,
        return_tensors: Literal["pt"],
        padding: Literal[True],
    ) -> CTCProcessorBatch: ...

    def batch_decode(self, token_ids: torch.Tensor) -> Sequence[str]: ...


class CTCModelOutput(Protocol):
    logits: torch.Tensor


class CTCModel(Protocol):
    def to(self, device: str) -> "CTCModel": ...

    def eval(self) -> "CTCModel": ...

    def __call__(
        self,
        *,
        input_values: torch.Tensor,
        attention_mask: torch.Tensor | None,
    ) -> CTCModelOutput: ...


@dataclass(frozen=True, slots=True)
class CTCBundle:
    processor: CTCProcessor
    model: CTCModel


class WhisperTokenizer(Protocol): ...


class WhisperFeatureExtractor(Protocol): ...


class WhisperProcessor(Protocol):
    tokenizer: WhisperTokenizer
    feature_extractor: WhisperFeatureExtractor


class WhisperModel(Protocol):
    def to(self, device: str) -> "WhisperModel": ...


class WhisperPipelineInput(TypedDict):
    raw: list[float]
    sampling_rate: int


class WhisperGenerateKwargs(TypedDict):
    language: str


class WhisperPipelineResult(TypedDict):
    text: str


class WhisperASRPipeline(Protocol):
    def __call__(
        self,
        audio: WhisperPipelineInput,
        *,
        generate_kwargs: WhisperGenerateKwargs | None = None,
    ) -> WhisperPipelineResult: ...


class GigaAMModelLoader(Protocol):
    def __call__(
        self,
        hf_model_id: str,
        *,
        revision: str | None,
        trust_remote_code: bool,
        token: str | None,
    ) -> GigaAMModel: ...


class CTCProcessorLoader(Protocol):
    def __call__(self, hf_model_id: str, *, revision: str | None, token: str | None) -> CTCProcessor: ...


class CTCModelLoader(Protocol):
    def __call__(
        self,
        hf_model_id: str,
        *,
        revision: str | None,
        token: str | None,
        dtype: STTModelDTypeName,
    ) -> CTCModel: ...


class WhisperProcessorLoader(Protocol):
    def __call__(self, hf_model_id: str, *, revision: str | None, token: str | None) -> WhisperProcessor: ...


class WhisperModelLoader(Protocol):
    def __call__(
        self,
        hf_model_id: str,
        *,
        revision: str | None,
        token: str | None,
        dtype: STTModelDTypeName,
    ) -> WhisperModel: ...


class ASRPipelineFactory(Protocol):
    def __call__(
        self,
        task: Literal["automatic-speech-recognition"],
        *,
        model: WhisperModel,
        tokenizer: WhisperTokenizer,
        feature_extractor: WhisperFeatureExtractor,
        device: str,
    ) -> WhisperASRPipeline: ...


class STTTranscriptionInput(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    audio_bytes: bytes
    model: str
    language: str | None = None


def _require_cuda_when_selected(device: str) -> None:
    if not device.startswith("cuda"):
        return
    if not torch.cuda.is_available():
        message = (
            "provider_litserve STT: CUDA недоступен (torch.cuda.is_available() == False); "
            "нужны драйвер NVIDIA на хосте, NVIDIA Container Toolkit и "
            "resources.limits.nvidia.com/gpu."
        )
        raise RuntimeError(message)


def _stt_model_dtype_name(device: str) -> STTModelDTypeName:
    if device.strip().lower().startswith("cuda"):
        return "float16"
    return "float32"


def _coerce_audio_bytes(raw: STTRawValue | None) -> bytes:
    if raw is None:
        raise HTTPException(status_code=422, detail="STT: поле file обязательно")
    if isinstance(raw, bytes):
        audio_bytes = raw
    elif isinstance(raw, bytearray | memoryview):
        audio_bytes = bytes(raw)
    elif isinstance(raw, list):
        byte_values: list[int] = []
        for item in raw:
            if not isinstance(item, int) or isinstance(item, bool):
                raise HTTPException(status_code=422, detail="STT: file должен быть bytes или list[int]")
            byte_values.append(item)
        try:
            audio_bytes = bytes(byte_values)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="STT: file содержит байт вне диапазона 0..255") from exc
    else:
        raise HTTPException(status_code=422, detail="STT: file должен быть bytes или list[int]")
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=422, detail="STT: поле file обязательно")
    return audio_bytes


def parse_stt_body(
    raw: STTRawBody | Request,
    *,
    default_api_model_id: str,
) -> STTTranscriptionInput:
    """Разобрать тело STT-запроса.

    Поля: ``file`` (или ``audio``) — байты аудио, ``model`` (опционально) —
    api id из ``cfg.stt_models``, ``language`` (опционально, для Whisper).
    """
    if isinstance(raw, Request):
        raise HTTPException(status_code=422, detail="STT: LitServe должен передать подготовленное тело запроса")
    audio_raw = raw.get("file")
    if audio_raw is None:
        audio_raw = raw.get("audio")
    audio_bytes = _coerce_audio_bytes(audio_raw)

    model_raw = raw.get("model")
    if model_raw is None:
        requested_model = ""
    elif isinstance(model_raw, str):
        requested_model = model_raw.strip()
    else:
        raise HTTPException(status_code=422, detail="STT: model должен быть строкой")
    if requested_model == "":
        requested_model = default_api_model_id.strip()
    if requested_model == "":
        raise HTTPException(
            status_code=422,
            detail="STT: model обязателен (либо явно в payload, либо stt_default_api_model_id в конфиге)",
        )

    language_raw = raw.get("language")
    if language_raw is None:
        language = None
    elif isinstance(language_raw, str):
        language = language_raw.strip() or None
    else:
        raise HTTPException(status_code=422, detail="STT: language должен быть строкой")
    return STTTranscriptionInput(audio_bytes=audio_bytes, model=requested_model, language=language)


def _decode_audio_to_floats(audio_bytes: bytes) -> tuple[list[float], int]:
    """Универсальный декод: пробуем soundfile (mp3/wav/ogg/flac), иначе PCM-16 16kHz.

    ``soundfile`` лежит в группе ``rag`` и является обязательной зависимостью
    provider_litserve.
    """
    try:
        buf = io.BytesIO(audio_bytes)
        data, sr = sf.read(buf, dtype="float32", always_2d=False)
        if data.ndim == 2:
            data = data.mean(axis=1)
        return [float(sample) for sample in data], int(sr)
    except (RuntimeError, ValueError):
        pass

    n_samples = len(audio_bytes) // 2
    if n_samples == 0:
        raise ValueError("STT: пустые аудио-данные")
    floats = [
        int.from_bytes(audio_bytes[offset : offset + 2], "little", signed=True) / 32768.0
        for offset in range(0, n_samples * 2, 2)
    ]
    return floats, 16000


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


class _BaseSTTAdapter(Generic[ModelT], ABC):
    backend: ClassVar[STTBackend]

    def __init__(self, cfg: ProviderLitserveInfraConfig, device: str) -> None:
        self._cfg: ProviderLitserveInfraConfig = cfg
        self._device: str = device

    @abstractmethod
    def load(self, hf_model_id: str, revision: str | None) -> ModelT:
        raise NotImplementedError

    @abstractmethod
    def transcribe(self, model_obj: ModelT, audio_bytes: bytes, language: str | None) -> str:
        raise NotImplementedError


class _GigaAMAdapter(_BaseSTTAdapter[GigaAMModel]):
    backend: ClassVar[STTBackend] = "gigaam"

    @override
    def load(self, hf_model_id: str, revision: str | None) -> GigaAMModel:
        _require_cuda_when_selected(self._device)
        logger.info("STT gigaam: загрузка hf=%s revision=%s device=%s", hf_model_id, revision, self._device)
        started = time.monotonic()
        load_model = cast(GigaAMModelLoader, AutoModel.from_pretrained)
        model = load_model(
            hf_model_id,
            revision=revision,
            trust_remote_code=True,
            token=self._cfg.hf_token,
        )
        try:
            _ = model.to(self._device)
        except Exception:  # noqa: BLE001 - GigaAM сам управляет device через .transcribe
            pass
        logger.info("STT gigaam: %s загружен за %.2fs", hf_model_id, time.monotonic() - started)
        return model

    @override
    def transcribe(self, model_obj: GigaAMModel, audio_bytes: bytes, language: str | None) -> str:
        _ = language
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


class _HuggingfaceCTCAdapter(_BaseSTTAdapter[CTCBundle]):
    backend: ClassVar[STTBackend] = "huggingface_ctc"

    @override
    def load(self, hf_model_id: str, revision: str | None) -> CTCBundle:
        _require_cuda_when_selected(self._device)
        logger.info(
            "STT huggingface_ctc: загрузка hf=%s revision=%s device=%s",
            hf_model_id, revision, self._device,
        )
        started = time.monotonic()
        load_processor = cast(CTCProcessorLoader, AutoProcessor.from_pretrained)
        load_model = cast(CTCModelLoader, AutoModelForCTC.from_pretrained)
        processor = load_processor(hf_model_id, revision=revision, token=self._cfg.hf_token)
        model = load_model(
            hf_model_id,
            revision=revision,
            token=self._cfg.hf_token,
            dtype=_stt_model_dtype_name(self._device),
        )
        _ = model.to(self._device)
        _ = model.eval()
        logger.info("STT huggingface_ctc: %s загружен за %.2fs", hf_model_id, time.monotonic() - started)
        return CTCBundle(processor=processor, model=model)

    @override
    def transcribe(self, model_obj: CTCBundle, audio_bytes: bytes, language: str | None) -> str:
        _ = language
        processor = model_obj.processor
        model = model_obj.model
        floats, sr = _decode_audio_to_floats(audio_bytes)
        inputs = processor(floats, sampling_rate=sr, return_tensors="pt", padding=True)
        input_values = inputs.input_values.to(self._device)
        attn = inputs.get("attention_mask")
        if attn is not None:
            attn = attn.to(self._device)
        with torch.no_grad():
            logits = model(input_values=input_values, attention_mask=attn).logits
        ids = logits.argmax(dim=-1)
        decoded = processor.batch_decode(ids)
        if not decoded:
            return ""
        return decoded[0].strip()


class _WhisperAdapter(_BaseSTTAdapter[WhisperASRPipeline]):
    backend: ClassVar[STTBackend] = "whisper"

    @override
    def load(self, hf_model_id: str, revision: str | None) -> WhisperASRPipeline:
        _require_cuda_when_selected(self._device)
        logger.info("STT whisper: загрузка hf=%s revision=%s device=%s", hf_model_id, revision, self._device)
        started = time.monotonic()
        load_processor = cast(WhisperProcessorLoader, AutoProcessor.from_pretrained)
        load_model = cast(WhisperModelLoader, AutoModelForSpeechSeq2Seq.from_pretrained)
        pipeline_factory = cast(ASRPipelineFactory, pipeline)
        processor = load_processor(hf_model_id, revision=revision, token=self._cfg.hf_token)
        model = load_model(
            hf_model_id,
            revision=revision,
            token=self._cfg.hf_token,
            dtype=_stt_model_dtype_name(self._device),
        )
        _ = model.to(self._device)
        pipe = pipeline_factory(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            device=self._device,
        )
        logger.info("STT whisper: %s загружен за %.2fs", hf_model_id, time.monotonic() - started)
        return pipe

    @override
    def transcribe(self, model_obj: WhisperASRPipeline, audio_bytes: bytes, language: str | None) -> str:
        floats, sr = _decode_audio_to_floats(audio_bytes)
        audio: WhisperPipelineInput = {"raw": floats, "sampling_rate": sr}
        generate_kwargs: WhisperGenerateKwargs | None = None
        if language is not None:
            generate_kwargs = {"language": language}
        result = model_obj(audio, generate_kwargs=generate_kwargs)
        return result["text"].strip()


class LocalSTTEngine:
    """Multi-backend STT-движок: загружает требуемую модель из ``cfg.stt_models``."""

    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        self._cfg: ProviderLitserveInfraConfig = cfg
        self._device: str = "cpu"
        self._gigaam_models: dict[STTModelCacheKey, GigaAMModel] = {}
        self._ctc_models: dict[STTModelCacheKey, CTCBundle] = {}
        self._whisper_pipelines: dict[STTModelCacheKey, WhisperASRPipeline] = {}

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

    def _cache_key(self, entry: ProviderLitserveSTTModelEntry) -> STTModelCacheKey:
        return entry.hf_model_id, entry.revision or ""

    def _transcribe_entry(
        self,
        entry: ProviderLitserveSTTModelEntry,
        audio_bytes: bytes,
        language: str | None,
    ) -> str:
        cache_key = self._cache_key(entry)
        if entry.backend == "gigaam":
            adapter = _GigaAMAdapter(self._cfg, self._device)
            model = self._gigaam_models.get(cache_key)
            if model is None:
                model = adapter.load(entry.hf_model_id, entry.revision)
                self._gigaam_models[cache_key] = model
            return adapter.transcribe(model, audio_bytes, language)
        if entry.backend == "huggingface_ctc":
            adapter = _HuggingfaceCTCAdapter(self._cfg, self._device)
            model = self._ctc_models.get(cache_key)
            if model is None:
                model = adapter.load(entry.hf_model_id, entry.revision)
                self._ctc_models[cache_key] = model
            return adapter.transcribe(model, audio_bytes, language)
        adapter = _WhisperAdapter(self._cfg, self._device)
        model = self._whisper_pipelines.get(cache_key)
        if model is None:
            model = adapter.load(entry.hf_model_id, entry.revision)
            self._whisper_pipelines[cache_key] = model
        return adapter.transcribe(model, audio_bytes, language)

    def transcribe_batch(self, items: list[STTTranscriptionInput]) -> list[str]:
        results: list[str] = []
        for item in items:
            audio_bytes = item.audio_bytes
            requested_model = item.model
            language = item.language
            started = time.monotonic()

            entry = self._resolve_entry(requested_model)
            text = self._transcribe_entry(entry, audio_bytes, language)
            results.append(text)
            logger.info(
                "STT транскрипция: model=%s backend=%s chars=%d duration=%.2fs",
                requested_model,
                entry.backend,
                len(text),
                time.monotonic() - started,
            )
        return results
