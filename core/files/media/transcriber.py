"""MediaTranscriber — единая точка входа для транскрипции аудио и видео."""

import logging
from typing import Optional

from pydantic import BaseModel, Field

from core.clients.stt_client import BaseSTTClient, STTClientFactory
from core.files.media.audio_extract import extract_audio_from_video
from core.files.media.chunked_stt import transcribe_audio_with_chunking

logger = logging.getLogger(__name__)


def _detect_provider_name(client: BaseSTTClient) -> str:
    """Определяет имя провайдера по классу STT-клиента."""
    from core.clients.stt_client import CloudRuSTTClient, MockSTTClient

    if isinstance(client, CloudRuSTTClient):
        return "cloud_ru"
    if isinstance(client, MockSTTClient):
        return "mock"
    return type(client).__name__


class TranscriptionResult(BaseModel):
    """Результат транскрипции медиафайла."""

    text: str = Field(description="Распознанный текст.")
    language: Optional[str] = Field(default=None, description="Язык распознавания.")
    provider: Optional[str] = Field(default=None, description="Идентификатор STT провайдера.")


class MediaTranscriber:
    """Единый сервис транскрипции медиафайлов.

    Поддерживает:
    - аудиофайлы (mp3, wav, ogg, m4a, flac, aac, wma, webm audio-only)
    - видеофайлы (mp4, mkv, avi, mov, webm video) — извлекает аудиодорожку
    - YouTube URL — скачивает аудио через yt-dlp (см. core.files.media.youtube)
    """

    def __init__(self, *, stt_client: BaseSTTClient | None = None) -> None:
        self._stt_client = stt_client

    def _get_stt_client(self) -> BaseSTTClient:
        if self._stt_client is None:
            self._stt_client = STTClientFactory.create_client()
        return self._stt_client

    async def transcribe_audio(
        self,
        *,
        audio_bytes: bytes,
        file_name: str,
        mime_type: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Транскрибирует аудиофайл в текст (с чанкованием при необходимости).

        Args:
            audio_bytes: байты аудиофайла
            file_name: имя файла
            mime_type: MIME-тип
            language: язык (None — дефолтный из конфигурации STT)
        """
        if not audio_bytes:
            raise ValueError("audio_bytes не может быть пустым.")
        if file_name == "":
            raise ValueError("file_name не может быть пустым.")
        if mime_type == "":
            raise ValueError("mime_type не может быть пустым.")

        stt_client = self._get_stt_client()
        text = await transcribe_audio_with_chunking(
            job_id=f"media-audio-{file_name}",
            audio_bytes=audio_bytes,
            file_name=file_name,
            mime_type=mime_type,
            language=language,
            stt_client=stt_client,
        )
        provider = _detect_provider_name(stt_client)
        return TranscriptionResult(
            text=text,
            language=language,
            provider=provider,
        )

    async def transcribe_video(
        self,
        *,
        video_bytes: bytes,
        file_name: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Транскрибирует видеофайл: извлекает аудиодорожку через ffmpeg, затем STT.

        Args:
            video_bytes: байты видеофайла
            file_name: имя файла
            language: язык (None — дефолтный из конфигурации STT)
        """
        if not video_bytes:
            raise ValueError("video_bytes не может быть пустым.")
        if file_name == "":
            raise ValueError("file_name не может быть пустым.")

        audio_bytes, audio_file_name = extract_audio_from_video(
            video_bytes=video_bytes,
            base_name=file_name,
        )
        return await self.transcribe_audio(
            audio_bytes=audio_bytes,
            file_name=audio_file_name,
            mime_type="audio/mpeg",
            language=language,
        )

    async def transcribe_url(
        self,
        *,
        url: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Скачивает аудио по URL (в т.ч. YouTube) и транскрибирует.

        Args:
            url: URL видео/аудио (YouTube, прямая ссылка)
            language: язык (None — дефолтный из конфигурации STT)
        """
        if not url or url.strip() == "":
            raise ValueError("url не может быть пустым.")

        from core.files.media.youtube import download_audio_from_url

        audio_bytes, audio_file_name, mime_type = await download_audio_from_url(url=url.strip())
        return await self.transcribe_audio(
            audio_bytes=audio_bytes,
            file_name=audio_file_name,
            mime_type=mime_type,
            language=language,
        )
