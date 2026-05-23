"""Классификация входного содержимого для режима content_mode=auto."""

from __future__ import annotations

import base64
import binascii
import re

from core.files.writer.exceptions import FileWriteError
from core.files.writer.models import ContentKind

_BASE64_RE = re.compile(r"^[A-Za-z0-9+/=\s]+$")
_MD_HINT = re.compile(
    r"(?m)(^\s{0,3}(#{1,6}\s|[-*+]\s|\d+\.\s|```|>\s|\|.+\|)|!\[)"
)


def classify_content(text: str) -> ContentKind:
    """
    Определяет вид строкового контента без явного content_mode.

    При неоднозначности (похоже и на base64, и на markdown) — FileWriteError.
    """
    stripped = text.strip()
    if not stripped:
        return ContentKind.RAW

    has_md = bool(_MD_HINT.search(text))
    compact = "".join(stripped.split())
    looks_b64 = len(compact) >= 32 and _BASE64_RE.match(compact) is not None
    decoded_ok = False
    if looks_b64:
        try:
            base64.b64decode(compact, validate=True)
            decoded_ok = True
        except (ValueError, binascii.Error):
            decoded_ok = False

    if has_md and looks_b64 and decoded_ok:
        raise FileWriteError(
            "Неоднозначный контент: похож одновременно на markdown и на base64. "
            "Укажите content_mode явно: markdown, base64 или raw."
        )
    if looks_b64 and decoded_ok:
        return ContentKind.BASE64
    if has_md:
        return ContentKind.MARKDOWN
    return ContentKind.RAW


SourceContent = str | bytes


def normalize_str_content(content: SourceContent, encoding: str) -> tuple[str, bool]:
    """Возвращает (строка, was_bytes)."""
    if isinstance(content, bytes):
        return content.decode(encoding), True
    if not isinstance(content, str):
        raise TypeError(f"content must be str or bytes, got {type(content).__name__}")
    return content, False
