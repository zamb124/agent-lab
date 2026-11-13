"""Захват значения со страницы после стабилизации навигации.

SPA продолжает клиентские переходы после ``goto``: ``page.content()`` и
``page.evaluate`` падают «page is navigating and changing the content».
Захват выполняется после ``wait_for_load_state("load")`` с ограниченным
числом повторов; постоянная навигация — ``PageNavigatingError`` (исход
нестабильного целевого сайта, а не дефект платформы).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from playwright.async_api import Error as PlaywrightError

from apps.browser.models.types import BrowserPage

_CaptureReturn = TypeVar("_CaptureReturn")

# Playwright не типизирует эту гонку — единственный сигнал в тексте ошибки.
_NAVIGATING_MARKER = "navigating and changing the content"
_CAPTURE_ATTEMPTS = 3


class PageNavigatingError(RuntimeError):
    """Страница не прекратила навигацию за отведённые попытки захвата."""


async def capture_settled_value(
    page: BrowserPage,
    *,
    capture: Callable[[], Awaitable[_CaptureReturn]],
    navigation_timeout_ms: int,
) -> _CaptureReturn:
    """Дождаться load-state и выполнить ``capture``; navigating-гонка → retry.

    Ожидание load-state каждой попытки ограничено ``navigation_timeout_ms``;
    таймаут пробрасывается как ``PlaywrightTimeoutError``.
    """
    last_error: PlaywrightError | None = None
    for _ in range(_CAPTURE_ATTEMPTS):
        try:
            await page.wait_for_load_state("load", timeout=navigation_timeout_ms)
            return await capture()
        except PlaywrightError as exc:
            if _NAVIGATING_MARKER not in str(exc):
                raise
            last_error = exc
    raise PageNavigatingError(str(last_error))
