"""Настройки витрины в браузере: обязательная точка магазина на карте.

Продовый путь: реальный SPA настроек → клик по platform-map → op_update_shop
→ GET /shops/{id} с координатами. Пин ставится кликом и перетаскиванием,
поля широты/долготы — только точная правка.
"""

from __future__ import annotations

import re
from typing import cast

import httpx2
import pytest
import pytest_asyncio
from playwright.async_api import Page, ViewportSize, expect

from core.types import JsonObject, JsonValue, require_json_object
from tests.ui.apps import SERVICE_UI_REGISTRY
from tests.ui.e2e.test_shop_feed_e2e import _shot
from tests.ui.e2e.test_shop_storefront_desktop import _SHOP_API, _post
from tests.ui.e2e_worker import ui_e2e_scope_headers
from tests.ui.harness import AppUI

_SHOP_UI = AppUI(SERVICE_UI_REGISTRY["shop"])
_DESKTOP = ViewportSize(width=1440, height=900)


@pytest_asyncio.fixture
async def nopoint_shop(
    shop_client_http: httpx2.AsyncClient,
    shop_worker: None,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> JsonObject:
    """Черновик без точки — сценарий первичной настройки директором."""
    slug = f"nop{unique_id[:8]}"
    return await _post(
        shop_client_http,
        {**auth_headers_system, **ui_e2e_scope_headers()},
        "/shops",
        {"slug": slug, "name": f"E2E Витрина {slug}", "kind": "cafe"},
    )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_shop_point_set_by_map_click_and_drag(
    ui_page_system: Page,
    nopoint_shop: JsonObject,
    shop_client_http: httpx2.AsyncClient,
    auth_headers_system: dict[str, str],
) -> None:
    """Клик ставит пин и прячет бейдж; drag двигает точку; save → lat/lng в API."""
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    slug = str(nopoint_shop["slug"])
    shop_id = str(nopoint_shop["shop_id"])
    await ui_page_system.set_viewport_size(_DESKTOP)
    _ = await ui_page_system.goto(
        f"{_SHOP_UI.spa_url()}{shop_id}/settings?section=delivery",
        wait_until="load",
    )
    wrap = ui_page_system.locator(".zone-map-wrap")
    await expect(wrap).to_be_visible(timeout=45_000)

    # Карта видна и без включённой доставки — точка обязательна для любого
    # режима; зона-редактор при этом скрыт (доставки нет — зоны нет).
    delivery_option = ui_page_system.locator(".option").filter(
        has_text=re.compile("Доставка|Delivery")
    )
    await delivery_option.locator("platform-switch").click()
    await expect(ui_page_system.locator(".zone-map-wrap")).to_be_visible(timeout=15_000)
    zone_button = wrap.locator(".open-editor")
    await expect(zone_button).to_have_count(0)
    missing = wrap.locator(".empty-badge.point")
    await expect(missing).to_be_visible(timeout=15_000)

    # Ждём готовности карты: пока идёт загрузка стиля, поверх canvas висит
    # pm-overlay и клики до карты не доходят.
    await expect(wrap.locator(".maplibregl-canvas")).to_be_visible(timeout=45_000)
    await expect(wrap.locator(".pm-overlay")).to_have_count(0, timeout=45_000)

    lat_input = ui_page_system.locator(
        "platform-field[label*='Широта'] input, platform-field[label*='latitude'] input"
    )
    lng_input = ui_page_system.locator(
        "platform-field[label*='Долгота'] input, platform-field[label*='longitude'] input"
    )
    await expect(lat_input).to_have_value("", timeout=15_000)

    # Клик по карте — точка ставится в место клика, бейдж уходит, маркер появляется.
    map_el = wrap.locator("platform-map")
    await map_el.click(position={"x": 260, "y": 120})
    await expect(missing).to_have_count(0, timeout=15_000)
    marker = wrap.locator(".maplibregl-marker")
    await expect(marker).to_have_count(1, timeout=15_000)

    lat_first = await lat_input.input_value()
    lng_first = await lng_input.input_value()
    assert float(lat_first.replace(",", ".")) != 0.0
    assert float(lng_first.replace(",", ".")) != 0.0
    await _shot(ui_page_system, "settings-point-click", slug)

    # Повторный клик в другом месте переносит точку.
    await map_el.click(position={"x": 520, "y": 220})
    await expect(marker).to_have_count(1, timeout=15_000)
    lat_second = await lat_input.input_value()
    assert lat_second != lat_first

    # Drag пина — третий способ сместить точку, поля синхронизируются.
    await marker.drag_to(map_el, target_position={"x": 300, "y": 180})
    lat_third = await lat_input.input_value()
    assert lat_third != lat_second

    save = ui_page_system.locator(".savebar platform-button[variant=primary]")
    await expect(save).not_to_have_attribute("disabled", "", timeout=15_000)
    await save.click()
    await expect(ui_page_system.locator(".savebar")).to_have_count(0, timeout=30_000)

    resp = await shop_client_http.get(
        f"{_SHOP_API}/shops/{shop_id}", headers=headers
    )
    assert resp.status_code == 200, resp.text
    shop = require_json_object(cast("JsonValue", resp.json()), "shop")
    assert isinstance(shop["lat"], (int, float)) and shop["lat"] != 0
    assert isinstance(shop["lng"], (int, float)) and shop["lng"] != 0
    await _shot(ui_page_system, "settings-point-saved", slug)
