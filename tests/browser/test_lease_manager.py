"""Менеджер аренды страниц с поддельной фабрикой контекстов."""

from __future__ import annotations

from typing import Any, Optional

import pytest

import apps.browser.services.page_lease_manager as lease_module
from apps.browser.models.types import ContextSignature
from apps.browser.services.page_lease_manager import PageLeaseManager
from core.types import JsonObject


class _FakePage:
    def __init__(self, ctx: _FakeContext) -> None:
        self.context = ctx
        self._handlers: dict[str, list[Any]] = {}

    def on(self, event: str, handler: Any) -> None:
        self._handlers.setdefault(event, []).append(handler)

    def remove_listener(self, event: str, handler: Any) -> None:
        handlers = self._handlers.get(event)
        if handlers and handler in handlers:
            handlers.remove(handler)

    def fire(self, event: str, obj: Any) -> None:
        for handler in list(self._handlers.get(event, [])):
            handler(obj)


class _FakeRequest:
    def __init__(self, url: str) -> None:
        self.url = url
        self.method = "GET"
        self.failure = "net::ERR_FAILED"


class _FakeContext:
    def __init__(self) -> None:
        self.pages: list[Any] = []


class FakeContextFactory:
    def __init__(self) -> None:
        self.new_context_count = 0
        self.new_page_count = 0
        self.close_page_count = 0
        self.close_context_count = 0

    async def new_context(
        self,
        browser: Any,
        endpoint_key: str,
        signature: ContextSignature,
        storage_state: Optional[dict[str, Any]],
    ) -> Any:
        _ = browser
        _ = endpoint_key
        _ = signature
        _ = storage_state
        self.new_context_count += 1
        return _FakeContext()

    async def new_page(self, context: Any) -> Any:
        self.new_page_count += 1
        page = _FakePage(context)
        context.pages.append(page)
        return page

    async def close_page(self, page: Any) -> None:
        _ = page
        self.close_page_count += 1

    async def close_context(self, context: Any) -> None:
        _ = context
        self.close_context_count += 1


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
async def test_kill_session_closes_all_pages() -> None:
    factory = FakeContextFactory()
    lm = PageLeaseManager(factory)  # type: ignore[arg-type]
    browser = object()
    sig = _sig()
    _, p1, _ = await lm.lease_page(
        browser,
        "ep",
        sig,
        "sess-a",
        storage_state=None,
        session_mode="warm",
        page_ttl_sec=3600,
        warm_idle_sec=0,
    )
    _, p2, _ = await lm.lease_page(
        browser,
        "ep",
        sig,
        "sess-a",
        storage_state=None,
        session_mode="warm",
        page_ttl_sec=3600,
        warm_idle_sec=0,
    )
    assert factory.new_context_count == 1
    assert factory.new_page_count == 2
    await lm.kill_session("sess-a", warm_idle_sec=0)
    assert factory.close_page_count == 2
    assert factory.close_context_count == 1
    assert await lm.is_session_recently_closed("sess-a") is True
    assert await lm.is_session_recently_closed("sess-never") is False
    _ = p1
    _ = p2


@pytest.mark.asyncio
async def test_get_page_for_session_requires_single_lease() -> None:
    factory = FakeContextFactory()
    lm = PageLeaseManager(factory)  # type: ignore[arg-type]
    browser = object()
    sig = _sig()
    _, page, _ = await lm.lease_page(
        browser,
        "ep",
        sig,
        "sess-one",
        storage_state=None,
        session_mode="warm",
        page_ttl_sec=3600,
        warm_idle_sec=0,
    )
    got = await lm.get_page_for_session("sess-one")
    assert got is page


