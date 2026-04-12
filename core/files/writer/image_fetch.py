"""Загрузка байтов по http(s) для вставки изображений из markdown."""

from __future__ import annotations

import mimetypes
from typing import Optional
from urllib.parse import urlparse

import httpx

from core.files.writer.exceptions import FileWriteError


def _normalize_image_url(raw: str) -> str:
    u = raw.strip().strip("<>").strip()
    if not u:
        raise FileWriteError("Пустой URL в разметке изображения markdown")
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https"):
        raise FileWriteError(
            f"URL изображения должен быть http или https (стандартный markdown ![]()): {u!r}"
        )
    return u


def fetch_url_bytes(
    url: str,
    *,
    max_bytes: int,
    timeout_seconds: float,
) -> tuple[bytes, Optional[str]]:
    """
    GET по URL; возвращает (тело ответа, content-type из заголовка при наличии).
    """
    normalized = _normalize_image_url(url)
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            response = client.get(normalized)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise FileWriteError(
            f"Не удалось загрузить изображение {normalized!r}: HTTP {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise FileWriteError(f"Ошибка сети при загрузке изображения {normalized!r}: {exc}") from exc

    data = response.content
    if len(data) > max_bytes:
        raise FileWriteError(
            f"Изображение {normalized!r} превышает лимит {max_bytes} байт (получено {len(data)})"
        )
    if len(data) == 0:
        raise FileWriteError(f"Пустой ответ при загрузке изображения {normalized!r}")

    ct_header = response.headers.get("content-type")
    mime: Optional[str] = None
    if isinstance(ct_header, str) and ct_header.strip():
        mime = ct_header.split(";")[0].strip()
    if mime is None or mime == "application/octet-stream":
        guessed, _ = mimetypes.guess_type(normalized)
        if guessed:
            mime = guessed
    return data, mime
