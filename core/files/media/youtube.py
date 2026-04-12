"""Скачивание аудио с YouTube и других видеоплатформ через yt-dlp."""

import asyncio
import logging
import re
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_YOUTUBE_URL_PATTERN = re.compile(
    r"(https?://)?(www\.)?"
    r"(youtube\.com/(watch\?v=|shorts/|embed/|v/)|youtu\.be/|"
    r"music\.youtube\.com/watch\?v=)"
)


def is_youtube_url(url: str) -> bool:
    """Проверяет, является ли URL ссылкой на YouTube."""
    return bool(_YOUTUBE_URL_PATTERN.search(url))


def _download_audio_sync(url: str, output_dir: str) -> tuple[bytes, str, str]:
    """Синхронно скачивает аудио через yt-dlp в указанную директорию."""
    import yt_dlp

    output_template = str(Path(output_dir) / "%(title).100B.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "64",
            }
        ],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            raise RuntimeError(f"yt-dlp не вернул информацию о видео: {url}")
        title = info.get("title", "audio")

    mp3_files = list(Path(output_dir).glob("*.mp3"))
    if len(mp3_files) == 0:
        all_files = list(Path(output_dir).iterdir())
        if len(all_files) == 0:
            raise RuntimeError(f"yt-dlp не скачал ни одного файла: {url}")
        target = all_files[0]
    else:
        target = mp3_files[0]

    audio_bytes = target.read_bytes()
    if len(audio_bytes) == 0:
        raise ValueError(f"Скачанный аудиофайл пуст: {url}")

    safe_title = re.sub(r'[^\w\s\-.]', '_', title)[:80]
    file_name = f"{safe_title}.mp3"
    return audio_bytes, file_name, "audio/mpeg"


async def download_audio_from_url(*, url: str) -> tuple[bytes, str, str]:
    """Скачивает аудиодорожку по URL (YouTube и другие платформы, поддерживаемые yt-dlp).

    Для прямых ссылок на медиафайлы использует httpx вместо yt-dlp.

    Args:
        url: URL видео или аудио

    Returns:
        (audio_bytes, file_name, mime_type)
    """
    if url == "" or url.strip() == "":
        raise ValueError("URL не может быть пустым.")

    if not is_youtube_url(url) and not _looks_like_video_platform_url(url):
        return await _download_direct_media(url)

    with tempfile.TemporaryDirectory(prefix="media-ytdlp-") as work_dir:
        audio_bytes, file_name, mime_type = await asyncio.to_thread(
            _download_audio_sync, url, work_dir
        )
    return audio_bytes, file_name, mime_type


def _looks_like_video_platform_url(url: str) -> bool:
    """Эвристика: URL с видеоплатформы (vimeo, dailymotion, rutube и т.п.)."""
    platforms = (
        "vimeo.com",
        "dailymotion.com",
        "rutube.ru",
        "vk.com/video",
        "ok.ru/video",
        "twitch.tv",
        "tiktok.com",
    )
    lowered = url.lower()
    return any(p in lowered for p in platforms)


async def _download_direct_media(url: str) -> tuple[bytes, str, str]:
    """Скачивает медиафайл по прямой ссылке через httpx."""
    from core.http import get_httpx_client

    async with get_httpx_client(timeout=120.0) as client:
        response = await client.get(url)
    response.raise_for_status()
    data = response.content
    if len(data) == 0:
        raise ValueError(f"Скачанный файл пуст: {url}")
    content_type = response.headers.get("content-type", "application/octet-stream")
    mime = content_type.split(";")[0].strip()
    tail = url.rsplit("/", 1)[-1].split("?")[0]
    file_name = tail if tail else "media-file"
    return data, file_name, mime