@pytest.mark.asyncio
async def test_get_page_for_session_multiple_pages_raises() -> None:
    factory = FakeContextFactory()
    lm = PageLeaseManager(factory)  # type: ignore[arg-type]
    browser = object()
    sig = _sig()
    await lm.lease_page(
        browser,
        "ep",
        sig,
        "sess-dup",
        storage_state=None,
        session_mode="warm",
        page_ttl_sec=3600,
        warm_idle_sec=0,
    )
    await lm.lease_page(
        browser,
        "ep",
        sig,
        "sess-dup",
        storage_state=None,
        session_mode="warm",
        page_ttl_sec=3600,
        warm_idle_sec=0,
    )
    with pytest.raises(RuntimeError, match="Expected one page"):
        await lm.get_page_for_session("sess-dup")


@pytest.mark.asyncio
async def test_release_unknown_page_raises() -> None:
    factory = FakeContextFactory()
    lm = PageLeaseManager(factory)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="not registered"):
        await lm.release_page(object(), warm_idle_sec=0)


@pytest.mark.asyncio
async def test_endpoint_drain_blocks_only_selected_endpoint() -> None:
    factory = FakeContextFactory()
    lm = PageLeaseManager(factory)  # type: ignore[arg-type]
    browser = object()
    sig = _sig()
    lm.set_endpoint_drain("ep-a", True)
    with pytest.raises(RuntimeError, match="endpoint=ep-a"):
        await lm.lease_page(
            browser,
            "ep-a",
            sig,
            "sess-a",
            storage_state=None,
            session_mode="warm",
            page_ttl_sec=3600,
            warm_idle_sec=0,
        )
    _, page, _ = await lm.lease_page(
        browser,
        "ep-b",
        sig,
        "sess-b",
        storage_state=None,
        session_mode="warm",
        page_ttl_sec=3600,
        warm_idle_sec=0,
    )
    assert page is not None


@pytest.mark.asyncio
async def test_page_event_budget_suppresses_flood_and_flushes() -> None:
    """Страница в цикле ошибок: первые N событий verbatim, остальное — агрегат."""
    events: list[tuple[str, JsonObject]] = []

    def logger_fn(session_id: str, event: JsonObject) -> None:
        events.append((session_id, event))

    factory = FakeContextFactory()
    lm = PageLeaseManager(factory, page_event_logger=logger_fn)  # type: ignore[arg-type]
    budget = lease_module._PAGE_EVENT_BUDGET  # pyright: ignore[reportPrivateUsage]
    _, page, _ = await lm.lease_page(
        object(),
        "ep",
        _sig(),
        "sess-ev",
        storage_state=None,
        session_mode="warm",
        page_ttl_sec=3600,
        warm_idle_sec=0,
    )
    assert isinstance(page, _FakePage)
    flood = budget + 50
    for i in range(flood):
        page.fire("requestfailed", _FakeRequest(f"https://x/r{i}"))
    verbatim = [e for _, e in events if e.get("kind") == "requestfailed"]
    assert len(verbatim) == budget
    await lm.kill_session("sess-ev", warm_idle_sec=0)
    summaries = [e for _, e in events if e.get("kind") == "events_suppressed"]
    assert len(summaries) == 1
    assert summaries[0]["suppressed_total"] == 50


@pytest.mark.asyncio
async def test_navigate_locks_pruned_for_dead_sessions() -> None:
    """Sweep вычищает _navigate_locks сессий, у которых не осталось контекста."""
    factory = FakeContextFactory()
    lm = PageLeaseManager(factory)  # type: ignore[arg-type]
    _, page, _ = await lm.lease_page(
        object(),
        "ep",
        _sig(),
        "sess-lock",
        storage_state=None,
        session_mode="warm",
        page_ttl_sec=3600,
        warm_idle_sec=0,
    )
    async with lm.session_navigate_exclusive("sess-lock"):
        pass
    await lm.release_page(page, warm_idle_sec=0)
    await lm.sweep_expired(warm_idle_sec=0)
    assert "sess-lock" not in lm._navigate_locks  # pyright: ignore[reportPrivateUsage]
