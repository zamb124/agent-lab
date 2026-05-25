"""STT-клиенты для всех провайдеров платформы.

Все клиенты реализуют batch-контракт `BaseSTTClient.transcribe_audio(...)`.
Stream-обёртки для real-time распознавания (накопление PCM в буфере с
flush по VAD) живут в `apps/voice/providers/stt/*` и используют эти
batch-клиенты под капотом.

Создание клиентов:

* для voice/flows/eval/sync/CRM batch — **только** через
  `core.clients.voice_resolver.get_stt_client(*, company_id, override)`.
  Прямой импорт классов из этого модуля в `apps/**` и в `core/**` вне
  `core/clients/**` запрещён CI (`scripts/check_voice_resolver_usage.py`).
"""

import json
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, cast, override

import httpx
from pydantic import BaseModel, Field

from core.files.models import AudioTranscriptionStatus
from core.http import get_httpx_client
from core.logging import get_logger
from core.types import (
    JsonArray,
    JsonObject,
    JsonValue,
    parse_json_value,
    require_json_array,
    require_json_object,
)

if TYPE_CHECKING:
    from core.config.models import (
        CloudRuSTTConfig,
        STTProvidersConfig,
    )


logger = get_logger(__name__)


def _extract_transcript_from_json_payload(payload: JsonValue) -> str | None:
    """Достаёт транскрипт из JSON-ответа STT в разных форматах."""
    if isinstance(payload, str):
        text = payload.strip()
        return text if text != "" else None
    if isinstance(payload, dict):
        payload_object: JsonObject = require_json_object(payload, "stt.payload")
        direct_keys = ("text", "transcript", "transcription")
        for key in direct_keys:
            if key in payload_object:
                found = _extract_transcript_from_json_payload(payload_object[key])
                if found is not None:
                    return found
        error_keys = ("error", "errors", "error_message", "exception")
        if any(key in payload_object for key in error_keys):
            return None
        container_keys = (
            "result",
            "data",
            "message",
            "output",
            "content",
            "segments",
            "alternatives",
            "choices",
            "chunks",
            "hypotheses",
            "items",
        )
        for key in container_keys:
            if key in payload_object:
                found = _extract_transcript_from_json_payload(payload_object[key])
                if found is not None:
                    return found
        for key, value in payload_object.items():
            if key in error_keys:
                continue
            if isinstance(value, dict) or isinstance(value, list):
                found = _extract_transcript_from_json_payload(value)
                if found is not None:
                    return found
        return None
    if isinstance(payload, list):
        payload_array: JsonArray = require_json_array(payload, "stt.payload")
        for item in payload_array:
            found = _extract_transcript_from_json_payload(item)
            if found is not None:
                return found
        return None
    return None


def _short_json(value: JsonValue, *, limit: int = 1200) -> str:
    serialized = json.dumps(value, ensure_ascii=False)
    if len(serialized) <= limit:
        return serialized
    return serialized[:limit] + "...(truncated)"


def _raise_if_cloud_ru_error_body(body_json: JsonValue) -> None:
    """Ответ Whisper/OpenAI-совместимого API в JSON может быть 2xx с `error`."""
    if not isinstance(body_json, dict):
        return
    body_object: JsonObject = require_json_object(body_json, "stt.error_body")
    err_raw = body_object.get("error")
    if err_raw is None:
        return
    if isinstance(err_raw, str):
        msg = err_raw.strip()
        if msg != "":
            raise ValueError(f"STT cloud_ru вернул ошибку API: {msg}")
        return
    if isinstance(err_raw, dict):
        err_object: JsonObject = require_json_object(err_raw, "stt.error_body.error")
        parts: list[str] = []
        message = err_object.get("message")
        if isinstance(message, str) and message.strip() != "":
            parts.append(message.strip())
        typ = err_object.get("type")
        if isinstance(typ, str) and typ.strip() != "":
            parts.append(f"type={typ.strip()}")
        code = err_object.get("code")
        if code is not None and str(code).strip() != "":
            parts.append(f"code={code}")
        if parts:
            raise ValueError("STT cloud_ru вернул ошибку API: " + "; ".join(parts))


