"""Чекаут доставки в браузере: автокомплит, зона, детали адреса, карта-пин.

Продовый путь: Granian :9027 + реальный geo-сервис (OSM-экстракт Москвы
в тестовом стеке): «Тверская» резолвится справочником и попадает в зону
фикстуры; карта грузит настоящий maplibre-бандл и тайлы через
``/public/geo/*`` прокси. Скриншот-матрица — artifacts/shop-checkout/.
"""

from __future__ import annotations

from pathlib import Path

import httpx2
import pytest
import pytest_asyncio
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.apps import SERVICE_UI_REGISTRY
from tests.ui.e2e.test_shop_customer_auth_e2e import _page_url
from tests.ui.e2e.test_shop_delivery_e2e import (
    _ZONE,
    _cart_to_sheet,
    _emulator_auth,
    zoned_storefront,  # noqa: F401 — фикстура
)
from tests.ui.e2e.test_shop_storefront_desktop import Storefront
from tests.ui.e2e.test_shop_feed_e2e import _PHONE, _shot
from tests.ui.harness import AppUI

_SHOP_UI = AppUI(SERVICE_UI_REGISTRY["shop"])


@pytest_asyncio.fixture
async def _viewport(page: Page) -> None:
    await page.set_viewport_size(_PHONE)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_delivery_address_form_and_suggest(
    page: Page, zoned_storefront: Storefront, _viewport: None
) -> None:
    """Форма доставки: поле адреса, кнопка карты, детали, автокомплит с зоной."""
    await _cart_to_sheet(page, zoned_storefront)
    await expect(page.locator("#ca")).to_be_visible()
    await expect(page.locator(".amapbtn")).to_be_visible()
    await expect(page.locator(".dgrid input")).to_have_count(4)

    await page.locator("#ca").fill("Тверская")
    sug = page.locator("#caSug")
    await expect(sug).to_have_class("sug open", timeout=15_000)
    rows = sug.locator(".sugrow")
    await expect(rows.first).to_be_visible()
    assert await rows.count() > 0
    await _shot(page, "phone-suggest", zoned_storefront.slug)

    await rows.first.click()
    await expect(page.locator("#zoneStat")).to_have_class("zstat ok", timeout=15_000)
    await expect(page.locator("#payBtn")).to_be_enabled()
    await _shot(page, "phone-zone-ok", zoned_storefront.slug)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_suggest_keyboard_and_empty_hint(
    page: Page, zoned_storefront: Storefront, _viewport: None, unique_id: str
) -> None:
    """Клавиатура: стрелка вниз подсвечивает строку, Enter выбирает; мусор → хинт."""
    await _cart_to_sheet(page, zoned_storefront)
    await page.locator("#ca").fill("Тверская")
    sug = page.locator("#caSug")
    await expect(sug).to_have_class("sug open", timeout=15_000)

    await page.locator("#ca").press("ArrowDown")
    first = sug.locator(".sugrow").first
    await expect(first).to_have_class("sugrow on")
    name = await first.get_attribute("data-name")
    await page.locator("#ca").press("Enter")
    await expect(page.locator("#ca")).to_have_value(name or "")
    await expect(sug).not_to_have_class("sug open")

    await page.locator("#ca").fill(f"Несуществующий {unique_id[:8]}")
    await expect(sug.locator(".sugempty")).to_be_visible(timeout=15_000)
    await expect(sug.locator(".sugempty")).to_contain_text("не найден")


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_address_map_sheet_pick_point(
    page: Page, zoned_storefront: Storefront, _viewport: None
) -> None:
    """Шит карты: центр-пин, зона, подтверждение пишет точку и запускает zoneCheck."""
    await _cart_to_sheet(page, zoned_storefront)
    await page.locator(".amapbtn").click()
    sheet = page.locator("#asheet")
    await expect(sheet).to_have_class("sheet show", timeout=10_000)
    await expect(sheet.locator("#amapPin")).to_be_visible()
    # maplibre-бандл ленивый: ждём реальную карту с канвой.
    await expect(sheet.locator("platform-map canvas")).to_be_visible(timeout=45_000)
    await _shot(page, "phone-map-sheet", zoned_storefront.slug)

    confirm = sheet.locator("#amapBtn")
    await expect(confirm).to_be_enabled(timeout=15_000)
    await confirm.click()
    await expect(sheet).not_to_have_class("sheet show")
    await expect(page.locator("#zoneStat")).to_have_class("zstat ok", timeout=15_000)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_dtype_switch_resets_address_state(
    page: Page, zoned_storefront: Storefront, _viewport: None
) -> None:
    """Самовывоз/обратно: адресный блок пересоздаётся чистым, зона не наследуется."""
    await _cart_to_sheet(page, zoned_storefront)
    await page.locator("#ca").fill("Тверская")
    sug = page.locator("#caSug")
    await expect(sug.locator(".sugrow").first).to_be_visible(timeout=15_000)
    await sug.locator(".sugrow").first.click()
    await expect(page.locator("#zoneStat")).to_have_class("zstat ok", timeout=15_000)

    await page.locator(".seg button", has_text="Самовывоз").click()
    await expect(page.locator("#ca")).to_have_count(0)

    await page.locator(".seg button", has_text="Доставка").click()
    await expect(page.locator("#ca")).to_be_visible()
    await expect(page.locator("#ca")).to_have_value("")
    # Старый zoneOk не «проталкивает» заказ с пустым адресом.
    await expect(page.locator("#payBtn")).to_be_disabled()


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_details_reach_order(
    page: Page, zoned_storefront: Storefront, _viewport: None, unique_id: str
) -> None:
    """Кв/подъезд/этаж/домофон + точка подсказки доезжают до созданного заказа."""
    await _cart_to_sheet(page, zoned_storefront)
    await page.locator("#ca").fill("Тверская")
    sug = page.locator("#caSug")
    await expect(sug.locator(".sugrow").first).to_be_visible(timeout=15_000)
    await sug.locator(".sugrow").first.click()
    await expect(page.locator("#zoneStat")).to_have_class("zstat ok", timeout=15_000)

    await page.locator("#dflat").fill("12")
    await page.locator("#dentrance").fill("3")
    await page.locator("#dfloor").fill("5")
    await page.locator("#dintercom").fill("123К")
    await _shot(page, "phone-details", zoned_storefront.slug)

    await page.locator("#payBtn").click()
    await _emulator_auth(page, f"+7999{int(unique_id[:8], 16) % 10**7:07d}")
    await expect(page.locator(".done .code")).to_be_visible(timeout=20_000)
    await _shot(page, "phone-done", zoned_storefront.slug)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_admin_settings_delivery_section(
    ui_page_system: Page, zoned_storefront: Storefront
) -> None:
    """SPA настроек: секция доставки — карта зоны, пин магазина, поля lat/lng."""
    await ui_page_system.set_viewport_size(ViewportSize(width=1440, height=900))
    await ui_page_system.goto(
        f"{_SHOP_UI.spa_url()}{zoned_storefront.shop_id}/settings",
        wait_until="load",
    )
    ui_page_system.on(
        "console",
        lambda m: print("SPA CONSOLE:", m.type, m.text[:200])
        if m.type in ("error", "warning")
        else None,
    )
    try:
        await expect(ui_page_system.locator(".nav")).to_be_visible(timeout=45_000)
    except AssertionError:
        await _shot(ui_page_system, "admin-settings-debug", zoned_storefront.slug)
        print("PAGE URL:", ui_page_system.url)
        raise
    nav = ui_page_system.locator(".nav-item", has_text="Выдача заказов")
    await expect(nav).to_be_visible(timeout=30_000)
    await nav.click()
    # Карта зоны с draggable-пином магазина + пара координатных полей.
    await expect(ui_page_system.locator(".zone-map-wrap platform-map")).to_be_visible(
        timeout=45_000
    )
    await expect(ui_page_system.locator(".zone-map-wrap .open-editor")).to_be_visible()
    fields = ui_page_system.locator(".option-fields platform-field")
    await expect(fields).to_have_count(6, timeout=15_000)
    await _shot(ui_page_system, "admin-delivery", zoned_storefront.slug)
