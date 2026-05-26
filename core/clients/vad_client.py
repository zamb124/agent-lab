"""VAD-клиенты для всех провайдеров платформы.

Все клиенты реализуют batch-контракт `BaseVADClient.detect_segments(...)`.
Stream-обёртки для real-time детекции (фрейм за фреймом) живут в
`apps/voice/providers/vad/*` и используют эти batch-клиенты под капотом
(где это применимо: для `silero_local` обёртка может работать напрямую с
моделью, не выгружая её на каждый фрейм).

Создание клиентов:

* для voice/flows/eval — **только** через
  `core.clients.voice_resolver.get_vad_client(*, company_id, override)`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from importlib import import_module
from typing import TYPE_CHECKING, Protocol, TypedDict, cast, override

from core.http import get_httpx_client
from core.logging import get_logger
from core.models.voice_models import VADSegment
from core.types import JsonObject, JsonValue, parse_json_object, require_json_array

if TYPE_CHECKING:
    from torch import Tensor

    from core.config.models import (
        LocalSileroVADBackendConfig,
        VADProvidersConfig,
    )


logger = get_logger(__name__)


class _SileroScalar(Protocol):
    def item(self) -> float: ...


class _SileroModel(Protocol):
    def reset_states(self) -> None: ...

    def __call__(self, audio: Tensor, sample_rate: int) -> _SileroScalar: ...


class _SileroSpeechTimestamp(TypedDict):
    start: int | float
    end: int | float


class _SileroSpeechTimestampFn(Protocol):
    def __call__(
        self,
        audio: Tensor,
        model: _SileroModel,
        *,
        sampling_rate: int,
        threshold: float,
    ) -> Sequence[_SileroSpeechTimestamp]: ...


class _TorchModule(Protocol):
    def Tensor(self, data: Sequence[float]) -> Tensor: ...

    def no_grad(self) -> AbstractContextManager[object]: ...


class _SileroVadModule(Protocol):
    def load_silero_vad(self) -> object: ...

    def get_speech_timestamps(
        self,
        audio: Tensor,
        model: _SileroModel,
        *,
        sampling_rate: int,
        threshold: float,
    ) -> Sequence[_SileroSpeechTimestamp]: ...


def _load_torch_module() -> _TorchModule:
    module = cast(object, import_module("torch"))
    return cast(_TorchModule, module)


def _load_silero_vad_module() -> _SileroVadModule:
    module = cast(object, import_module("silero_vad"))
    return cast(_SileroVadModule, module)


def _pcm16le_to_unit_floats(audio_bytes: bytes) -> list[float]:
    even_length = len(audio_bytes) - (len(audio_bytes) % 2)
    return [
        int.from_bytes(audio_bytes[i : i + 2], "little", signed=True) / 32768.0
        for i in range(0, even_length, 2)
    ]


def _vad_segment_from_json(value: JsonValue) -> VADSegment:
    if not isinstance(value, Mapping):
        raise ValueError("VAD litserve: элемент segments должен быть JSON-объектом.")
    start = value.get("start")
    end = value.get("end")
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int | float)
        or not isinstance(end, int | float)
    ):
        raise ValueError("VAD litserve: segment.start и segment.end должны быть числами.")
    return VADSegment(start=float(start), end=float(end))


class BaseVADClient(ABC):
    """Базовый интерфейс VAD-клиента.

    * `detect_segments(audio_bytes, sample_rate, threshold)` — batch-детекция
      сегментов речи на куске произвольной длины. Поддерживается всеми
      реализациями.
    * `supports_streaming` / `detect_speech_prob(audio_bytes, sample_rate)` —
      опциональный **streaming** контракт: вход — ровно один фиксированный
      chunk (для silero — 512 сэмплов на 16 kHz / 256 на 8 kHz), выход —
      вероятность речи в [0.0, 1.0]. Между вызовами клиент **не** сбрасывает
      внутреннее состояние модели — это требование silero-vad v5
      (см. `https://github.com/snakers4/silero-vad/wiki/FAQ`).
    """

    @abstractmethod
    async def detect_segments(
        self,
        *,
        audio_bytes: bytes,
        sample_rate: int,
        threshold: float | None = None,
    ) -> list[VADSegment]:
        """Найти сегменты речи в `audio_bytes` (PCM-16 mono LE)."""

    @property
    def supports_streaming(self) -> bool:
        """Поддерживает ли клиент per-frame стриминг через ``detect_speech_prob``."""
        return False

    async def detect_speech_prob(
        self,
        *,
        audio_bytes: bytes,
        sample_rate: int,
    ) -> float:
        _ = audio_bytes, sample_rate
        raise NotImplementedError(
            f"{type(self).__name__}: streaming detect_speech_prob не поддержан."
        )

    def reset_streaming_state(self) -> None:
        """Сбросить состояние streaming VAD, если клиент его хранит."""


class LitserveVADClient(BaseVADClient):
    """VAD клиент `provider-litserve` (POST /v1/audio/vad)."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout: float,
    ) -> None:
        if base_url == "":
            raise ValueError("VAD litserve base_url не может быть пустым.")
        if model == "":
            raise ValueError("VAD litserve model не может быть пустым.")
        if timeout <= 0:
            raise ValueError("VAD litserve timeout должен быть больше 0.")
        self._base_url: str = base_url.rstrip("/")
        self._model: str = model
        self._timeout: float = timeout

    @override
    async def detect_segments(
        self,
        *,
        audio_bytes: bytes,
        sample_rate: int,
        threshold: float | None = None,
    ) -> list[VADSegment]:
        if not audio_bytes:
            raise ValueError("VAD litserve: audio_bytes пуст.")
        if sample_rate <= 0:
            raise ValueError("VAD litserve: sample_rate должен быть > 0.")

        url = f"{self._base_url}/v1/audio/vad"
        payload: JsonObject = {
            "model": self._model,
            "audio": list(audio_bytes),
            "sample_rate": sample_rate,
        }
        if threshold is not None:
            payload["threshold"] = threshold

        async with get_httpx_client(timeout=self._timeout) as client:
            response = await client.post(url, json=payload)
        _ = response.raise_for_status()

        body = parse_json_object(response.content, "vad.response")
        segments_raw = require_json_array(body.get("segments"), "vad.response.segments")

        return [_vad_segment_from_json(segment) for segment in segments_raw]


