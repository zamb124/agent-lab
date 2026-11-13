"""Тесты `capture_settled_value`: navigating-гонка → retry, исчерпание → PageNavigatingError."""

from __future__ import annotations

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from apps.browser.services.page_html_capture import (
    PageNavigatingError,
    capture_settled_value,
)

_NAVIGATING = (
    "Page.content: Unable to retrieve content because the page is "
    "navigating and changing the content."
)


class _FakePage:
    def __init__(self, failures: int, *, settle_failures: int = 0) -> None:
        self.failures = failures
        self.settle_failures = settle_failures
        self.load_state_waits = 0

    async def wait_for_load_state(self, _state: str, *, timeout: float) -> None:
        _ = timeout
        self.load_state_waits += 1
        if self.settle_failures > 0:
            self.settle_failures -= 1
            raise PlaywrightTimeoutError("Timeout 5000ms exceeded")

    async def content(self) -> str:
        if self.failures > 0:
            self.failures -= 1
            raise PlaywrightError(_NAVIGATING)
        return "<html/>"


@pytest.mark.asyncio
async def test_capture_retries_navigating_race() -> None:
    page = _FakePage(failures=2)
    html = await capture_settled_value(
        page,  # pyright: ignore[reportArgumentType] — фейк страницы
        capture=page.content,
        navigation_timeout_ms=1000,
    )
    assert html == "<html/>"
    assert page.load_state_waits == 3


@pytest.mark.asyncio
async def test_capture_exhaustion_raises_navigating_error() -> None:
    page = _FakePage(failures=10)
    with pytest.raises(PageNavigatingError):
        await capture_settled_value(
            page,  # pyright: ignore[reportArgumentType]
            capture=page.content,
            navigation_timeout_ms=1000,
        )
    assert page.load_state_waits == 3


@pytest.mark.asyncio
async def test_non_navigating_error_propagates() -> None:
    page = _FakePage(failures=0)

    async def _broken() -> str:
        raise PlaywrightError("Execution context was destroyed")

    with pytest.raises(PlaywrightError, match="Execution context"):
        await capture_settled_value(
            page,  # pyright: ignore[reportArgumentType]
            capture=_broken,
            navigation_timeout_ms=1000,
        )


@pytest.mark.asyncio
async def test_settle_timeout_propagates() -> None:
    page = _FakePage(failures=10, settle_failures=1)
    with pytest.raises(PlaywrightTimeoutError):
        await capture_settled_value(
            page,  # pyright: ignore[reportArgumentType]
            capture=page.content,
            navigation_timeout_ms=1000,
        )
