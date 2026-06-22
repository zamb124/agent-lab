"""Контракт BrowserControlAdapter: Playwright vs заглушки."""

from __future__ import annotations

import pytest

from apps.browser.adapters.stub_control_adapters import AgentBrowserAdapter, BrowserUseAdapter
from apps.browser.contracts.control_types import BrowserCapabilityError
from apps.browser.engine.types import (
    BrowserAcquireRequest,
    BrowserRuntimeSettingsView,
    ContextSignature,
)
from tests.browser._runtime import build_test_facade


def _minimal_view() -> BrowserRuntimeSettingsView:
    return BrowserRuntimeSettingsView(
        default_endpoint_key="default",
        cdp_urls_by_endpoint={"default": "http://127.0.0.1:9222"},
        default_page_ttl_sec=3600,
        warm_idle_sec=0,
        init_scripts_version="v1",
        control_backend="playwright",
        reaper_interval_sec=60,
        max_contexts=50,
        session_state_ttl_sec=3600,
    )


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


def test_playwright_adapter_features() -> None:
    facade = build_test_facade(_minimal_view())
    f = facade.control_adapter.features()
    assert f.supports_ax_tree is True
    assert f.supports_selector_map is False


@pytest.mark.asyncio
async def test_browser_use_stub_raises_capability() -> None:
    ad = BrowserUseAdapter()
    assert ad.features().supports_ax_tree is False
    req = BrowserAcquireRequest(
        run_id="r",
        task_id="t",
        session_id="s",
        page_mode="crawl",
        shared_storage_key=None,
        proxy_policy="",
        anti_bot_tier="white",
        timeout_ms=1000,
        endpoint_key="default",
        session_mode="warm",
        restore_state_key=None,
        context_signature=_sig(),
    )
    with pytest.raises(BrowserCapabilityError) as ei:
        await ad.start(req)
    assert ei.value.code == "backend_not_configured"


@pytest.mark.asyncio
async def test_agent_browser_stub_stop_is_noop() -> None:
    ad = AgentBrowserAdapter()
    await ad.stop(object())  # pyright: ignore[reportArgumentType]
