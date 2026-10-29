"""Загрузка байтов по http(s) для вставки изображений из markdown."""

from __future__ import annotations

import mimetypes
from urllib.parse import urlparse

import httpx2

from core.files.writer.exceptions import FileWriteError


def _normalize_image_url(raw: str) -> str:
    u = raw.strip().strip("<>").strip()
    if not u:
        raise FileWriteError("Empty URL in markdown image markup")
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https"):
        raise FileWriteError(
            f"Image URL must be http or https (standard markdown ![]()): {u!r}"
        )
    return u


def fetch_url_bytes(
    url: str,
    *,
    max_bytes: int,
    timeout_seconds: float,
) -> tuple[bytes, str | None]:
    """
    GET по URL; возвращает (тело ответа, content-type из заголовка при наличии).
    """
    normalized = _normalize_image_url(url)
    try:
        with httpx2.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            response: httpx2.Response = client.get(normalized)
            _ = response.raise_for_status()
    except httpx2.HTTPStatusError as exc:
        raise FileWriteError(
            f"Failed to download image {normalized!r}: HTTP {exc.response.status_code}"
        ) from exc
    except httpx2.RequestError as exc:
        raise FileWriteError(f"Network error while downloading image {normalized!r}: {exc}") from exc

    data = response.content
    if len(data) > max_bytes:
        raise FileWriteError(
            f"Image {normalized!r} exceeds the limit of {max_bytes} bytes (got {len(data)})"
        )
    if len(data) == 0:
        raise FileWriteError(f"Empty response while downloading image {normalized!r}")

    mime: str | None = None
    if "content-type" in response.headers:
        ct_header = response.headers["content-type"]
        mime = ct_header.split(";")[0].strip()
    if mime is None or mime == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(normalized)
        if guessed:
            mime = guessed
    return data, mime
