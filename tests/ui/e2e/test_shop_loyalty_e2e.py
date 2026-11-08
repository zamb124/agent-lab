"""Лояльность в браузере: карточка прогресса, тумблер награды в чекауте.

Продовый путь: реальный Granian :9027, программа goal=1/100 ₽ через
админский REST, первый заказ через UI → ``done`` → карточка «Награда
доступна» во вкладке «Заказы» → второй заказ с тумблером награды →
строка скидки в шите и детали заказа, возврат награды при отмене.
Скриншоты — artifacts/shop-loyalty/.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import httpx2
import pytest
import pytest_asyncio
from playwright.async_api import Page, ViewportSize, expect

from core.types import JsonValue, require_json_object
from tests.ui.e2e.test_shop_customer_auth_e2e import (
    _auth,
    _enter_phone,
    _page_url,
    _phone,
)
from tests.ui.e2e.test_shop_storefront_desktop import (
    Storefront,
    _create_storefront,
)
from tests.ui.e2e_worker import ui_e2e_scope_headers

_SHOP_API = "/shop/api/v1"
_PHONE = ViewportSize(width=390, height=844)
_ARTIFACTS = Path(__file__).resolve().parents[3] / "artifacts" / "shop-loyalty"


@pytest_asyncio.fixture
async def loyalty_storefront(
    shop_client_http: httpx2.AsyncClient,
    shop_worker: None,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> Storefront:
    """Витрина с лояльностью: каждый заказ — награда 100 ₽."""
    sf = await _create_storefront(
        shop_client_http,
        {**auth_headers_system, **ui_e2e_scope_headers()},
        f"e2ly{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=1,
        shop_patch={
            "delivery_enabled": True,
            "pickup_enabled": True,
            "features": {"loyalty": True},
        },
    )
    resp = await shop_client_http.put(
        f"{_SHOP_API}/shops/{sf.shop_id}/loyalty",
        json={"orders_goal": 1, "reward_kind": "discount_minor", "reward_value": 10000},
        headers={**auth_headers_system, **ui_e2e_scope_headers()},
    )
    assert resp.status_code == 200, resp.text
    return sf


async def _shot(page: Page, name: str, slug: str) -> None:
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    _ = await page.add_style_tag(
        content="*{animation:none!important;transition:none!important}"
        + "body{position:relative!important}"
        + ".acctnav,.cart,.sheet,.toast,.bdrop{position:absolute!important}"
    )
    _ = await page.screenshot(path=str(_ARTIFACTS / f"{slug}-{name}.png"), full_page=True)


async def _order_id(
    client: httpx2.AsyncClient, headers: dict[str, str], shop_id: str, code: str
) -> str:
    resp = await client.get(f"{_SHOP_API}/shops/{shop_id}/orders", headers=headers)
    assert resp.status_code == 200, resp.text
    items = require_json_object(cast("JsonValue", resp.json()), "orders")["items"]
    assert isinstance(items, list)
    return next(
        str(o["shop_order_id"])
        for o in items
        if isinstance(o, dict) and o.get("public_code") == code
    )


async def _set_status(
    client: httpx2.AsyncClient,
    headers: dict[str, str],
    shop_id: str,
    order_id: str,
    status: str,
) -> None:
    resp = await client.post(
        f"{_SHOP_API}/shops/{shop_id}/orders/{order_id}/status",
        params={"status": status},
        headers=headers,
    )
    assert resp.status_code == 200, f"{status}: {resp.status_code} {resp.text}"


async def _place_order(page: Page, sf: Storefront, phone: str) -> str:
    """Заказ через UI: позиция → корзина → адрес → auth → трекинг."""
    _ = await page.goto(_page_url(sf.slug), wait_until="load")
    await expect(page.locator(".item").first).to_be_visible()
    await page.locator(f".item[data-pid='{sf.plain_product_id}'] .add").click()
    await expect(page.locator("#cart.show")).to_be_visible()
    await page.locator("#cart").click()
    await expect(page.locator("#sheet.show")).to_be_visible()
    await page.locator("#ca").fill("Тверская, 1")
    await page.locator("#payBtn").click()
    await expect(_auth(page).locator(".sheet")).to_be_visible()
    await _enter_phone(page, phone)
    methods = _auth(page).locator("button.method")
    await expect(methods.first).to_be_visible()
    await methods.filter(has_text="Эмулятор").click()
    code_el = page.locator(".done .code")
    await expect(code_el).to_be_visible(timeout=15_000)
    code = (await code_el.text_content()) or ""
    await page.keyboard.press("Escape")
    await expect(page.locator("#sheet.show")).to_have_count(0)
    return code.lstrip("#").strip()


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(150)
async def test_loyalty_reward_full_cycle(
    page: Page,
    loyalty_storefront: Storefront,
    shop_client_http: httpx2.AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    """done-заказ → награда → тумблер в чекауте → скидка → отмена возвращает."""
    sf = loyalty_storefront
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    await page.set_viewport_size(_PHONE)
    phone = _phone(unique_id)

    # Первый заказ через UI и доводка до done — награда начислена.
    code = await _place_order(page, sf, phone)
    assert code
    order_id = await _order_id(shop_client_http, headers, sf.shop_id, code)
    for status in ("accepted", "preparing", "done"):
        await _set_status(shop_client_http, headers, sf.shop_id, order_id, status)

    # Вкладка «Заказы»: карточка лояльности с доступной наградой.
    _ = await page.goto(_page_url(sf.slug) + "?tab=orders&fresh=1", wait_until="load")
    card = page.locator(".loycard")
    await expect(card).to_be_visible(timeout=15_000)
    await expect(card.locator(".loybadge")).to_have_text("Награда доступна")
    await expect(card.locator(".loytxt")).to_contain_text("скидка 100")
    await _shot(page, "phone-loyalty-card", sf.slug)

    # Второй заказ: тумблер награды в шите чекаута.
    await page.locator(".acctnav [data-tab='catalog']").click()
    await page.locator(f".item[data-pid='{sf.plain_product_id}'] .add").click()
    await page.locator("#cart").click()
    await expect(page.locator("#sheet.show")).to_be_visible()
    loy = page.locator("#loyRow")
    await expect(loy).to_be_visible(timeout=10_000)
    await expect(loy.locator(".loysub")).to_contain_text("−100")
    await loy.click()
    await expect(loy.locator(".lswt")).to_have_class("lswt on")
    await expect(page.locator(".loysave")).to_contain_text("Награда лояльности")
    await _shot(page, "phone-loyalty-toggle", sf.slug)

    # Подтверждение: сессия уже есть — заказ уходит сразу со скидкой.
    await page.locator("#ca").fill("Тверская, 1")
    await page.locator("#payBtn").click()
    code_el = page.locator(".done .code")
    await expect(code_el).to_be_visible(timeout=15_000)
    code2 = ((await code_el.text_content()) or "").lstrip("#").strip()
    assert code2
    await page.keyboard.press("Escape")
    await expect(page.locator("#sheet.show")).to_have_count(0)

    # Деталь заказа: строка «Награда лояльности» в тоталах.
    _ = await page.goto(
        _page_url(sf.slug) + f"?tab=orders&order={code2}&fresh=2", wait_until="load"
    )
    trow = page.locator(".trow", has_text="Награда лояльности")
    await expect(trow).to_be_visible(timeout=15_000)
    await expect(trow).to_contain_text("100")
    await _shot(page, "phone-loyalty-detail", sf.slug)

    # Отмена заказа — награда возвращается на счёт.
    order_id2 = await _order_id(shop_client_http, headers, sf.shop_id, code2)
    await _set_status(shop_client_http, headers, sf.shop_id, order_id2, "cancelled")
    _ = await page.goto(_page_url(sf.slug) + "?tab=orders&fresh=3", wait_until="load")
    await expect(page.locator(".loycard .loybadge")).to_have_text(
        "Награда доступна", timeout=15_000
    )
    await _shot(page, "phone-loyalty-refunded", sf.slug)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_loyalty_feature_disabled_hides_ui(
    page: Page,
    shop_client_http: httpx2.AsyncClient,
    shop_worker: None,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    """features.loyalty=false: ни карточки, ни строки в шите — без следа."""
    _ = shop_worker
    sf = await _create_storefront(
        shop_client_http,
        {**auth_headers_system, **ui_e2e_scope_headers()},
        f"e2ld{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=1,
        shop_patch={
            "delivery_enabled": True,
            "pickup_enabled": True,
            "features": {"loyalty": False},
        },
    )
    await page.set_viewport_size(_PHONE)
    _ = await page.goto(_page_url(sf.slug), wait_until="load")
    await expect(page.locator(".item").first).to_be_visible()
    await page.locator(f".item[data-pid='{sf.plain_product_id}'] .add").click()
    await page.locator("#cart").click()
    await expect(page.locator("#sheet.show")).to_be_visible()
    await expect(page.locator("#loyRow")).to_have_count(0)
    await page.keyboard.press("Escape")
    _ = await page.goto(_page_url(sf.slug) + "?tab=orders&fresh=1", wait_until="load")
    await page.locator(".acctnav [data-tab='orders']").click()
    await expect(page.locator(".loycard")).to_have_count(0)
    await _shot(page, "phone-loyalty-off", sf.slug)
