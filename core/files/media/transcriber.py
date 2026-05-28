"""MediaTranscriber — единая точка входа для транскрипции аудио и видео."""

import asyncio

from pydantic import BaseModel, Field

from core.clients.speech_override import SpeechOverride
from core.clients.stt_client import BaseSTTClient
from core.clients.voice_resolver import get_stt_client
from core.files.media.audio_extract import extract_audio_from_video
from core.files.media.chunked_stt import transcribe_audio_with_chunking
from core.files.media.youtube import download_audio_from_url
from core.logging import get_logger

logger = get_logger(__name__)


class TranscriptionResult(BaseModel):
    """Результат транскрипции медиафайла."""

    text: str = Field(description="Распознанный текст.")
    language: str | None = Field(default=None, description="Язык распознавания.")
    provider: str | None = Field(default=None, description="Идентификатор STT провайдера.")


class MediaTranscriber:
    """Единый сервис транскрипции медиафайлов.

    Поддерживает:
    - аудиофайлы (mp3, wav, ogg, m4a, flac, aac, wma, webm audio-only)
    - видеофайлы (mp4, mkv, avi, mov, webm video) — извлекает аудиодорожку
    - YouTube URL — скачивает аудио через yt-dlp (см. core.files.media.youtube)

    ``company_id`` обязателен — tier-резолв STT через ``voice_resolver``.
    """

    def __init__(
        self,
        *,
        company_id: str,
        speech_override: SpeechOverride | None = None,
        stt_client: BaseSTTClient | None = None,
    ) -> None:
        if company_id == "":
            raise ValueError("MediaTranscriber: company_id не может быть пустым.")
        self._company_id: str = company_id
        self._speech_override: SpeechOverride | None = speech_override
        self._stt_client: BaseSTTClient | None = stt_client

    async def _get_stt_client(self) -> BaseSTTClient:
        if self._stt_client is not None:
            return self._stt_client
        return await get_stt_client(
            company_id=self._company_id,
            override=self._speech_override,
        )

    async def transcribe_audio(
        self,
        *,
        audio_bytes: bytes,
        file_name: str,
        content_type: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Транскрибирует аудиофайл в текст (с чанкованием при необходимости).

        Аргументы:
            audio_bytes: байты аудиофайла
            file_name: имя файла
            content_type: платформенный MIME-тип файла (например, ``audio/wav``)
            language: язык (None — из tier-резолва / media_transcriber.default_language)
        """
        if not audio_bytes:
            raise ValueError("audio_bytes не может быть пустым.")
        if file_name == "":
            raise ValueError("file_name не может быть пустым.")
        if content_type == "":
            raise ValueError("content_type не может быть пустым.")

        stt_client = await self._get_stt_client()
        text, provider = await transcribe_audio_with_chunking(
            job_id=f"media-audio-{file_name}",
            company_id=self._company_id,
            audio_bytes=audio_bytes,
            file_name=file_name,
            content_type=content_type,
            language=language,
            speech_override=self._speech_override,
            stt_client=stt_client,
        )
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

        Аргументы:
            video_bytes: байты видеофайла
            file_name: имя файла
            language: язык (None — из tier-резолва)
        """
        if not video_bytes:
            raise ValueError("video_bytes не может быть пустым.")
        if file_name == "":
            raise ValueError("file_name не может быть пустым.")

        audio_bytes, audio_file_name = await asyncio.to_thread(
            extract_audio_from_video,
            video_bytes=video_bytes,
            base_name=file_name,
        )
        return await self.transcribe_audio(
            audio_bytes=audio_bytes,
            file_name=audio_file_name,
            content_type="audio/mpeg",
            language=language,
        )

    async def transcribe_url(
        self,
        *,
        url: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Скачивает аудио по URL (в т.ч. YouTube) и транскрибирует.

        Аргументы:
            url: URL видео/аудио (YouTube, прямая ссылка)
            language: язык (None — из tier-резолва)
        """
        if not url or url.strip() == "":
            raise ValueError("url не может быть пустым.")

        audio_bytes, audio_file_name, downloaded_content_type = await download_audio_from_url(
            url=url.strip()
        )
        return await self.transcribe_audio(
            audio_bytes=audio_bytes,
            file_name=audio_file_name,
            content_type=downloaded_content_type,
            language=language,
        )
