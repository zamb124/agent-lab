"""Локаль HTML/JSON ошибок OAuth callback (cookie language + Accept-Language q=)."""

from __future__ import annotations

import pytest

from core.api.integration_oauth_error_html import resolve_oauth_integration_locale


@pytest.mark.parametrize(
    ("accept_language", "language_cookie", "expected"),
    [
        ("en-US;q=0.8, ru-RU;q=0.9", None, "ru"),
        ("ru-RU, en;q=0.8", None, "ru"),
        ("en-US", None, "en"),
        (None, "ru", "ru"),
        ("en-US,en;q=0.9", "ru", "ru"),
        ("ru-RU", "en", "en"),
        ("", None, "ru"),
        ("fr-CH, de;q=0.9", None, "ru"),
    ],
)
def test_resolve_oauth_integration_locale(
    accept_language: str | None,
    language_cookie: str | None,
    expected: str,
) -> None:
    loc = resolve_oauth_integration_locale(
        accept_language,
        language_cookie=language_cookie,
    )
    assert loc == expected
