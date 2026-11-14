"""Юнит-тесты ``CDPConnectionPool``: реюз Browser и восстановление мёртвого driver."""

from __future__ import annotations

import pytest

from apps.browser.services import cdp_pool
from apps.browser.services.cdp_pool import CDPConnectionPool


class _FakeBrowser:
    def __init__(self) -> None:
        self._connected = True
        self.closed = False

    def is_connected(self) -> bool:
        return self._connected

    def on(self, _event: str, _cb: object) -> None:
        return None

    async def close(self) -> None:
        self._connected = False
        self.closed = True


class _FakeChromium:
    def __init__(self, pw: _FakePlaywright) -> None:
        self._pw = pw

    async def connect_over_cdp(self, _ws_url: str) -> _FakeBrowser:
        if self._pw.dead:
            raise Exception("Connection closed while reading from the driver")
        if self._pw.connect_error is not None:
            raise self._pw.connect_error
        browser = _FakeBrowser()
        self._pw.browsers.append(browser)
        return browser


class _FakePlaywright:
    """Playwright instance: ``dead`` — умерший Node driver (pipe закрыт)."""

    def __init__(self) -> None:
        self.dead = False
        self.stopped = False
        self.connect_error: Exception | None = None
        self.browsers: list[_FakeBrowser] = []
        self.chromium = _FakeChromium(self)

    async def stop(self) -> None:
        self.stopped = True


class _FakePlaywrightCtx:
    def __init__(self, pw: _FakePlaywright) -> None:
        self._pw = pw

    async def start(self) -> _FakePlaywright:
        return self._pw


def _patch_playwright(monkeypatch: pytest.MonkeyPatch, generations: list[_FakePlaywright]) -> None:
    queue = iter(generations)
    monkeypatch.setattr(cdp_pool, "async_playwright", lambda: _FakePlaywrightCtx(next(queue)))

    async def _norm(url: str) -> str:
        return url

    monkeypatch.setattr(cdp_pool, "normalize_playwright_cdp_connect_url", _norm)


async def test_acquire_restarts_dead_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    gen1, gen2 = _FakePlaywright(), _FakePlaywright()
    _patch_playwright(monkeypatch, [gen1, gen2])
    evicted: list[str] = []
    pool = CDPConnectionPool(
        on_endpoint_disconnected=lambda key: _record(evicted, key),
    )
    browser1 = await pool.acquire_browser("ep", "cdp://x")
    _ = await pool.acquire_browser("ep2", "cdp://x")

    # Драйвер умер: Browser-хэндлы отвечают disconnected, любой send по pipe падает.
    gen1.dead = True
    browser1._connected = False  # у "ep" disconnected-событие уже дошло

    browser2 = await pool.acquire_browser("ep", "cdp://x")

    assert browser2 is not browser1
    assert gen1.stopped, "старый driver должен быть остановлен best-effort"
    # "ep" вычищен как stale до рестарта; "ep2" умер вместе с драйвером в map —
    # верхний слой обязан получить уведомление и закрыть его контексты/lease.
    assert evicted == ["ep2"]
    assert pool.playwright is gen2


async def test_acquire_propagates_endpoint_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gen1 = _FakePlaywright()
    gen1.connect_error = RuntimeError("ECONNREFUSED")
    _patch_playwright(monkeypatch, [gen1])
    pool = CDPConnectionPool()

    with pytest.raises(RuntimeError, match="ECONNREFUSED"):
        await pool.acquire_browser("ep", "cdp://x")
    assert not gen1.stopped, "CDP-отказ Chromium — не повод пересоздавать driver"


async def test_stop_tolerates_dead_handles(monkeypatch: pytest.MonkeyPatch) -> None:
    gen1 = _FakePlaywright()
    _patch_playwright(monkeypatch, [gen1])
    pool = CDPConnectionPool()
    browser = await pool.acquire_browser("ep", "cdp://x")
    gen1.dead = True

    async def _raise_close() -> None:
        raise Exception("Connection closed while reading from the driver")

    browser.close = _raise_close  # type: ignore[method-assign]

    async def _raise_stop() -> None:
        raise Exception("pipe closed")

    gen1.stop = _raise_stop  # type: ignore[method-assign]
    await pool.stop()  # не должно бросать: shutdown идемпотентен


async def _record(store: list[str], key: str) -> None:
    store.append(key)