def _looks_like_stt_error_text(text: str) -> bool:
    normalized = text.strip().lower()
    if normalized == "":
        return False
    if normalized.startswith("error opening <_io.bytesio object>"):
        return True
    if normalized.startswith("error:") or normalized.startswith("error "):
        return True
    error_markers = (
        "format not recognised",
        "invalid data found when processing input",
        "moov atom not found",
        "ffmpeg error",
    )
    for marker in error_markers:
        if marker in normalized:
            return True
    return False


class BaseSTTClient(ABC):
    """Базовый интерфейс STT клиента."""

    @abstractmethod
    async def transcribe_audio(
        self,
        *,
        audio_bytes: bytes,
        file_name: str,
        content_type: str,
        language: str | None = None,
    ) -> "STTTranscriptionResult":
        """
        Возвращает нормализованный результат транскрипции аудио.

        ``content_type`` — платформенный MIME-тип файла (``audio/wav``,
        ``audio/mpeg``, ...). Маппится в `multipart/form-data` параметр
        ``Content-Type`` (бывший ``mime_type``) только на границе с
        внешним STT-провайдером.
        """


class STTTranscriptionResult(BaseModel):
    """Единый нормализованный DTO результата STT."""

    provider: str = Field(description="Идентификатор STT провайдера.")
    status: AudioTranscriptionStatus = Field(
        description="Статус обработки транскрипции."
    )
    text: str = Field(description="Распознанный текст.")
    error: str | None = Field(
        default=None,
        description="Ошибка обработки транскрипции.",
    )
    language: str | None = Field(
        default=None,
        description="Язык, использованный для распознавания.",
    )


