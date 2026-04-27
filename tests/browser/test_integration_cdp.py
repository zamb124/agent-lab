"""
Интеграция с реальным CDP (Lightpanda). В тестах CDP поднимается через Docker.
"""

from __future__ import annotations

import uuid

import pytest

from apps.browser.engine.types import (
    BrowserAcquireRequest,
    BrowserFetchRequest,
    BrowserRuntimeSettingsView,
    ContextSignature,
)
from apps.browser.orchestration.runtime_facade import BrowserRuntimeFacade
from tests.browser.cdp_local import ensure_cdp_url

pytestmark = pytest.mark.timeout(60)


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
    uid = uuid.uuid4().hex
    async with ensure_cdp_url() as url:
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
        res = await facade.interactor.acquire(
            _acquire_req(session_id=session_id, restore_key=None)
        )
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
async def test_control_adapter_navigate_and_run_action_after_fetch() -> None:
    uid = uuid.uuid4().hex
    async with ensure_cdp_url() as url:
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
        res = await facade.interactor.acquire(
            _acquire_req(session_id=session_id, restore_key=None)
        )
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
            out = await facade.control_adapter.navigate(res.page, fr)
            assert out.status_code == 200
            assert "example.com" in out.final_url
            r = await facade.control_adapter.run_action(res.page, "return 1;", timeout_ms=5_000)
            assert r["ok"] is True
        finally:
            await facade.interactor.release(res.page)
            await facade.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_restore_roundtrip() -> None:
    uid = uuid.uuid4().hex
    async with ensure_cdp_url() as url:
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
        res = await facade.interactor.acquire(
            _acquire_req(session_id=session_id, restore_key=None)
        )
        state_key: str | None = None
        try:
            page0 = res.context.pages[0]
            fr = BrowserFetchRequest(
                url="https://example.com",
                wait_policy="domcontentloaded",
                screenshot=False,
                snapshot=False,
                capture_pdf=False,
                navigation_timeout_ms=60_000,
            )
            out = await facade.control_adapter.navigate(page0, fr)
            assert out.status_code == 200
            assert "example.com" in out.final_url
            state_key = await facade.interactor.save_state(res.context, "bucket-test")
        finally:
            await facade.interactor.release(res.page)

        # restore_state_key в текущей модели контекста отключён (zero-guess: без скрытого реюза storage_state).
        with pytest.raises(ValueError, match="restore_state_key не поддерживается"):
            await facade.interactor.acquire(
                _acquire_req(session_id=f"{session_id}-b", restore_key=state_key)
            )
        await facade.stop()
