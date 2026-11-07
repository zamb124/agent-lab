"""Отзывы на заказ в браузере: шит оценки, вкладка «Отзывы», бейдж рейтинга.

Продовый путь: реальный Granian :9027, заказ через UI (корзина →
эмулятор customer-auth → трекинг), перевод в ``done`` админским REST,
оценка в кабинете покупателя. Скриншоты — artifacts/shop-feedback/.
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
_DESKTOP = ViewportSize(width=1440, height=900)
_ARTIFACTS = Path(__file__).resolve().parents[3] / "artifacts" / "shop-feedback"


@pytest_asyncio.fixture
async def feedback_storefront(
    shop_client_http: httpx2.AsyncClient,
    shop_worker: None,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> Storefront:
    """Минимальная витрина с доставкой — для заказа через UI."""
    return await _create_storefront(
        shop_client_http,
        {**auth_headers_system, **ui_e2e_scope_headers()},
        f"e2fb{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=1,
        shop_patch={"delivery_enabled": True, "pickup_enabled": True},
    )


async def _shot(page: Page, name: str, slug: str) -> None:
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    _ = await page.add_style_tag(
        content="*{animation:none!important;transition:none!important}"
        + "body{position:relative!important}"
        + ".acctnav,.cart,.sheet,.toast,.bdrop{position:absolute!important}"
    )
    _ = await page.screenshot(path=str(_ARTIFACTS / f"{slug}-{name}.png"), full_page=True)


async def _place_order(page: Page, sf: Storefront, phone: str) -> str:
    """Заказ через UI: позиция → корзина → адрес → auth → экран трекинга."""
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
    # Экран «Заказ принят» — открытый шит поверх витрины: закрываем как пользователь.
    await page.keyboard.press("Escape")
    await expect(page.locator("#sheet.show")).to_have_count(0)
    return code.lstrip("#").strip()


async def _mark_done(
    client: httpx2.AsyncClient,
    headers: dict[str, str],
    shop_id: str,
    public_code: str,
) -> None:
    """Админская цепочка статусов new → … → done по реальному REST."""
    resp = await client.get(f"{_SHOP_API}/shops/{shop_id}/orders", headers=headers)
    assert resp.status_code == 200, resp.text
    items = require_json_object(cast("JsonValue", resp.json()), "orders")["items"]
    assert isinstance(items, list)
    order_id = next(
        str(o["shop_order_id"]) for o in items
        if isinstance(o, dict) and o.get("public_code") == public_code
    )
    url = f"{_SHOP_API}/shops/{shop_id}/orders/{order_id}/status"
    for status in ("accepted", "preparing", "done"):
        resp = await client.post(url, params={"status": status}, headers=headers)
        assert resp.status_code == 200, f"{status}: {resp.status_code} {resp.text}"


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_feedback_order_done_rate_and_reviews_tab(
    page: Page,
    feedback_storefront: Storefront,
    shop_client_http: httpx2.AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    """Заказ → done → карточка оценки → отправка → вкладка «Отзывы» → бейдж."""
    sf = feedback_storefront
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    await page.set_viewport_size(_PHONE)
    code = await _place_order(page, sf, _phone(unique_id))
    assert code

    await _mark_done(shop_client_http, headers, sf.shop_id, code)

    # Лента заказов: карточка с призывом «Оценить заказ».
    await page.locator(".acctnav [data-tab='orders']").click()
    card = page.locator(".acard", has_text=code)
    await expect(card).to_be_visible()
    await expect(card.locator(".revline")).to_contain_text("Оценить заказ")
    await card.click()

    # Форма оценки: звёзды → чипы + комментарий → отправка.
    fb = page.locator(".acard.fb")
    await expect(fb).to_be_visible()
    await expect(fb.locator(".fbt")).to_have_text("Как вам заказ?")
    stars = fb.locator(".fstar")
    await expect(stars).to_have_count(5)
    await stars.nth(3).click()
    await expect(fb.locator(".fchip").first).to_be_visible()
    await fb.locator(".fchip").first.click()
    await fb.locator(".fbtext").fill("Очень вкусно и быстро")
    await _shot(page, "phone-feedback-form", sf.slug)
    await fb.locator("[data-role='send']").click()

    # Оценка принята: сводка «Ваша оценка», чип, комментарий, «Изменить».
    await expect(fb.locator(".fbt")).to_have_text("Ваша оценка", timeout=10_000)
    await expect(fb.locator(".fbcmt")).to_have_text("Очень вкусно и быстро")
    await expect(fb.locator(".fbedit")).to_be_visible()
    await _shot(page, "phone-feedback-done", sf.slug)

    # Вкладка «Отзывы»: сводка рейтинга и карточка отзыва.
    await page.locator(".acctnav [data-tab='reviews']").click()
    await expect(page.locator(".rsum .rnum")).to_have_text("4.0", timeout=10_000)
    ritem = page.locator(".ritem").first
    await expect(ritem).to_be_visible()
    await expect(ritem.locator(".rcomment")).to_have_text("Очень вкусно и быстро")
    await _shot(page, "phone-reviews-tab", sf.slug)

    # Витрина: бейдж рейтинга в мета-строке hero. Страница кэшируется
    # браузером 30 c — уходим от старого HTML свежим query-параметром.
    await page.locator(".acctnav [data-tab='menu']").click()
    _ = await page.goto(_page_url(sf.slug) + "?fresh=1", wait_until="load")
    rate = page.locator(".meta .rate")
    await expect(rate).to_be_visible()
    await expect(rate).to_contain_text("4.0 · 1")
    await _shot(page, "phone-rating-badge", sf.slug)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_reviews_feature_disabled_hides_ui(
    page: Page,
    shop_client_http: httpx2.AsyncClient,
    shop_worker: None,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    """features.reviews=false: ни вкладки «Отзывы», ни бейджа — без следа."""
    _ = shop_worker
    sf = await _create_storefront(
        shop_client_http,
        {**auth_headers_system, **ui_e2e_scope_headers()},
        f"e2fd{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=1,
        shop_patch={
            "delivery_enabled": True,
            "pickup_enabled": True,
            "features": {"reviews": False},
        },
    )
    await page.set_viewport_size(_PHONE)
    _ = await page.goto(_page_url(sf.slug), wait_until="load")
    await expect(page.locator(".item").first).to_be_visible()
    await expect(page.locator(".acctnav [data-tab='reviews']")).to_have_count(0)
    await expect(page.locator(".meta .rate")).to_have_count(0)
    await _shot(page, "phone-reviews-off", sf.slug)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_reviews_desktop_layout(
    page: Page,
    feedback_storefront: Storefront,
    shop_client_http: httpx2.AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    """Десктоп: шапка-табы, отзыв после оценки — снимок в матрицу."""
    sf = feedback_storefront
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    await page.set_viewport_size(_DESKTOP)
    code = await _place_order(page, sf, _phone(unique_id))
    await _mark_done(shop_client_http, headers, sf.shop_id, code)
    await page.locator(".ahead [data-tab='orders']").click()
    await page.locator(".acard", has_text=code).click()
    fb = page.locator(".acard.fb")
    await expect(fb).to_be_visible()
    await fb.locator(".fstar").nth(4).click()
    await fb.locator(".fbtext").fill("Идеально")
    await fb.locator("[data-role='send']").click()
    await expect(fb.locator(".fbt")).to_have_text("Ваша оценка", timeout=10_000)
    await page.locator(".ahead [data-tab='reviews']").click()
    await expect(page.locator(".rsum")).to_be_visible(timeout=10_000)
    await expect(page.locator(".ritem").first).to_be_visible()
    await _shot(page, "desktop-reviews", sf.slug)