class CloudRuSTTClient(BaseSTTClient):
    """STT клиент cloud.ru foundation-models."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        response_format: str,
        temperature: float,
        default_language: str,
        timeout: float,
    ) -> None:
        if api_key == "":
            raise ValueError("STT cloud_ru api_key не может быть пустым.")
        if base_url == "":
            raise ValueError("STT cloud_ru base_url не может быть пустым.")
        if model == "":
            raise ValueError("STT cloud_ru model не может быть пустым.")
        if response_format == "":
            raise ValueError("STT cloud_ru response_format не может быть пустым.")
        if default_language == "":
            raise ValueError("STT cloud_ru language не может быть пустым.")
        if timeout <= 0:
            raise ValueError("STT cloud_ru timeout должен быть больше 0.")

        self._api_key: str = api_key
        self._base_url: str = base_url
        self._model: str = model
        self._response_format: str = response_format
        self._temperature: float = temperature
        self._default_language: str = default_language
        self._timeout: float = timeout

    @override
    async def transcribe_audio(
        self,
        *,
        audio_bytes: bytes,
        file_name: str,
        content_type: str,
        language: str | None = None,
    ) -> STTTranscriptionResult:
        if not audio_bytes:
            raise ValueError("audio_bytes не может быть пустым.")
        if file_name == "":
            raise ValueError("file_name не может быть пустым.")
        if content_type == "":
            raise ValueError("content_type не может быть пустым.")

        selected_language = language or self._default_language
        if selected_language == "":
            raise ValueError("language не может быть пустым.")

        payload = {
            "model": self._model,
            "response_format": self._response_format,
            "temperature": str(self._temperature),
            "language": selected_language,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        # `multipart/form-data`-граница: внешний STT API ждёт MIME-тип файла.
        files = {"file": (file_name, audio_bytes, content_type)}

        async with get_httpx_client(timeout=self._timeout) as client:
            response: httpx.Response = await client.post(
                self._base_url,
                headers=headers,
                data=payload,
                files=files,
            )
        _ = response.raise_for_status()

        content_type = cast(str, response.headers.get("content-type", ""))
        body_text = response.text.strip()
        if "application/json" in content_type:
            body_json = parse_json_value(response.content, "stt.cloud_ru.response")
            _raise_if_cloud_ru_error_body(body_json)
            transcript = _extract_transcript_from_json_payload(body_json)
            if transcript is None:
                message = (
                    "STT cloud_ru вернул пустую транскрипцию. "
                    + f"content_type={content_type}; payload={_short_json(body_json)}"
                )
                raise ValueError(
                    message
                )
            return STTTranscriptionResult(
                provider="cloud_ru",
                status=AudioTranscriptionStatus.DONE,
                text=transcript,
                language=selected_language,
            )

        if body_text.startswith("{") and body_text.endswith("}"):
            body_json = parse_json_value(body_text, "stt.cloud_ru.response")
            _raise_if_cloud_ru_error_body(body_json)
            transcript = _extract_transcript_from_json_payload(body_json)
            if transcript is None:
                message = (
                    "STT cloud_ru вернул пустую транскрипцию (json-string body). "
                    + f"payload={_short_json(body_json)}"
                )
                raise ValueError(
                    message
                )
            return STTTranscriptionResult(
                provider="cloud_ru",
                status=AudioTranscriptionStatus.DONE,
                text=transcript,
                language=selected_language,
            )

        if body_text.startswith("[") and body_text.endswith("]"):
            body_json = parse_json_value(body_text, "stt.cloud_ru.response")
            transcript = _extract_transcript_from_json_payload(body_json)
            if transcript is None:
                message = (
                    "STT cloud_ru вернул пустую транскрипцию (json-array body). "
                    + f"payload={_short_json(body_json)}"
                )
                raise ValueError(
                    message
                )
            return STTTranscriptionResult(
                provider="cloud_ru",
                status=AudioTranscriptionStatus.DONE,
                text=transcript,
                language=selected_language,
            )

        if body_text == "":
            raise ValueError("STT cloud_ru вернул пустой ответ.")
        if _looks_like_stt_error_text(body_text):
            message = (
                "STT cloud_ru вернул текст ошибки вместо транскрипции: "
                + f"{body_text[:300]}"
            )
            raise ValueError(
                message
            )
        return STTTranscriptionResult(
            provider="cloud_ru",
            status=AudioTranscriptionStatus.DONE,
            text=body_text,
            language=selected_language,
        )


class MockSTTClient(BaseSTTClient):
    """STT клиент для тестового окружения."""

    def __init__(self, *, transcript_text: str) -> None:
        if transcript_text == "":
            raise ValueError("STT mock transcript_text не может быть пустым.")
        self._transcript_text: str = transcript_text

    @override
    async def transcribe_audio(
        self,
        *,
        audio_bytes: bytes,
        file_name: str,
        content_type: str,
        language: str | None = None,
    ) -> STTTranscriptionResult:
        if not audio_bytes:
            raise ValueError("audio_bytes не может быть пустым.")
        if file_name == "":
            raise ValueError("file_name не может быть пустым.")
        if content_type == "":
            raise ValueError("content_type не может быть пустым.")
        return STTTranscriptionResult(
            provider="mock",
            status=AudioTranscriptionStatus.DONE,
            text=self._transcript_text,
            language=language,
        )


class LitserveSTTClient(BaseSTTClient):
    """STT клиент `provider-litserve` (OpenAI-совместимый /v1/audio/transcriptions)."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        default_language: str,
        timeout: float,
    ) -> None:
        if base_url == "":
            raise ValueError("STT litserve base_url не может быть пустым.")
        if model == "":
            raise ValueError("STT litserve model не может быть пустым.")
        if default_language == "":
            raise ValueError("STT litserve language не может быть пустым.")
        if timeout <= 0:
            raise ValueError("STT litserve timeout должен быть больше 0.")

        self._base_url: str = base_url.rstrip("/")
        self._model: str = model
        self._default_language: str = default_language
        self._timeout: float = timeout

    @override
    async def transcribe_audio(
        self,
        *,
        audio_bytes: bytes,
        file_name: str,
        content_type: str,
        language: str | None = None,
    ) -> STTTranscriptionResult:
        """Отправить аудио в provider-litserve `/v1/audio/transcriptions`.

        Тело — **JSON**: ``{"model": ..., "language": ..., "file": [int,...]}``.
        Это совпадает с контрактом ``STTLitAPI.decode_request`` /
        ``parse_stt_body`` (`apps/provider_litserve/stt/engines.py`):
        litserve декодирует JSON в dict, ``parse_stt_body`` берёт байты из
        ``raw["file"] or raw["audio"]`` и поддерживает list[int] →
        ``bytes(...)``. Multipart не используется — litserve не парсит
        multipart автоматически. ``file_name``/``content_type`` сохраняются
        в логах для совместимости с другими клиентами.
        """
        if not audio_bytes:
            raise ValueError("audio_bytes не может быть пустым.")
        if file_name == "":
            raise ValueError("file_name не может быть пустым.")
        if content_type == "":
            raise ValueError("content_type не может быть пустым.")

        selected_language = language or self._default_language
        if selected_language == "":
            raise ValueError("language не может быть пустым.")

        url = f"{self._base_url}/v1/audio/transcriptions"
        payload = {
            "model": self._model,
            "language": selected_language,
            "file": list(audio_bytes),
        }

        async with get_httpx_client(timeout=self._timeout) as client:
            response = await client.post(url, json=payload)
        _ = response.raise_for_status()

        body_json = parse_json_value(response.content, "stt.litserve.response")
        if isinstance(body_json, dict):
            body_object = require_json_object(body_json, "stt.litserve.response")
            _raise_if_cloud_ru_error_body(body_object)
            raw_text = body_object.get("text")
            if raw_text == "":
                return STTTranscriptionResult(
                    provider="litserve",
                    status=AudioTranscriptionStatus.DONE,
                    text="",
                    language=selected_language,
                )

        transcript = _extract_transcript_from_json_payload(body_json)
        if transcript is None:
            message = (
                "STT litserve вернул пустую транскрипцию. "
                + f"payload={_short_json(body_json)}"
            )
            raise ValueError(
                message
            )
        return STTTranscriptionResult(
            provider="litserve",
            status=AudioTranscriptionStatus.DONE,
            text=transcript,
            language=selected_language,
        )


