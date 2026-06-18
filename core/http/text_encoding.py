"""Декодирование HTTP response body с учётом charset из заголовков и HTML meta."""

from __future__ import annotations

import re

from charset_normalizer import from_bytes

_META_CHARSET_RE = re.compile(
    rb"""<meta[^>]+charset\s*=\s*["']?\s*([a-zA-Z0-9_-]+)""",
    re.IGNORECASE,
)
_META_HTTP_EQUIV_CHARSET_RE = re.compile(
    rb"""content\s*=\s*["'][^"']*;\s*charset\s*=\s*([a-zA-Z0-9_-]+)""",
    re.IGNORECASE,
)


def _charset_from_content_type(content_type: str) -> str | None:
    parts = content_type.split(";")
    for part in parts[1:]:
        key_value = part.strip().split("=", 1)
        if len(key_value) != 2:
            continue
        if key_value[0].strip().lower() != "charset":
            continue
        return key_value[1].strip().strip('"').strip("'")
    return None


def _charset_from_html_meta(content: bytes) -> str | None:
    head = content[:8192]
    match = _META_CHARSET_RE.search(head)
    if match is not None:
        return match.group(1).decode("ascii")
    match = _META_HTTP_EQUIV_CHARSET_RE.search(head)
    if match is not None:
        return match.group(1).decode("ascii")
    return None


def _append_charset(charsets: list[str], charset: str | None) -> None:
    if charset is None:
        return
    normalized = charset.strip()
    if not normalized:
        return
    if normalized.lower() in {existing.lower() for existing in charsets}:
        return
    charsets.append(normalized)


def decode_response_body_bytes(content: bytes, *, content_type: str) -> str:
    if not content:
        raise ValueError("empty response body")

    charsets: list[str] = []
    _append_charset(charsets, _charset_from_content_type(content_type))
    if "html" in content_type.lower():
        _append_charset(charsets, _charset_from_html_meta(content))
    _append_charset(charsets, "utf-8")

    for charset in charsets:
        try:
            return content.decode(charset)
        except (LookupError, UnicodeDecodeError):
            continue

    best = from_bytes(content).best()
    if best is None:
        raise ValueError("unable to decode response body charset")
    return str(best)
