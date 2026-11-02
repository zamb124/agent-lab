"""Нормализация телефона покупателя → E.164 (customers.mdc)."""

from __future__ import annotations

from core.customers.phone import mask_phone, normalize_phone_e164


def test_normalize_ru_mobile() -> None:
    assert normalize_phone_e164("+7 (999) 123-45-67") == "+79991234567"
    assert normalize_phone_e164("8 999 123 45 67") == "+79991234567"
    assert normalize_phone_e164("89991234567") == "+79991234567"
    assert normalize_phone_e164("9991234567") == "+79991234567"


def test_normalize_foreign() -> None:
    assert normalize_phone_e164("+1 202 555 0123") == "+12025550123"
    assert normalize_phone_e164("+49 30 123456") == "+4930123456"


def test_normalize_invalid() -> None:
    assert normalize_phone_e164("") is None
    assert normalize_phone_e164("123") is None
    assert normalize_phone_e164("not a phone") is None
    assert normalize_phone_e164("+7000") is None


def test_mask() -> None:
    masked = mask_phone("+79991234567")
    assert masked.endswith("45-67")
    assert "123" not in masked
