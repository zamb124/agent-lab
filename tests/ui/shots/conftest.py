"""Фикстуры маркетинговых скриншотов.

Браузерный контекст с ``device_scale_factor=2`` (PNG ~2880px по ширине),
auth-cookie владельца worker-компании и сиднутый демо-контент всех сервисов.
Кадры пишутся в ``tests/ui/shots/out/<name>.png`` — отсюда их забирает
``scripts/tools/land_optimize.py`` в ``apps/frontend/ui/assets/images/land``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import pytest
import pytest_asyncio
from playwright.async_api import Browser, BrowserContext, Page

from tests.ui.browser_auth import add_auth_token_cookie
from tests.ui.centrifugo_ws_bridge import install_centrifugo_ws_bridge
from tests.ui.e2e_worker import ui_e2e_company_id, ui_e2e_test_scope
from tests.ui.shots import seed_content

SHOTS_OUT_DIR = Path(__file__).resolve().parent / "out"

DESKTOP_VIEWPORT = {"width": 1440, "height": 900}
MOBILE_VIEWPORT = {"width": 390, "height": 844}
DEVICE_SCALE = 2

PAGE_SETTLE_MS = 1200


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.path.is_relative_to(Path(__file__).resolve().parent):
            item.add_marker(pytest.mark.shots)


async def _new_shot_context(
    browser: Browser,
    *,
    token: str | None,
    viewport: dict[str, int],
    reduced_motion: bool,
) -> BrowserContext:
    context = await browser.new_context(
        viewport=viewport,
        device_scale_factor=DEVICE_SCALE,
        locale="ru",
        reduced_motion="reduce" if reduced_motion else "no-preference",
    )
    await install_centrifugo_ws_bridge(context)
    if token is not None:
        await add_auth_token_cookie(context, token)

    async def _scope_header(route) -> None:
        headers = {**route.request.headers, "X-Test-Scope": ui_e2e_test_scope()}
        await route.continue_(headers=headers)

    await context.route("**/*", _scope_header)
    await context.add_init_script(
        """
        try {
            window.localStorage.setItem('platform:core:theme', 'dark');
            window.localStorage.setItem('platform:core:locale', 'ru');
        } catch (e) { /* storage недоступен на public-origin */ }
        """
    )
    return context


@pytest_asyncio.fixture
async def shot_desktop_page(
    _browser_session: Browser, auth_token_system: str
) -> AsyncIterator[Page]:
    context = await _new_shot_context(
        _browser_session,
        token=auth_token_system,
        viewport=DESKTOP_VIEWPORT,
        reduced_motion=True,
    )
    try:
        yield await context.new_page()
    finally:
        await context.close()


@pytest_asyncio.fixture
async def shot_mobile_page(
    _browser_session: Browser, auth_token_system: str
) -> AsyncIterator[Page]:
    context = await _new_shot_context(
        _browser_session,
        token=auth_token_system,
        viewport=MOBILE_VIEWPORT,
        reduced_motion=True,
    )
    try:
        yield await context.new_page()
    finally:
        await context.close()


@pytest_asyncio.fixture
async def shot_anonymous_page(_browser_session: Browser) -> AsyncIterator[Page]:
    """Публичная витрина/лендинг без auth-cookie."""
    context = await _new_shot_context(
        _browser_session,
        token=None,
        viewport=DESKTOP_VIEWPORT,
        reduced_motion=True,
    )
    try:
        yield await context.new_page()
    finally:
        await context.close()


@pytest_asyncio.fixture
async def shot_anonymous_mobile(_browser_session: Browser) -> AsyncIterator[Page]:
    context = await _new_shot_context(
        _browser_session,
        token=None,
        viewport=MOBILE_VIEWPORT,
        reduced_motion=True,
    )
    try:
        yield await context.new_page()
    finally:
        await context.close()


@pytest.fixture
def save_shot() -> Callable[[Page, str], Awaitable[Path]]:
    async def _save(page: Page, name: str) -> Path:
        SHOTS_OUT_DIR.mkdir(parents=True, exist_ok=True)
        path = SHOTS_OUT_DIR / f"{name}.png"
        await page.screenshot(path=str(path), full_page=False)
        return path

    return _save


async def settle_page(page: Page, ms: int = PAGE_SETTLE_MS) -> None:
    """Дать фабрикам и запросам дорендерить кадр."""
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    await page.evaluate(
        """
        () => {
            const timeout = new Promise((resolve) => setTimeout(resolve, 4000));
            const decodes = Array.from(document.images)
                .filter((img) => !img.complete)
                .slice(0, 60)
                .map((img) => img.decode().catch(() => undefined));
            return Promise.race([Promise.all(decodes), timeout]);
        }
        """
    )
    await page.wait_for_timeout(ms)


@pytest_asyncio.fixture(scope="session")
async def shots_shop_di(setup_database_before_tests):
    """Session-вариант ``shop_di``: seed ~70 фото — один lifespan на воркера."""
    from apps.shop.di import ShopDi
    from apps.shop.main import app as shop_app
    from core.di import require_di

    _ = setup_database_before_tests
    async with shop_app.router.lifespan_context(shop_app):
        yield require_di(shop_app, ShopDi)


@pytest_asyncio.fixture(scope="session")
async def marketing_seeded(
    _ui_e2e_company_resources: None,
    auth_token_system: str,
    auth_token_system_user2: str,
    shots_shop_di,
    shop_worker,
) -> dict[str, object]:
    """Один раз на воркер: demo-витрины + контент сервисов для кадров."""
    _ = _ui_e2e_company_resources
    shops = await seed_content.seed_demo_shops(
        shots_shop_di, company_id=ui_e2e_company_id(), token=auth_token_system
    )
    seeds = await seed_content.seed_service_content(
        token=auth_token_system, member_token=auth_token_system_user2
    )
    seeds["shops"] = shops
    return seeds
