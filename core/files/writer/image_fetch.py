"""Загрузка байтов по http(s) или data: для вставки изображений из markdown."""

from __future__ import annotations

import base64
import binascii
import mimetypes
import re
from urllib.parse import unquote_to_bytes, urlparse

import httpx2

from core.files.writer.exceptions import FileWriteError

_DATA_URI_RE = re.compile(
    r"^data:(?P<mime>[\w.+/-]+)?(?P<params>(?:;[\w.-]+=[^;,]+)*)?(?P<base64>;base64)?,(?P<data>.*)$",
    re.DOTALL,
)


def _normalize_image_url(raw: str) -> str:
    u = raw.strip().strip("<>").strip()
    if not u:
        raise FileWriteError("Empty URL in markdown image markup")
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https", "data"):
        raise FileWriteError(
            f"Image URL must be http, https or data: (markdown ![]()): {u!r}"
        )
    return u


def _decode_data_uri(uri: str, *, max_bytes: int) -> tuple[bytes, str | None]:
    match = _DATA_URI_RE.match(uri)
    if match is None:
        raise FileWriteError(f"Invalid data URI for markdown image: {uri[:64]!r}")
    mime = match.group("mime")
    payload = match.group("data")
    if match.group("base64") is not None:
        try:
            data = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise FileWriteError("Invalid base64 in data URI image") from exc
    else:
        data = unquote_to_bytes(payload)
    if len(data) > max_bytes:
        raise FileWriteError(
            f"data URI image exceeds the limit of {max_bytes} bytes (got {len(data)})"
        )
    if len(data) == 0:
        raise FileWriteError("Empty data URI image")
    return data, mime if mime else None


def fetch_url_bytes(
    url: str,
    *,
    max_bytes: int,
    timeout_seconds: float,
) -> tuple[bytes, str | None]:
    """
    GET по URL или decode data:; возвращает (тело, content-type при наличии).
    """
    normalized = _normalize_image_url(url)
    if normalized.startswith("data:"):
        return _decode_data_uri(normalized, max_bytes=max_bytes)

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
