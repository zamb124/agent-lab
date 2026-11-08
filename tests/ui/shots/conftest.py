"""Фикстуры маркетинговых скриншотов.

Браузерный контекст с ``device_scale_factor=2`` (PNG ~2880px по ширине),
auth-cookie владельца worker-компании и сиднутый демо-контент всех сервисов.
Кадры пишутся в ``tests/ui/shots/out/<name>.png`` — отсюда их забирает
``scripts/tools/land_optimize.py`` в ``apps/frontend/ui/assets/images/land``.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import pytest
import pytest_asyncio
from playwright.async_api import Browser, BrowserContext, Page, expect

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


async def dismiss_cookie_banner(page: Page) -> None:
    """Снять баннер cookie-согласия основной кнопкой до скрытия панели.

    Баннер может не рендериться (legal-роуты, уже сохранённое согласие) —
    тогда просто выходим.
    """
    try:
        handle = await page.wait_for_selector(
            "cookie-consent-banner .panel", state="visible", timeout=8_000
        )
    except Exception:
        return
    if handle is None:
        return
    btn = page.locator(
        "cookie-consent-banner .cosmic-btn--primary:visible"
    ).first
    await btn.click()
    await expect(
        page.locator("cookie-consent-banner .panel")
    ).to_be_hidden(timeout=10_000)


# micro.osm: Тверская 1 — центральная точка фикстуры.
GEO_FIXTURE_CENTER = (37.6173, 55.7501)


async def wait_geo_map_ready(
    page: Page,
    *,
    center: tuple[float, float] = GEO_FIXTURE_CENTER,
    zoom: float = 16.5,
    sources: dict[str, int] | None = None,
    timeout_s: float = 45.0,
    nth: int = 0,
) -> None:
    """platform-map: камера на micro.osm и векторная подложка до idle."""
    el = page.locator("platform-map").nth(nth)
    await expect(el).to_be_visible(timeout=30_000)
    await expect(
        page.locator("canvas.maplibregl-canvas").nth(nth)
    ).to_be_visible(timeout=30_000)
    await el.evaluate(
        "(el, c) => el.getMap().jumpTo({ center: c.center, zoom: c.zoom })",
        {"center": [center[0], center[1]], "zoom": zoom},
    )
    deadline = time.monotonic() + timeout_s
    while True:
        ready = await el.evaluate(
            "(el) => { const m = el.getMap(); return m.loaded() && m.areTilesLoaded(); }"
        )
        if ready is True:
            break
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"platform-map не дорендерил подложку за {timeout_s}s"
            )
        await page.wait_for_timeout(300)
    for source, minimum in (sources or {}).items():
        await _wait_geo_source_features(page, source, minimum, nth=nth)


async def _wait_geo_source_features(
    page: Page, source: str, minimum: int, *, nth: int = 0, timeout_s: float = 20.0
) -> None:
    """Фичи geojson-source: поллинг, headless rAF ненадёжен."""
    deadline = time.monotonic() + timeout_s
    count = 0
    while True:
        count = await page.locator("platform-map").nth(nth).evaluate(
            """(el, src) => {
                const s = el.getMap().getSource(src);
                const data = s ? s.serialize().data : null;
                return data && data.features ? data.features.length : -1;
            }""",
            source,
        )
        if count >= minimum:
            return
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"geo source {source}: {count} фич < {minimum} за {timeout_s}s"
            )
        await page.wait_for_timeout(400)


async def click_geo_map_at(
    page: Page, lng_lat: tuple[float, float], *, nth: int = 0
) -> None:
    """Клик по карте в lngLat-точке через project → реальные координаты canvas."""
    pt = await page.locator("platform-map").nth(nth).evaluate(
        "(el, ll) => { const p = el.getMap().project(ll); return {x: p.x, y: p.y}; }",
        [lng_lat[0], lng_lat[1]],
    )
    box = await page.locator("canvas.maplibregl-canvas").nth(nth).bounding_box()
    if box is None:
        raise AssertionError("maplibre canvas без bounding box")
    await page.mouse.click(box["x"] + float(pt["x"]), box["y"] + float(pt["y"]))


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
async def geo_directory_ready(setup_database_before_tests) -> None:
    """micro.osm импортирован: тот же тик, что у geo-e2e, через живого geo_worker."""
    from apps.geo.models.geo_import_state import GeoImportState, GeoImportStatus
    from apps.geo.tasks.task_names import GEO_OSM_SYNC_TICK
    from core.tasks import enqueue
    from tests.fixtures.workers import require_taskiq_worker

    _ = setup_database_before_tests
    require_taskiq_worker("geo_worker", "geo")
    state = await GeoImportState.get_state()
    if state is not None and state.current_generation > 0:
        return
    _ = await enqueue(GEO_OSM_SYNC_TICK, background_kind="background")
    deadline = time.monotonic() + 120.0
    while time.monotonic() < deadline:
        state = await GeoImportState.get_state()
        if state is None:
            await asyncio.sleep(0.5)
            continue
        if state.status == GeoImportStatus.FAILED:
            raise AssertionError(f"geo импорт упал: {state.last_error}")
        if state.current_generation > 0 and state.status == GeoImportStatus.IDLE:
            return
        await asyncio.sleep(0.5)
    raise AssertionError("geo импорт не опубликовал поколение за 120s")


@pytest_asyncio.fixture(scope="session")
async def marketing_seeded(
    _ui_e2e_company_resources: None,
    auth_token_system: str,
    auth_token_system_user2: str,
    shots_shop_di,
    shop_worker,
    geo_directory_ready,
) -> dict[str, object]:
    """Один раз на воркер: demo-витрины + контент сервисов для кадров."""
    _ = _ui_e2e_company_resources
    _ = geo_directory_ready
    shops = await seed_content.seed_demo_shops(
        shots_shop_di, company_id=ui_e2e_company_id(), token=auth_token_system
    )
    seeds = await seed_content.seed_service_content(
        token=auth_token_system, member_token=auth_token_system_user2
    )
    failed = {
        key: res["error"]
        for key, res in seeds.items()
        if isinstance(res, dict) and "error" in res
    }
    if failed:
        raise AssertionError(f"маркетинговый сид упал: {failed}")
    seeds["shops"] = shops
    return seeds