class LocalSileroVADClient(BaseVADClient):
    """In-process VAD клиент через `silero-vad` (без HTTP).

    Используется когда провайдер-litserve недоступен (например, локальная
    разработка voice-сессии без поднятого provider-litserve). Модель
    загружается лениво при первом вызове и держится в памяти процесса.
    """

    def __init__(
        self,
        *,
        sample_rate: int,
        threshold: float,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("VAD silero_local: sample_rate должен быть > 0.")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("VAD silero_local: threshold должен быть в [0.0, 1.0].")
        self._default_sample_rate: int = sample_rate
        self._default_threshold: float = threshold
        self._model: _SileroModel | None = None
        self._get_speech_ts: _SileroSpeechTimestampFn | None = None

    def _ensure_loaded(self) -> tuple[_SileroModel, _SileroSpeechTimestampFn]:
        if self._model is None:
            silero_vad = _load_silero_vad_module()
            self._model = cast(_SileroModel, silero_vad.load_silero_vad())
            self._get_speech_ts = cast(
                _SileroSpeechTimestampFn,
                silero_vad.get_speech_timestamps,
            )
        if self._get_speech_ts is None:
            raise RuntimeError("VAD silero_local: get_speech_timestamps не инициализирован.")
        return self._model, self._get_speech_ts

    @override
    async def detect_segments(
        self,
        *,
        audio_bytes: bytes,
        sample_rate: int,
        threshold: float | None = None,
    ) -> list[VADSegment]:
        if not audio_bytes:
            raise ValueError("VAD silero_local: audio_bytes пуст.")
        if sample_rate <= 0:
            raise ValueError("VAD silero_local: sample_rate должен быть > 0.")
        chosen_threshold = threshold if threshold is not None else self._default_threshold

        model, get_speech_ts = self._ensure_loaded()
        # Сегментный API независим от streaming-state; сбрасываем только тут,
        # чтобы не «загрязнять» streaming-сессию случайными batch-вызовами.
        model.reset_states()

        n_samples = len(audio_bytes) // 2
        if n_samples == 0:
            return []
        floats = _pcm16le_to_unit_floats(audio_bytes[: n_samples * 2])

        torch = _load_torch_module()
        tensor = torch.Tensor(floats)
        timestamps = get_speech_ts(
            tensor,
            model,
            sampling_rate=sample_rate,
            threshold=chosen_threshold,
        )
        return [
            VADSegment(
                start=float(ts["start"]) / sample_rate,
                end=float(ts["end"]) / sample_rate,
            )
            for ts in timestamps
        ]

    @property
    @override
    def supports_streaming(self) -> bool:
        return True

    @override
    async def detect_speech_prob(
        self,
        *,
        audio_bytes: bytes,
        sample_rate: int,
    ) -> float:
        """Streaming API: один фиксированный chunk -> вероятность речи [0,1].

        Silero-VAD v5 принимает ровно **512 сэмплов** на 16 kHz и **256** на
        8 kHz; другие размеры модель отвергает. Состояние модели **не**
        сбрасывается между вызовами — оно несёт контекст, без которого
        короткие чанки неотличимы от шума. Перезапуск streaming-сессии
        (новый разговор) — `reset_streaming_state()`.
        """
        if sample_rate not in (8000, 16000):
            raise ValueError(
                "VAD silero_local streaming: поддерживаются только "
                + f"sample_rate ∈ {{8000, 16000}}, получено {sample_rate}."
            )
        expected_samples = 512 if sample_rate == 16000 else 256
        expected_bytes = expected_samples * 2
        if len(audio_bytes) != expected_bytes:
            raise ValueError(
                "VAD silero_local streaming: chunk должен быть ровно "
                + f"{expected_bytes} байт ({expected_samples} сэмплов "
                + f"PCM-16 mono LE), получено {len(audio_bytes)} байт."
            )

        model, _ = self._ensure_loaded()

        floats = _pcm16le_to_unit_floats(audio_bytes)

        torch = _load_torch_module()
        tensor = torch.Tensor(floats)
        with torch.no_grad():
            prob = float(model(tensor, sample_rate).item())
        return prob

    @override
    def reset_streaming_state(self) -> None:
        """Сбросить внутренний state silero-модели (новый разговор/сессия)."""
        if self._model is None:
            return
        self._model.reset_states()


class MockVADClient(BaseVADClient):
    """VAD клиент-заглушка для тестов: batch — один сегмент; streaming prob по энергии PCM."""

    @override
    async def detect_segments(
        self,
        *,
        audio_bytes: bytes,
        sample_rate: int,
        threshold: float | None = None,
    ) -> list[VADSegment]:
        if not audio_bytes:
            return []
        n_samples = len(audio_bytes) // 2
        duration_s = n_samples / sample_rate if sample_rate > 0 else 0.0
        return [VADSegment(start=0.0, end=max(duration_s, 0.01))]

    @property
    @override
    def supports_streaming(self) -> bool:
        return True

    @override
    async def detect_speech_prob(
        self,
        *,
        audio_bytes: bytes,
        sample_rate: int,
    ) -> float:
        _ = sample_rate
        if not audio_bytes or len(audio_bytes) < 2:
            return 0.0
        samples = [
            int.from_bytes(audio_bytes[i : i + 2], "little", signed=True)
            for i in range(0, len(audio_bytes) - (len(audio_bytes) % 2), 2)
        ]
        if not samples:
            return 0.0
        peak = max(abs(s) for s in samples)
        return 1.0 if peak > 0 else 0.0


class VADClientFactory:
    """Фабрика VAD клиентов для voice_resolver."""

    @staticmethod
    def create_for_voice(
        *,
        cfg: "VADProvidersConfig",
        provider_name: str,
        model: str | None,
        sample_rate: int | None,
        threshold: float | None,
        timeout_s: float | None,
        secrets: dict[str, str] | None = None,
    ) -> BaseVADClient:
        """Создать клиент по уже резолвнутым параметрам."""
        _ = secrets or {}
        if provider_name == "":
            raise ValueError("VAD provider не задан после tier-резолва.")

        if provider_name == "litserve":
            backend = cfg.litserve
            if not backend.enabled:
                raise ValueError(
                    "VAD провайдер `litserve` выключен в `voice.vad.litserve.enabled`."
                )
            chosen_model = model or cfg.default_model
            if not chosen_model:
                raise ValueError(
                    "VAD litserve: model не задан ни в override, ни в "
                    + "`voice.vad.default_model`."
                )
            return LitserveVADClient(
                base_url=backend.base_url,
                model=chosen_model,
                timeout=timeout_s if timeout_s is not None else backend.timeout_s,
            )
        if provider_name == "silero_local":
            backend_local: LocalSileroVADBackendConfig = cfg.silero_local
            if not backend_local.enabled:
                raise ValueError(
                    "VAD провайдер `silero_local` выключен в "
                    + "`voice.vad.silero_local.enabled`."
                )
            return LocalSileroVADClient(
                sample_rate=sample_rate or backend_local.sample_rate,
                threshold=threshold if threshold is not None else backend_local.threshold,
            )
        if provider_name == "mock":
            return MockVADClient()

        raise ValueError(f"Неизвестный VAD провайдер: {provider_name!r}")


__all__ = [
    "BaseVADClient",
    "VADSegment",
    "LitserveVADClient",
    "LocalSileroVADClient",
    "MockVADClient",
    "VADClientFactory",
]
