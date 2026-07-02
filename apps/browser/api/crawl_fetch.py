"""Stateless one-shot crawl fetch for search-worker browser fallback."""

from __future__ import annotations

import asyncio
import random
import time
import uuid

from fastapi import APIRouter, HTTPException
from playwright._impl._errors import is_target_closed_error
from playwright.async_api import Route
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from apps.browser.contracts.control_types import BrowserCapabilityError
from apps.browser.contracts.crawl_fetch_types import (
    BrowserCrawlFetchRequest,
    BrowserCrawlFetchResponse,
)
from apps.browser.dependencies import ContainerDep
from apps.browser.engine.types import (
    BrowserAcquireRequest,
    BrowserFetchRequest,
    BrowserPage,
    ContextSignature,
)
from apps.browser.interaction.human_interaction import HumanInteraction, InteractionRng
from apps.browser.interaction.interaction_profiles import get_interaction_profile
from core.logging import get_logger
from core.logging.attributes import (
    EVENT_BROWSER_CRAWL_FETCH_COMPLETED,
    EVENT_BROWSER_CRAWL_FETCH_FAILED,
    LOG_CRAWL_CANONICAL_URL,
    LOG_CRAWL_FETCH_DURATION_MS,
    LOG_EXCEPTION_MESSAGE,
    LOG_EXCEPTION_TYPE,
    LOG_HTTP_STATUS_CODE,
)

router = APIRouter(prefix="/control/crawl", tags=["browser-crawl-fetch"])
logger = get_logger(__name__)

_CRAWL_ANTI_BOT_TIER = "gray"
_crawl_fetch_inflight_semaphore: asyncio.Semaphore | None = None
_crawl_fetch_inflight_limit: int | None = None


def _crawl_fetch_semaphore(max_inflight: int) -> asyncio.Semaphore:
    global _crawl_fetch_inflight_semaphore, _crawl_fetch_inflight_limit
    if _crawl_fetch_inflight_semaphore is None or _crawl_fetch_inflight_limit != max_inflight:
        _crawl_fetch_inflight_semaphore = asyncio.Semaphore(max_inflight)
        _crawl_fetch_inflight_limit = max_inflight
    return _crawl_fetch_inflight_semaphore


async def _install_resource_block(page: BrowserPage, block_resource_types: list[str]) -> None:
    blocked = frozenset(block_resource_types)

    async def _handler(route: Route) -> None:
        if route.request.resource_type in blocked:
            await route.abort()
            return
        await route.continue_()

    _ = await page.route("**/*", _handler)


async def _post_navigate_crawl_signals(page: BrowserPage) -> None:
    profile = get_interaction_profile("fast")
    interactor = HumanInteraction()
    rnd = InteractionRng(rng=random.Random())
    await interactor.post_navigate_signals(page, profile=profile, rnd=rnd)


