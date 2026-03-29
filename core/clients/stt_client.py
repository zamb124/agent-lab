"""
STT клиент с поддержкой провайдеров.
"""

from abc import ABC, abstractmethod
import json
import os

from pydantic import BaseModel, Field

from core.config import get_settings
from core.files.models import AudioTranscriptionStatus
from core.http import get_httpx_client


def _extract_transcript_from_json_payload(payload: object) -> str | None:
    """Достаёт транскрипт из JSON-ответа STT в разных форматах."""
    if isinstance(payload, str):
        text = payload.strip()
        return text if text != "" else None
    if isinstance(payload, dict):
        direct_keys = ("text", "transcript", "transcription")
        for key in direct_keys:
            if key in payload:
                found = _extract_transcript_from_json_payload(payload[key])
                if found is not None:
                    return found
        error_keys = ("error", "errors", "error_message", "exception")
        if any(key in payload for key in error_keys):
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
            if key in payload:
                found = _extract_transcript_from_json_payload(payload[key])
                if found is not None:
                    return found
        for key, value in payload.items():
            if key in error_keys:
                continue
            if isinstance(value, dict) or isinstance(value, list):
                found = _extract_transcript_from_json_payload(value)
                if found is not None:
                    return found
        return None
    if isinstance(payload, list):
        for item in payload:
            found = _extract_transcript_from_json_payload(item)
            if found is not None:
                return found
        return None
    return None


def _short_json(value: object, *, limit: int = 1200) -> str:
    serialized = json.dumps(value, ensure_ascii=False)
    if len(serialized) <= limit:
        return serialized
    return serialized[:limit] + "...(truncated)"


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
        mime_type: str,
        language: str | None = None,
    ) -> "STTTranscriptionResult":
        """Возвращает нормализованный результат транскрипции аудио."""


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

        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._response_format = response_format
        self._temperature = temperature
        self._default_language = default_language
        self._timeout = timeout

    async def transcribe_audio(
        self,
        *,
        audio_bytes: bytes,
        file_name: str,
        mime_type: str,
        language: str | None = None,
    ) -> STTTranscriptionResult:
        if not audio_bytes:
            raise ValueError("audio_bytes не может быть пустым.")
        if file_name == "":
            raise ValueError("file_name не может быть пустым.")
        if mime_type == "":
            raise ValueError("mime_type не может быть пустым.")

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
        files = {"file": (file_name, audio_bytes, mime_type)}

        async with get_httpx_client(timeout=self._timeout) as client:
            response = await client.post(
                self._base_url,
                headers=headers,
                data=payload,
                files=files,
            )
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        body_text = response.text.strip()
        if "application/json" in content_type:
            body_json = response.json()
            transcript = _extract_transcript_from_json_payload(body_json)
            if transcript is None:
                raise ValueError(
                    "STT cloud_ru вернул пустую транскрипцию. "
                    f"content_type={content_type}; payload={_short_json(body_json)}"
                )
            return STTTranscriptionResult(
                provider="cloud_ru",
                status=AudioTranscriptionStatus.DONE,
                text=transcript,
                language=selected_language,
            )

        if body_text.startswith("{") and body_text.endswith("}"):
            body_json = json.loads(body_text)
            transcript = _extract_transcript_from_json_payload(body_json)
            if transcript is None:
                raise ValueError(
                    "STT cloud_ru вернул пустую транскрипцию (json-string body). "
                    f"payload={_short_json(body_json)}"
                )
            return STTTranscriptionResult(
                provider="cloud_ru",
                status=AudioTranscriptionStatus.DONE,
                text=transcript,
                language=selected_language,
            )

        if body_text.startswith("[") and body_text.endswith("]"):
            body_json = json.loads(body_text)
            transcript = _extract_transcript_from_json_payload(body_json)
            if transcript is None:
                raise ValueError(
                    "STT cloud_ru вернул пустую транскрипцию (json-array body). "
                    f"payload={_short_json(body_json)}"
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
            raise ValueError(
                "STT cloud_ru вернул текст ошибки вместо транскрипции: "
                f"{body_text[:300]}"
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
        self._transcript_text = transcript_text

    async def transcribe_audio(
        self,
        *,
        audio_bytes: bytes,
        file_name: str,
        mime_type: str,
        language: str | None = None,
    ) -> STTTranscriptionResult:
        if not audio_bytes:
            raise ValueError("audio_bytes не может быть пустым.")
        if file_name == "":
            raise ValueError("file_name не может быть пустым.")
        if mime_type == "":
            raise ValueError("mime_type не может быть пустым.")
        return STTTranscriptionResult(
            provider="mock",
            status=AudioTranscriptionStatus.DONE,
            text=self._transcript_text,
            language=language,
        )


class STTClientFactory:
    """Фабрика STT клиентов по конфигу."""

    @staticmethod
    def create_client() -> BaseSTTClient:
        settings = get_settings()
        provider = settings.stt.provider

        if provider == "cloud_ru":
            config = settings.stt.cloud_ru
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
        if provider == "mock":
            transcript_text = os.getenv("STT__MOCK_TRANSCRIPT_TEXT", "Тестовая транскрипция")
            return MockSTTClient(transcript_text=transcript_text)

        raise ValueError(f"Неизвестный STT провайдер: {provider}")
