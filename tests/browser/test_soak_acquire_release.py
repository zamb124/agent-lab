"""Soak: многократный acquire/fetch/release (последовательно)."""

from __future__ import annotations

import os
import uuid

import pytest

from apps.browser.runtime.facade import BrowserRuntimeFacade
from apps.browser.runtime.types import (
    BrowserAcquireRequest,
    BrowserFetchRequest,
    BrowserRuntimeSettingsView,
    ContextSignature,
)


def _cdp_url() -> str | None:
    v = os.environ.get("BROWSER__CDP_URL", "").strip()
    if v:
        return v
    return None


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
        emulate_locale_timezone_via_cdp=False,
    )


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.asyncio
async def test_soak_100_acquire_fetch_release() -> None:
    url = _cdp_url()
    if not url:
        pytest.skip("BROWSER__CDP_URL не задан")
    uid = uuid.uuid4().hex
    view = BrowserRuntimeSettingsView(
        default_endpoint_key="default",
        cdp_urls_by_endpoint={"default": url},
        artifacts_dir=f"artifacts/browser_runtime_soak_{uid}",
        default_page_ttl_sec=3600,
        warm_idle_sec=0,
        init_scripts_version="v1",
        control_backend="playwright",
    )
    facade = BrowserRuntimeFacade(view)
    fr = BrowserFetchRequest(
        url="https://example.com",
        wait_policy="domcontentloaded",
        screenshot=False,
        snapshot=False,
        capture_pdf=False,
        navigation_timeout_ms=60_000,
    )
    try:
        for i in range(100):
            req = BrowserAcquireRequest(
                run_id=f"run-{uid}-{i}",
                task_id=f"task-{uid}-{i}",
                session_id=f"sess-{uid}-{i}",
                page_mode="crawl",
                shared_storage_key=None,
                proxy_policy="",
                anti_bot_tier="white",
                timeout_ms=60_000,
                endpoint_key="default",
                session_mode="warm",
                restore_state_key=None,
                context_signature=_sig(),
            )
            res = await facade.interactor.acquire(req)
            try:
                out = await facade.interactor.fetch(res.page, fr)
                assert out.status_code == 200
            finally:
                await facade.interactor.release(res.page)
    finally:
        await facade.stop()