@router.post("/fetch", response_model=BrowserCrawlFetchResponse)
async def crawl_fetch(
    body: BrowserCrawlFetchRequest,
    container: ContainerDep,
) -> BrowserCrawlFetchResponse:
    runtime = container.browser_runtime
    settings = runtime.settings
    semaphore = _crawl_fetch_semaphore(settings.crawl_fetch_max_inflight)
    try:
        _ = await asyncio.wait_for(semaphore.acquire(), timeout=0.01)
    except TimeoutError as exc:
        raise HTTPException(
            status_code=429,
            detail="crawl fetch concurrency limit exceeded",
        ) from exc
    endpoint_key = settings.default_endpoint_key
    sig = ContextSignature(
        proxy_policy="",
        shared_storage_key=None,
        anti_bot_tier=_CRAWL_ANTI_BOT_TIER,
        stealth_init_version="v1",
        locale="ru-RU",
        timezone_id="Europe/Moscow",
        user_agent=None,
        page_mode="crawl",
        permissions_fingerprint="default",
    )

    _MAX_RETRIES = 2
    session_id: str | None = None
    started_at = time.monotonic()
    canonical_url = body.url
    try:
        for attempt in range(_MAX_RETRIES):
            started_at = time.monotonic()
            canonical_url = body.url
            if attempt > 0:
                session_id = f"crawl-fetch-{uuid.uuid4().hex}"
                run_id = f"run-{session_id}"
                task_id = f"task-{session_id}"
            else:
                session_id = f"crawl-fetch-{uuid.uuid4().hex}"
                run_id = f"run-{session_id}"
                task_id = f"task-{session_id}"
            acquire = BrowserAcquireRequest(
                run_id=run_id,
                task_id=task_id,
                session_id=session_id,
                page_mode="crawl",
                shared_storage_key=None,
                proxy_policy="",
                anti_bot_tier=_CRAWL_ANTI_BOT_TIER,
                timeout_ms=body.navigation_timeout_ms,
                endpoint_key=endpoint_key,
                session_mode="warm",
                restore_state_key=None,
                context_signature=sig,
            )
            try:
                _ = await runtime.control_adapter.start(acquire)
                async with runtime.lease_manager.session_navigate_exclusive(session_id):
                    page = await runtime.lease_manager.get_page_for_session(session_id)
                    await _install_resource_block(page, body.block_resource_types)
                    fetch_req = BrowserFetchRequest(
                        url=body.url,
                        wait_policy=body.wait_policy,
                        screenshot=False,
                        snapshot=False,
                        capture_pdf=False,
                        navigation_timeout_ms=body.navigation_timeout_ms,
                    )
                    try:
                        fetched = await runtime.control_adapter.navigate(page, fetch_req)
                    except BrowserCapabilityError as exc:
                        raise HTTPException(status_code=501, detail=exc.to_dict()) from exc
                    except PlaywrightTimeoutError as exc:
                        raise HTTPException(
                            status_code=504,
                            detail=f"browser navigation timeout for {body.url}",
                        ) from exc
                    await _post_navigate_crawl_signals(page)
                    html = await page.content()
                if not html.strip():
                    raise HTTPException(status_code=502, detail="browser fetch returned empty html")
                duration_ms = int((time.monotonic() - started_at) * 1000)
                logger.info(
                    EVENT_BROWSER_CRAWL_FETCH_COMPLETED,
                    **{
                        LOG_CRAWL_CANONICAL_URL: fetched.final_url[:256],
                        LOG_CRAWL_FETCH_DURATION_MS: duration_ms,
                        LOG_HTTP_STATUS_CODE: fetched.status_code,
                    },
                )
                return BrowserCrawlFetchResponse(
                    final_url=fetched.final_url,
                    status_code=fetched.status_code,
                    html=html,
                    anti_bot_signals=fetched.anti_bot_signals,
                )
            except Exception as exc:
                if attempt == 0 and is_target_closed_error(exc):
                    duration_ms = int((time.monotonic() - started_at) * 1000)
                    logger.warning(
                        EVENT_BROWSER_CRAWL_FETCH_FAILED,
                        **{
                            LOG_CRAWL_CANONICAL_URL: canonical_url[:256],
                            LOG_CRAWL_FETCH_DURATION_MS: duration_ms,
                            LOG_EXCEPTION_TYPE: type(exc).__name__,
                            LOG_EXCEPTION_MESSAGE: f"TargetClosedError retrying, session={session_id}",
                        },
                    )
                    await runtime.lease_manager.kill_session(
                        session_id,
                        warm_idle_sec=0,
                    )
                    runtime.observe_store.forget(session_id)
                    continue
                raise
        raise RuntimeError("crawl_fetch: exhausted retries")
    except HTTPException as exc:
        duration_ms = int((time.monotonic() - started_at) * 1000)
        logger.error(
            EVENT_BROWSER_CRAWL_FETCH_FAILED,
            **{
                LOG_CRAWL_CANONICAL_URL: canonical_url[:256],
                LOG_CRAWL_FETCH_DURATION_MS: duration_ms,
                LOG_HTTP_STATUS_CODE: exc.status_code,
                LOG_EXCEPTION_TYPE: "HTTPException",
                LOG_EXCEPTION_MESSAGE: str(exc.detail),
            },
        )
        raise
    except Exception as exc:
        duration_ms = int((time.monotonic() - started_at) * 1000)
        logger.error(
            EVENT_BROWSER_CRAWL_FETCH_FAILED,
            **{
                LOG_CRAWL_CANONICAL_URL: canonical_url[:256],
                LOG_CRAWL_FETCH_DURATION_MS: duration_ms,
                LOG_EXCEPTION_TYPE: type(exc).__name__,
                LOG_EXCEPTION_MESSAGE: str(exc),
            },
        )
        raise
    finally:
        semaphore.release()
        if session_id is not None:
            await runtime.lease_manager.kill_session(
                session_id,
                warm_idle_sec=runtime.settings.warm_idle_sec,
            )
            runtime.observe_store.forget(session_id)