class YandexSTTClient(BaseSTTClient):
    """Yandex SpeechKit STT клиент (REST). Stub: не реализован.

    Полная реализация добавится отдельной фазой при наличии ключей
    Yandex Cloud. Сейчас фабрика возвращает этот клиент при выборе
    провайдера `yandex`, но любой вызов `transcribe_audio` упадёт.
    """

    def __init__(self, *, api_key: str | None, folder_id: str | None) -> None:
        self._api_key: str | None = api_key
        self._folder_id: str | None = folder_id

    @override
    async def transcribe_audio(
        self,
        *,
        audio_bytes: bytes,
        file_name: str,
        content_type: str,
        language: str | None = None,
    ) -> STTTranscriptionResult:
        message = (
            "STT yandex: HTTP-клиент Yandex SpeechKit ещё не реализован "
            + "(нужны ключи `voice.stt.yandex.api_key` и `folder_id`). "
            + "Используйте provider=`litserve` или `cloud_ru`."
        )
        raise NotImplementedError(
            message
        )


class SberSTTClient(BaseSTTClient):
    """Sber SmartSpeech STT клиент (REST). Stub: не реализован."""

    def __init__(
        self, *, client_id: str | None, client_secret: str | None, scope: str
    ) -> None:
        self._client_id: str | None = client_id
        self._client_secret: str | None = client_secret
        self._scope: str = scope

    @override
    async def transcribe_audio(
        self,
        *,
        audio_bytes: bytes,
        file_name: str,
        content_type: str,
        language: str | None = None,
    ) -> STTTranscriptionResult:
        message = (
            "STT sber: HTTP-клиент Sber SmartSpeech ещё не реализован "
            + "(нужны ключи `voice.stt.sber.client_id` и `client_secret`). "
            + "Используйте provider=`litserve` или `cloud_ru`."
        )
        raise NotImplementedError(
            message
        )


