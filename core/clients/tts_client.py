"""TTS-клиенты для всех провайдеров платформы.

Все клиенты реализуют batch-контракт `BaseTTSClient.synthesize(...)`.
Stream-обёртки для real-time синтеза (чанки по предложениям через
LookAheadBuffer) живут в `apps/voice/providers/tts/*` и используют эти
batch-клиенты под капотом.

Создание клиентов:

* для voice/flows/eval — **только** через
  `core.clients.voice_resolver.get_tts_client(*, company_id, override)`.
  Прямой импорт классов из этого модуля в `apps/**` запрещён CI
  (`scripts/check_voice_resolver_usage.py`).

``PronunciationAwareTTSClient`` — декоратор поверх ``BaseTTSClient``,
применяющий ``TtsTextPipeline`` перед делегированием провайдеру. Собирается
в ``voice_resolver.get_tts_client`` — это единственное место применения
``TtsTextPipeline`` в HTTP-слое.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

import httpx
from pydantic import BaseModel, Field

from core.clients.tts_pronunciation.pipeline import get_tts_text_pipeline
from core.files.media.pcm_to_wav import pcm_s16le_mono_to_wav
from core.http import get_httpx_client
from core.logging import get_logger
from core.tracing.operation_span import traced_operation
from core.utils.text_sanitize import sanitize_text_for_speech_backend

if TYPE_CHECKING:
    from core.clients.tts_pronunciation.models import CompiledPronunciation
    from core.config.models import (
        TTSProvidersConfig,
    )


logger = get_logger(__name__)


_MIME_BY_FORMAT: dict[str, str] = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "pcm": "audio/L16",
    "lpcm": "audio/L16",
}

_UPSTREAM_ERROR_BODY_MAX = 2048


def _sanitize_tts_voice_id(voice: str | None) -> str | None:
    """Идентификатор голоса не проходит через streamer; чистим здесь перед HTTP."""
    if voice is None:
        return None
    cleaned = sanitize_text_for_speech_backend(voice)
    if cleaned == "":
        raise ValueError("TTS: пустой voice после нормализации Unicode.")
    return cleaned


def _tts_upstream_error_summary(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        data = None
    if isinstance(data, dict) and "detail" in data:
        detail_obj = data["detail"]
        if isinstance(detail_obj, str):
            base = detail_obj
        else:
            base = json.dumps(detail_obj, ensure_ascii=False)
        exc_type = data.get("exception_type")
        exc_detail = data.get("exception_detail")
        if isinstance(exc_type, str) and exc_type.strip():
            if isinstance(exc_detail, str) and exc_detail.strip():
                base = f"{base} [{exc_type}: {exc_detail.strip()[:2000]}]"
            else:
                base = f"{base} [{exc_type}]"
        elif data.get("code") == "internal_error":
            base = (
                base
                + " — provider_litserve: лог `http_unhandled_exception` (тип исключения + traceback); "
                "синтез: `tts_litapi.predict_failed`. Локально: `SERVER__DEBUG=true` для текста в JSON."
            )
        return base[:_UPSTREAM_ERROR_BODY_MAX]
    raw = response.text.strip()
    if raw:
        return raw[:_UPSTREAM_ERROR_BODY_MAX]
    reason = response.reason_phrase
    if reason:
        return reason
    return "no body"


class TTSLitserveHttpError(Exception):
    """Ответ провайдера ``provider_litserve`` на ``POST /v1/audio/speech`` с ``status >= 400``."""

    def __init__(self, *, status_code: int, detail: str, url: str) -> None:
        self.status_code = status_code
        self.detail = detail
        self.url = url
        super().__init__(
            f"TTS litserve HTTP {status_code} for {url!r}: {detail}"
        )


class TTSResult(BaseModel):
    """Единый DTO результата синтеза речи."""

    provider: str = Field(description="Идентификатор TTS провайдера.")
    audio_bytes: bytes = Field(description="Сырой аудиопоток.")
    mime_type: str = Field(description="MIME-тип аудио (`audio/wav`, `audio/mpeg`, ...).")
    sample_rate: int = Field(gt=0, description="Частота дискретизации (Гц).")
    response_format: str = Field(
        description="Формат, запрошенный у провайдера (`wav`, `mp3`, ...)."
    )
    voice: str | None = Field(
        default=None, description="Имя голоса, использованного для синтеза."
    )
    model: str | None = Field(
        default=None, description="Имя модели TTS у провайдера."
    )

    def __len__(self) -> int:
        return len(self.audio_bytes)


class BaseTTSClient(ABC):
    """Базовый интерфейс TTS-клиента (batch синтез одного фрагмента)."""

    @abstractmethod
    async def synthesize(
        self,
        *,
        text: str,
        voice: str | None = None,
        response_format: str | None = None,
        sample_rate: int | None = None,
    ) -> TTSResult:
        """Синтезировать `text` и вернуть TTSResult."""


class LitserveTTSClient(BaseTTSClient):
    """Provider-litserve TTS клиент (OpenAI-совместимый /v1/audio/speech)."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        default_voice: str | None,
        default_response_format: str,
        default_sample_rate: int,
        timeout: float,
    ) -> None:
        if base_url == "":
            raise ValueError("TTS litserve base_url не может быть пустым.")
        if model == "":
            raise ValueError("TTS litserve model не может быть пустым.")
        if default_response_format == "":
            raise ValueError("TTS litserve response_format не может быть пустым.")
        if default_sample_rate <= 0:
            raise ValueError("TTS litserve sample_rate должен быть больше 0.")
        if timeout <= 0:
            raise ValueError("TTS litserve timeout должен быть больше 0.")

        self._base_url = base_url.rstrip("/")
        self._model = model
        self._default_voice = default_voice
        self._default_format = default_response_format
        self._default_sample_rate = default_sample_rate
        self._timeout = timeout

    async def synthesize(
        self,
        *,
        text: str,
        voice: str | None = None,
        response_format: str | None = None,
        sample_rate: int | None = None,
    ) -> TTSResult:
        text = sanitize_text_for_speech_backend(text)
        if text == "":
            raise ValueError("TTS litserve: пустой text.")
        chosen_voice = _sanitize_tts_voice_id(voice or self._default_voice)
        chosen_format = response_format or self._default_format
        chosen_sample_rate = sample_rate or self._default_sample_rate
        if chosen_format not in _MIME_BY_FORMAT:
            raise ValueError(
                f"TTS litserve: неизвестный response_format={chosen_format!r} "
                f"(допустимые: {sorted(_MIME_BY_FORMAT)})"
            )

        url = f"{self._base_url}/v1/audio/speech"
        payload: dict[str, object] = {
            "model": self._model,
            "input": text,
            "response_format": chosen_format,
        }
        if chosen_voice:
            payload["voice"] = chosen_voice
        if chosen_sample_rate:
            payload["sample_rate"] = chosen_sample_rate

        async with get_httpx_client(timeout=self._timeout) as client:
            response = await client.post(url, json=payload)
        if response.is_error:
            detail = _tts_upstream_error_summary(response)
            logger.warning(
                "litserve_tts.http_error status=%s url=%s detail=%s content_type=%s body_len=%s",
                response.status_code,
                url,
                detail,
                response.headers.get("content-type"),
                len(response.content),
            )
            raise TTSLitserveHttpError(
                status_code=response.status_code,
                detail=detail,
                url=url,
            ) from None

        return TTSResult(
            provider="litserve",
            audio_bytes=response.content,
            mime_type=_MIME_BY_FORMAT[chosen_format],
            sample_rate=chosen_sample_rate,
            response_format=chosen_format,
            voice=chosen_voice,
            model=self._model,
        )


