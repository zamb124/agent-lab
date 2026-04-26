"""
Интеграция с реальным CDP (Lightpanda/Chromium). Требуется BROWSER__CDP_URL.
"""

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


def _acquire_req(*, session_id: str, restore_key: str | None) -> BrowserAcquireRequest:
    sid = _sig()
    return BrowserAcquireRequest(
        run_id=f"run-{session_id}",
        task_id=f"task-{session_id}",
        session_id=session_id,
        page_mode="crawl",
        shared_storage_key=None,
        proxy_policy="",
        anti_bot_tier="white",
        timeout_ms=60_000,
        endpoint_key="default",
        session_mode="restore" if restore_key else "warm",
        restore_state_key=restore_key,
        context_signature=sid,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_acquire_fetch_release() -> None:
    url = _cdp_url()
    if not url:
        pytest.skip("BROWSER__CDP_URL не задан")
    uid = uuid.uuid4().hex
    view = BrowserRuntimeSettingsView(
        default_endpoint_key="default",
        cdp_urls_by_endpoint={"default": url},
        artifacts_dir=f"artifacts/browser_runtime_test_{uid}",
        default_page_ttl_sec=3600,
        warm_idle_sec=0,
        init_scripts_version="v1",
        control_backend="playwright",
    )
    facade = BrowserRuntimeFacade(view)
    session_id = f"sess-{uid}"
    res = await facade.interactor.acquire(_acquire_req(session_id=session_id, restore_key=None))
    try:
        fr = BrowserFetchRequest(
            url="https://example.com",
            wait_policy="domcontentloaded",
            screenshot=False,
            snapshot=False,
            capture_pdf=False,
            navigation_timeout_ms=60_000,
        )
        out = await facade.interactor.fetch(res.page, fr)
        assert out.status_code == 200
        assert "example.com" in out.final_url
    finally:
        await facade.interactor.release(res.page)
        await facade.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_control_adapter_visibility_after_fetch() -> None:
    url = _cdp_url()
    if not url:
        pytest.skip("BROWSER__CDP_URL не задан")
    uid = uuid.uuid4().hex
    view = BrowserRuntimeSettingsView(
        default_endpoint_key="default",
        cdp_urls_by_endpoint={"default": url},
        artifacts_dir=f"artifacts/browser_runtime_test_{uid}",
        default_page_ttl_sec=3600,
        warm_idle_sec=0,
        init_scripts_version="v1",
        control_backend="playwright",
    )
    facade = BrowserRuntimeFacade(view)
    session_id = f"sess-vis-{uid}"
    res = await facade.interactor.acquire(_acquire_req(session_id=session_id, restore_key=None))
    try:
        fr = BrowserFetchRequest(
            url="https://example.com",
            wait_policy="domcontentloaded",
            screenshot=False,
            snapshot=False,
            capture_pdf=False,
            navigation_timeout_ms=60_000,
        )
        await facade.interactor.fetch(res.page, fr)
        tree = await facade.control_adapter.get_visibility_tree(res.page, budget=30)
        assert tree["node_count"] <= 30
        assert tree["schema"].startswith("browser.control.visibility")
        listeners = await facade.control_adapter.get_dom_event_listeners(res.page)
        assert "supported" in listeners
        assert "items" in listeners
    finally:
        await facade.interactor.release(res.page)
        await facade.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_restore_roundtrip() -> None:
    url = _cdp_url()
    if not url:
        pytest.skip("BROWSER__CDP_URL не задан")
    uid = uuid.uuid4().hex
    view = BrowserRuntimeSettingsView(
        default_endpoint_key="default",
        cdp_urls_by_endpoint={"default": url},
        artifacts_dir=f"artifacts/browser_runtime_test_{uid}",
        default_page_ttl_sec=3600,
        warm_idle_sec=0,
        init_scripts_version="v1",
        control_backend="playwright",
    )
    facade = BrowserRuntimeFacade(view)
    session_id = f"sess-{uid}"
    res = await facade.interactor.acquire(_acquire_req(session_id=session_id, restore_key=None))
    state_key: str | None = None
    try:
        fr = BrowserFetchRequest(
            url="https://example.com",
            wait_policy="domcontentloaded",
            screenshot=False,
            snapshot=False,
            capture_pdf=False,
            navigation_timeout_ms=60_000,
        )
        await facade.interactor.fetch(res.page, fr)
        state_key = await facade.interactor.save_state(res.context, "bucket-test")
    finally:
        await facade.interactor.release(res.page)

    res2 = await facade.interactor.acquire(
        _acquire_req(session_id=f"{session_id}-b", restore_key=state_key)
    )
    try:
        fr2 = BrowserFetchRequest(
            url="https://example.com",
            wait_policy="domcontentloaded",
            screenshot=False,
            snapshot=False,
            capture_pdf=False,
            navigation_timeout_ms=60_000,
        )
        out2 = await facade.interactor.fetch(res2.page, fr2)
        assert out2.status_code == 200
    finally:
        await facade.interactor.release(res2.page)
        await facade.stop()