class STTClientFactory:
    """Фабрика STT клиентов для `voice_resolver`.

    `create_for_voice(...)` принимает уже резолвнутые параметры из
    tier-резолва (`SpeechOverride` → `company_voice_providers` →
    `settings.voice.stt`).
    """

    @staticmethod
    def create_for_voice(
        *,
        cfg: "STTProvidersConfig",
        provider_name: str,
        model: str | None,
        default_language: str | None,
        timeout_s: float | None,
        secrets: dict[str, str] | None = None,
    ) -> BaseSTTClient:
        """Создать клиент по уже резолвнутым параметрам.

        `provider_name` / `model` / `default_language` / `timeout_s` —
        результат tier-резолва из `voice_resolver`. Метод не делает
        собственных fallback'ов — пустые обязательные поля → `raise`.

        ``secrets`` — merge из `company_voice_providers.secrets`
        для выбранного провайдера (строковые ключи из allowlist API).
        """
        if provider_name == "":
            raise ValueError("STT provider не задан после tier-резолва.")
        language = default_language or cfg.default_language
        if language == "":
            raise ValueError("STT default_language пуст.")

        sec = secrets or {}

        if provider_name == "litserve":
            backend = cfg.litserve
            if not backend.enabled:
                raise ValueError(
                    "STT провайдер `litserve` выключен в `voice.stt.litserve.enabled`."
                )
            chosen_model = model or cfg.default_model
            if not chosen_model:
                message = (
                    "STT litserve: model не задан ни в override, ни в "
                    + "`voice.stt.default_model`."
                )
                raise ValueError(
                    message
                )
            return LitserveSTTClient(
                base_url=backend.base_url,
                model=chosen_model,
                default_language=language,
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
            resolved_model = model if model is not None and model != "" else merged.model
            merged = merged.model_copy(update={"model": resolved_model})
            return STTClientFactory._build_cloud_ru(merged)
        if provider_name == "yandex":
            backend = cfg.yandex
            patch_ya: dict[str, str | None] = {}
            for key in ("api_key", "folder_id"):
                if key in sec:
                    patch_ya[key] = sec[key]
            bk = backend.model_copy(update=patch_ya) if patch_ya else backend
            return YandexSTTClient(
                api_key=bk.api_key, folder_id=bk.folder_id
            )
        if provider_name == "sber":
            backend = cfg.sber
            patch_sb: dict[str, str | None] = {}
            for key in ("client_id", "client_secret", "scope"):
                if key in sec:
                    patch_sb[key] = sec[key]
            bk = backend.model_copy(update=patch_sb) if patch_sb else backend
            return SberSTTClient(
                client_id=bk.client_id,
                client_secret=bk.client_secret,
                scope=bk.scope,
            )
        if provider_name == "mock":
            return MockSTTClient(transcript_text=cfg.mock_transcript_text)

        raise ValueError(f"Неизвестный STT провайдер: {provider_name!r}")

    @staticmethod
    def _build_cloud_ru(config: "CloudRuSTTConfig") -> "CloudRuSTTClient":
        if not config.enabled:
            raise ValueError("STT провайдер cloud_ru выключен в конфигурации.")
        if not config.api_key:
            raise ValueError("STT cloud_ru api_key не настроен.")
        return CloudRuSTTClient(
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            response_format=config.response_format,
            temperature=config.temperature,
            default_language=config.language,
            timeout=config.timeout,
        )
