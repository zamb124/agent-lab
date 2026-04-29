"""ContextFactory: создание и закрытие без реюза."""

from __future__ import annotations

from typing import Any

import pytest

from apps.browser.engine.context_factory import ContextFactory
from apps.browser.engine.types import ContextSignature


class _FailingClosePage:
    def __init__(self, ctx: "_FakeContext") -> None:
        self.context = ctx

    async def close(self) -> None:
        raise RuntimeError("close failed")

    async def evaluate(self, script: str) -> None:
        _ = script
        return None


class _FakeContext:
    def __init__(self) -> None:
        self.pages: list[Any] = []
        self._routes: list[tuple[str, object]] = []

    async def new_page(self) -> _FailingClosePage:
        page = _FailingClosePage(self)
        self.pages.append(page)
        return page

    async def close(self) -> None:
        return None

    async def add_init_script(self, script: str) -> None:
        _ = script
        return None

    async def set_extra_http_headers(self, headers: dict[str, str]) -> None:
        _ = headers
        return None

    async def route(self, pattern: str, handler: object) -> None:
        self._routes.append((pattern, handler))
        return None


class _FakeBrowser:
    def __init__(self) -> None:
        self.contexts: list[Any] = []

    async def new_context(self, **kwargs: Any) -> _FakeContext:
        ctx = _FakeContext()
        self.contexts.append(ctx)
        return ctx


def _sig() -> ContextSignature:
    return ContextSignature(
        proxy_policy="",
        shared_storage_key=None,
        anti_bot_tier="white",
        stealth_init_version="v1",
        locale="en-US",
        timezone_id="UTC",
        user_agent=None,
        page_mode="crawl",
        permissions_fingerprint="p",
    )


@pytest.mark.asyncio
async def test_close_page_raises_when_page_close_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop_stealth(_ctx: object, _signature: ContextSignature) -> None:
        return None

    monkeypatch.setattr(
        "apps.browser.engine.context_factory.apply_stealth_to_context",
        _noop_stealth,
    )
    factory = ContextFactory()
    browser = _FakeBrowser()
    sig = _sig()
    with pytest.raises(RuntimeError, match="close failed"):
        ctx = await factory.new_context(browser, "chromium", sig, None)
        page = await factory.new_page(ctx)
        await factory.close_page(page)
