"""Документационный сценарий Shop: зона доставки на карте.

Маршрут владельца: настройки → «Доставка» → зона на карте →
редактор полигона → витрина проверяет адрес покупателя по зоне.
"""

from __future__ import annotations

import httpx2
import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.test_shop_customer_auth_e2e import _page_url
from tests.ui.e2e.test_shop_delivery_e2e import _ZONE
from tests.ui.e2e.test_shop_storefront_desktop import _create_storefront
from tests.ui.e2e_worker import ui_e2e_scope_headers
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="shop",
    tag="delivery",
    doc_slug="delivery-zone-map",
    title="Зона доставки на карте и проверка адреса покупателя",
    title_en="Delivery zone on the map and the customer's address check",
    description=(
        "**Для чего:** зона доставки — полигон на карте, внутри "
        "которого вы привозите заказы. Витрина сама проверяет адрес "
        "покупателя по этой зоне.\n\n"
        "**Какие проблемы решает:** заказы вне зоны не проходят "
        "оформление — не придётся звонить и отменять вручную. "
        "Покупатель видит проверку сразу, ещё до оплаты.\n\n"
        "**Результат:** полигон виден на карте в настройках и в "
        "редакторе зоны; на витрине адрес внутри зоны получает "
        "зелёную отметку."
    ),
    description_en=(
        "**Purpose:** the delivery zone is a polygon on the map where "
        "you deliver. The storefront checks the customer's address "
        "against it.\n\n"
        "**Problems solved:** orders outside the zone never reach "
        "checkout — no manual calls and cancellations. The customer "
        "sees the check before paying.\n\n"
        "**Result:** the polygon is visible on the settings map and "
        "in the zone editor; an address inside the zone gets a green "
        "badge on the storefront."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_delivery_zone_map(
    shop_client_http: httpx2.AsyncClient,
    shop_worker: None,
    auth_headers_system: dict[str, str],
    shop_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    scenario: ScenarioRecorder,
) -> None:
    _ = shop_worker
    page = ui_page_system
    storefront = await _create_storefront(
        shop_client_http,
        {**auth_headers_system, **ui_e2e_scope_headers()},
        f"zone{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=2,
        shop_patch={
            "delivery_enabled": True,
            "pickup_enabled": True,
            "delivery_zone": _ZONE,
        },
    )

    await shop_ui.open(page)
    await page.set_viewport_size(_DESKTOP)
    await page.goto(
        f"{shop_ui.spa_url()}{storefront.shop_id}/settings?section=delivery",
        wait_until="load",
    )
    wrap = page.locator(".zone-map-wrap")
    await expect(wrap).to_be_visible(timeout=45_000)
    await expect(wrap.locator(".maplibregl-canvas")).to_be_visible(timeout=45_000)
    await expect(wrap.locator(".pm-overlay")).to_have_count(0, timeout=45_000)
    open_editor = wrap.locator(".open-editor")
    await expect(open_editor).to_be_visible(timeout=15_000)
    await scenario.step(
        "Зона доставки в настройках",
        page,
        screenshot_name="settings-zone-map",
        label_en="Delivery zone in settings",
        details=(
            "Настройки → «Доставка»: карта показывает полигон зоны — "
            "куда вы возите заказы. Точка магазина на той же карте "
            "ставится одним кликом."
        ),
        details_en=(
            "Settings → Delivery: the map shows the zone polygon — "
            "where you deliver. The shop's own point sits on the same "
            "map, set with one click."
        ),
    )

    await open_editor.click()
    editor = page.locator("platform-zone-editor-modal")
    await expect(editor).to_be_visible(timeout=15_000)
    await expect(
        editor.locator(".maplibregl-canvas")
    ).to_be_visible(timeout=45_000)
    await expect(editor.locator(".zstats")).to_be_visible(timeout=15_000)
    await scenario.step(
        "Редактор зоны",
        page,
        screenshot_name="zone-editor",
        label_en="Zone editor",
        details=(
            "Кнопка «Изменить зону» открывает редактор: инструмент "
            "«Рисовать» ставит вершины полигона кликами, «Вместить» "
            "кадрирует карту по зоне, «Очистить» начинает заново. "
            "Площадь и периметр считаются сразу."
        ),
        details_en=(
            "The Edit zone button opens the editor: the Draw tool "
            "places polygon vertices with clicks, Fit frames the map "
            "to the zone, Clear starts over. Area and perimeter are "
            "computed live."
        ),
    )
    await page.keyboard.press("Escape")
    await expect(editor).to_have_count(0, timeout=10_000)

    _ = await page.goto(
        f"{_page_url(storefront.slug)}?tmode=light", wait_until="load"
    )
    await expect(page.locator(".item").first).to_be_visible(timeout=30_000)
    await page.locator(
        f".item[data-pid='{storefront.plain_product_id}'] .add"
    ).click()
    await expect(page.locator("#cart.show")).to_be_visible()
    await page.locator("#cart").click()
    await expect(page.locator("#sheet.show")).to_be_visible()

    # Точка на карте: пин в центре, зона — подложкой; локальный ray-cast
    # решает «в зоне» ещё до запроса на сервер.
    await page.locator(".amapbtn").click()
    asheet = page.locator("#asheet")
    await expect(asheet.locator(".maplibregl-canvas")).to_be_visible(
        timeout=45_000
    )
    confirm = page.locator("#amapBtn")
    await expect(confirm).to_be_enabled(timeout=15_000)
    await scenario.step(
        "Выбор точки на карте",
        page,
        screenshot_name="storefront-map-pick",
        label_en="Picking the point on the map",
        details=(
            "Если адрес не подсказывается, покупатель открывает карту "
            "кнопкой у поля адреса и двигает её под пином. Полигон "
            "зоны виден под картой: внутри — «Доставить сюда», "
            "снаружи кнопка неактивна."
        ),
        details_en=(
            "If the address is not suggested, the customer opens the "
            "map next to the address field and moves it under the pin. "
            "The zone polygon is visible under the map: inside — "
            "Deliver here, outside the button is disabled."
        ),
    )

    await confirm.click()
    await expect(page.locator("#zoneStat")).to_have_class(
        "zstat ok", timeout=15_000
    )
    await scenario.step(
        "Адрес проверен по зоне",
        page,
        screenshot_name="storefront-zone-ok",
        label_en="Address checked against the zone",
        details=(
            "Витрина проверила точку по полигону — зелёная отметка "
            "«Доставим» означает: заказ можно оформить и привезти."
        ),
        details_en=(
            "The storefront checked the point against the polygon — "
            "the green Deliver badge means the order can be placed "
            "and delivered."
        ),
    )