class CloudRuTTSClient(BaseTTSClient):
    """Cloud.ru TTS клиент (OpenAI-совместимый /v1/audio/speech)."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        default_voice: str,
        default_response_format: str,
        default_sample_rate: int,
        timeout: float,
    ) -> None:
        if api_key == "":
            raise ValueError("TTS cloud_ru api_key не может быть пустым.")
        if base_url == "":
            raise ValueError("TTS cloud_ru base_url не может быть пустым.")
        if model == "":
            raise ValueError("TTS cloud_ru model не может быть пустым.")
        if default_voice == "":
            raise ValueError("TTS cloud_ru voice не может быть пустым.")
        if default_response_format == "":
            raise ValueError("TTS cloud_ru response_format не может быть пустым.")
        if default_sample_rate <= 0:
            raise ValueError("TTS cloud_ru sample_rate должен быть больше 0.")
        if timeout <= 0:
            raise ValueError("TTS cloud_ru timeout должен быть больше 0.")

        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._default_voice = default_voice
        self._default_format = default_response_format
        self._default_sample_rate = default_sample_rate
        self._timeout = timeout

    async def synthesize(
        self,
        *,
        text: str,
        voice: str | None = None,
        response_format: str | None = None,
        sample_rate: int | None = None,
    ) -> TTSResult:
        text = sanitize_text_for_speech_backend(text)
        if text == "":
            raise ValueError("TTS cloud_ru: пустой text.")
        chosen_voice = _sanitize_tts_voice_id(voice or self._default_voice)
        chosen_format = response_format or self._default_format
        chosen_sample_rate = sample_rate or self._default_sample_rate
        if chosen_format not in _MIME_BY_FORMAT:
            raise ValueError(
                f"TTS cloud_ru: неизвестный response_format={chosen_format!r}"
            )

        payload = {
            "model": self._model,
            "input": text,
            "voice": chosen_voice,
            "response_format": chosen_format,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}

        async with get_httpx_client(timeout=self._timeout) as client:
            response = await client.post(self._base_url, json=payload, headers=headers)
        response.raise_for_status()

        return TTSResult(
            provider="cloud_ru",
            audio_bytes=response.content,
            mime_type=_MIME_BY_FORMAT[chosen_format],
            sample_rate=chosen_sample_rate,
            response_format=chosen_format,
            voice=chosen_voice,
            model=self._model,
        )


class YandexTTSClient(BaseTTSClient):
    """Yandex SpeechKit TTS клиент (REST). Stub: не реализован."""

    def __init__(self, *, api_key: str | None, folder_id: str | None) -> None:
        self._api_key = api_key
        self._folder_id = folder_id

    async def synthesize(
        self,
        *,
        text: str,
        voice: str | None = None,
        response_format: str | None = None,
        sample_rate: int | None = None,
    ) -> TTSResult:
        raise NotImplementedError(
            "TTS yandex: HTTP-клиент Yandex SpeechKit ещё не реализован "
            "(нужны ключи `voice.tts.yandex.api_key` и `folder_id`). "
            "Используйте provider=`litserve` или `cloud_ru`."
        )


class SberTTSClient(BaseTTSClient):
    """Sber SmartSpeech TTS клиент (REST). Stub: не реализован."""

    def __init__(
        self, *, client_id: str | None, client_secret: str | None, scope: str
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope

    async def synthesize(
        self,
        *,
        text: str,
        voice: str | None = None,
        response_format: str | None = None,
        sample_rate: int | None = None,
    ) -> TTSResult:
        raise NotImplementedError(
            "TTS sber: HTTP-клиент Sber SmartSpeech ещё не реализован "
            "(нужны ключи `voice.tts.sber.client_id` и `client_secret`). "
            "Используйте provider=`litserve` или `cloud_ru`."
        )


class MockTTSClient(BaseTTSClient):
    """TTS клиент для тестов: короткий валидный WAV (ненулевой PCM s16le mono)."""

    async def synthesize(
        self,
        *,
        text: str,
        voice: str | None = None,
        response_format: str | None = None,
        sample_rate: int | None = None,
    ) -> TTSResult:
        text = sanitize_text_for_speech_backend(text)
        if text == "":
            raise ValueError("TTS mock: пустой text.")
        chosen_format = response_format or "wav"
        chosen_sample_rate = sample_rate or 8000
        resolved_voice = _sanitize_tts_voice_id(voice)
        stub_pcm = b"\x01\x00" * max(80, chosen_sample_rate // 50)
        audio_bytes = pcm_s16le_mono_to_wav(stub_pcm, sample_rate=chosen_sample_rate)
        return TTSResult(
            provider="mock",
            audio_bytes=audio_bytes,
            mime_type=_MIME_BY_FORMAT.get(chosen_format, "audio/wav"),
            sample_rate=chosen_sample_rate,
            response_format=chosen_format,
            voice=resolved_voice,
            model="mock",
        )


class PronunciationAwareTTSClient(BaseTTSClient):
    """Декоратор-обёртка поверх ``BaseTTSClient``: применяет text-shaping pipeline.

    Создаётся в ``voice_resolver.get_tts_client`` для всех провайдеров.
    Является **единственным** местом вызова ``TtsTextPipeline.transform`` —
    CI ``scripts/check_tts_pipeline_single_apply.py`` проверяет это.

    ``provider_name`` используется для фильтрации правил по capabilities matrix
    (например stress-маркеры не применяются для ``cloud_ru``).
    """

    def __init__(
        self,
        delegate: BaseTTSClient,
        pronunciation: "CompiledPronunciation",
        *,
        provider_name: str,
        default_voice: Optional[str] = None,
        default_language: Optional[str] = None,
    ) -> None:
        self._delegate = delegate
        self._pronunciation = pronunciation
        self._provider_name = provider_name
        self._default_voice = default_voice
        self._default_language = default_language

    async def synthesize(
        self,
        *,
        text: str,
        voice: Optional[str] = None,
        response_format: Optional[str] = None,
        sample_rate: Optional[int] = None,
    ) -> TTSResult:
        pipeline = get_tts_text_pipeline()
        original_len = len(text)
        transformed = pipeline.transform(
            text,
            pronunciation=self._pronunciation,
            provider=self._provider_name,
            voice=voice or self._default_voice,
            language=self._default_language,
        )

        if transformed != text:
            async with traced_operation(
                "voice.tts.pronunciation.transform",
                operation_category="voice",
                extra_attributes={
                    "tts.provider": self._provider_name,
                    "tts.voice": voice or self._default_voice or "",
                    "tts.language": self._default_language or "",
                    "tts.pronunciation.original_len": original_len,
                    "tts.pronunciation.transformed_len": len(transformed),
                },
            ):
                pass

        return await self._delegate.synthesize(
            text=transformed,
            voice=voice,
            response_format=response_format,
            sample_rate=sample_rate,
        )


class TTSClientFactory:
    """Фабрика TTS клиентов для voice_resolver."""

    @staticmethod
    def create_for_voice(
        *,
        cfg: "TTSProvidersConfig",
        provider_name: str,
        model: str | None,
        default_voice: str | None,
        default_response_format: str | None,
        default_sample_rate: int | None,
        timeout_s: float | None,
        secrets: dict[str, str] | None = None,
    ) -> BaseTTSClient:
        """Создать клиент по уже резолвнутым параметрам.

        ``secrets`` — строковые поля из `company_voice_providers.secrets`
        для выбранного провайдера.
        """
        if provider_name == "":
            raise ValueError("TTS provider не задан после tier-резолва.")

        sec = secrets or {}

        if provider_name == "litserve":
            backend = cfg.litserve
            if not backend.enabled:
                raise ValueError(
                    "TTS провайдер `litserve` выключен в `voice.tts.litserve.enabled`."
                )
            chosen_model = model or cfg.default_model
            if not chosen_model:
                raise ValueError(
                    "TTS litserve: model не задан ни в override, ни в "
                    "`voice.tts.default_model`."
                )
            return LitserveTTSClient(
                base_url=backend.base_url,
                model=chosen_model,
                default_voice=default_voice or cfg.default_voice,
                default_response_format=(
                    default_response_format or cfg.default_response_format
                ),
                default_sample_rate=default_sample_rate or cfg.default_sample_rate,
                timeout=timeout_s if timeout_s is not None else backend.timeout_s,
            )
        if provider_name == "cloud_ru":
            backend = cfg.cloud_ru
            merged = backend
            if sec:
                patch_cr: dict[str, str | None] = {}
                if "api_key" in sec:
                    patch_cr["api_key"] = sec["api_key"]
                merged = merged.model_copy(update=patch_cr)
            if not merged.enabled:
                raise ValueError(
                    "TTS провайдер `cloud_ru` выключен в `voice.tts.cloud_ru.enabled`."
                )
            if not merged.api_key:
                raise ValueError("TTS cloud_ru api_key не настроен.")
            return CloudRuTTSClient(
                api_key=merged.api_key,
                base_url=merged.base_url,
                model=model or merged.model,
                default_voice=default_voice or merged.voice,
                default_response_format=(
                    default_response_format or merged.response_format
                ),
                default_sample_rate=default_sample_rate or merged.sample_rate,
                timeout=timeout_s if timeout_s is not None else merged.timeout_s,
            )
        if provider_name == "yandex":
            backend = cfg.yandex
            patch_ya: dict[str, str | None] = {}
            for key in ("api_key", "folder_id"):
                if key in sec:
                    patch_ya[key] = sec[key]
            bk = backend.model_copy(update=patch_ya) if patch_ya else backend
            return YandexTTSClient(
                api_key=bk.api_key, folder_id=bk.folder_id
            )
        if provider_name == "sber":
            backend = cfg.sber
            patch_sb: dict[str, str | None] = {}
            for key in ("client_id", "client_secret", "scope"):
                if key in sec:
                    patch_sb[key] = sec[key]
            bk = backend.model_copy(update=patch_sb) if patch_sb else backend
            return SberTTSClient(
                client_id=bk.client_id,
                client_secret=bk.client_secret,
                scope=bk.scope,
            )
        if provider_name == "mock":
            return MockTTSClient()

        raise ValueError(f"Неизвестный TTS провайдер: {provider_name!r}")


__all__ = [
    "BaseTTSClient",
    "TTSResult",
    "TTSLitserveHttpError",
    "LitserveTTSClient",
    "CloudRuTTSClient",
    "YandexTTSClient",
    "SberTTSClient",
    "MockTTSClient",
    "PronunciationAwareTTSClient",
    "TTSClientFactory",
]
