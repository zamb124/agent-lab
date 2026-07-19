"""Палитра цветов mailbox → calendar ribbon (ключи совпадают с COLOR_PALETTE на фронте)."""

from __future__ import annotations

import hashlib
from typing import Final

MAIL_CALENDAR_COLOR_KEYS: Final[tuple[str, ...]] = (
    "default",
    "mint",
    "sky",
    "violet",
    "amber",
    "rose",
    "gray",
    "slate",
    "orange",
    "red",
    "blue",
    "purple",
    "teal",
    "deeporange",
)

_MAIL_CALENDAR_COLOR_SET: Final[frozenset[str]] = frozenset(MAIL_CALENDAR_COLOR_KEYS)


def is_mail_calendar_color(value: str) -> bool:
    return value in _MAIL_CALENDAR_COLOR_SET


def require_mail_calendar_color(value: str) -> str:
    if not is_mail_calendar_color(value):
        raise ValueError(f"Unknown calendar_color={value!r}")
    return value


def default_calendar_color(email_address: str) -> str:
    if not email_address.strip():
        raise ValueError("email_address is required for default_calendar_color")
    digest = hashlib.sha256(email_address.strip().lower().encode("utf-8")).digest()
    return MAIL_CALENDAR_COLOR_KEYS[digest[0] % len(MAIL_CALENDAR_COLOR_KEYS)]
