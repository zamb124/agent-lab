"""Нормализация телефонов покупателей в E.164 (RU-фокус).

Вход может быть `8 900 123-45-67`, `+7 (900) 123 45 67`, `9001234567`.
Канон — всегда E.164 (`+7...`); региональные правила — phonenumbers,
`8…` → `+7…` разрешён для 11-значных RU-номеров.
"""

from __future__ import annotations

import re

import phonenumbers
from phonenumbers import PhoneNumberFormat

_DEFAULT_REGION = "RU"
_LEAD_8_RE = re.compile(r"^8\d{10}$")


def normalize_phone_e164(value: str, *, default_region: str = _DEFAULT_REGION) -> str | None:
    """Любой разумный ввод → `+7...` или `None` при невалидном номере."""
    raw = value.strip()
    if not raw:
        return None
    digits = re.sub(r"[\s\-()]", "", raw)
    try:
        if _LEAD_8_RE.match(digits):
            parsed = phonenumbers.parse("+7" + digits[1:], default_region)
        else:
            parsed = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)


def phones_equal(a: str, b: str) -> bool:
    """Сравнение через E.164 обеих сторон."""
    na = normalize_phone_e164(a)
    nb = normalize_phone_e164(b)
    return na is not None and na == nb


def mask_phone(phone_e164: str) -> str:
    """`+79001234567` → `+7 ••• ••• 45-67` — безопасно для UI и логов."""
    digits = phone_e164.lstrip("+")
    if len(digits) < 4:
        return "+•••"
    tail = digits[-4:]
    return f"+{digits[0]} ••• ••• {tail[:2]}-{tail[2:]}"
