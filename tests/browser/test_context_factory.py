"""ContextFactory: создание и закрытие без реюза."""

from __future__ import annotations

from typing import Any

import pytest

from apps.browser.runtime.context_factory import ContextFactory
from apps.browser.runtime.types import ContextSignature


class _FailingClosePage:
    def __init__(self, ctx: "_FakeContext") -> None:
        self.context = ctx

    async def close(self) -> None:
        raise RuntimeError("close failed")


class _FakeContext:
    def __init__(self) -> None:
        self.pages: list[Any] = []

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


class _FakeBrowser:
    async def new_context(self, **kwargs: Any) -> _FakeContext:
        _ = kwargs
        return _FakeContext()


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
async def test_close_page_raises_when_page_close_fails() -> None:
    factory = ContextFactory()
    browser = _FakeBrowser()
    sig = _sig()
    with pytest.raises(RuntimeError, match="close failed"):
        ctx = await factory.new_context(browser, sig, None)
        page = await factory.new_page(ctx)
        await factory.close_page(page)
