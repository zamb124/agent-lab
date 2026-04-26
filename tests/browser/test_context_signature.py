"""Тесты стабильности сигнатуры контекста."""

from apps.browser.runtime.types import ContextSignature


def test_context_signature_stable_hash_same_for_equal_fields() -> None:
    a = ContextSignature(
        proxy_policy="",
        shared_storage_key=None,
        anti_bot_tier="white",
        stealth_init_version="v1",
        locale="ru-RU",
        timezone_id="Europe/Moscow",
        user_agent=None,
        page_mode="crawl",
        permissions_fingerprint="default",
    )
    b = ContextSignature(
        proxy_policy="",
        shared_storage_key=None,
        anti_bot_tier="white",
        stealth_init_version="v1",
        locale="ru-RU",
        timezone_id="Europe/Moscow",
        user_agent=None,
        page_mode="crawl",
        permissions_fingerprint="default",
    )
    assert a.stable_hash() == b.stable_hash()


def test_context_signature_differs_on_emulate_locale_cdp() -> None:
    base = dict(
        shared_storage_key=None,
        anti_bot_tier="white",
        stealth_init_version="v1",
        locale="en-US",
        timezone_id="UTC",
        user_agent=None,
        page_mode="crawl",
        permissions_fingerprint="default",
    )
    a = ContextSignature(
        proxy_policy="",
        emulate_locale_timezone_via_cdp=True,
        **base,
    )
    b = ContextSignature(
        proxy_policy="",
        emulate_locale_timezone_via_cdp=False,
        **base,
    )
    assert a.stable_hash() != b.stable_hash()


def test_context_signature_differs_on_proxy() -> None:
    base = dict(
        shared_storage_key=None,
        anti_bot_tier="white",
        stealth_init_version="v1",
        locale="ru-RU",
        timezone_id="Europe/Moscow",
        user_agent=None,
        page_mode="crawl",
        permissions_fingerprint="default",
    )
    a = ContextSignature(proxy_policy="http://127.0.0.1:8888", **base)
    b = ContextSignature(proxy_policy="", **base)
    assert a.stable_hash() != b.stable_hash()
