"""Витрина Shop: зоны доставки, адресные чипы и чекаут — реальный браузер.

Продовый путь: Granian :9027, Chromium, анонимный покупатель. В тестовом
окружении GEOCODING__ENABLED=false → live `delivery-check` для зонированного
магазина детерминированно отвечает `address_unverifiable` — ровно тот же
контракт, что ждёт витрина на проде при «адрес вне зоны».
"""

from __future__ import annotations

import httpx2
import pytest
import pytest_asyncio
from playwright.async_api import Page, expect

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

_ZONE = {
    "type": "Polygon",
    "coordinates": [
        [
            [37.5, 55.7],
            [37.7, 55.7],
            [37.7, 55.8],
            [37.5, 55.8],
            [37.5, 55.7],
        ]
    ],
}


@pytest_asyncio.fixture
async def zoned_storefront(
    shop_client_http: httpx2.AsyncClient,
    shop_worker: None,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> Storefront:
    """Витрина с включённой доставкой и GeoJSON-полигоном зоны."""
    return await _create_storefront(
        shop_client_http,
        {**auth_headers_system, **ui_e2e_scope_headers()},
        f"zoned{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=1,
        shop_patch={
            "delivery_enabled": True,
            "pickup_enabled": True,
            "delivery_zone": _ZONE,
        },
    )


@pytest_asyncio.fixture
async def open_storefront(
    shop_client_http: httpx2.AsyncClient,
    shop_worker: None,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> Storefront:
    """Витрина с доставкой без зоны — для потока сохранённых адресов."""
    return await _create_storefront(
        shop_client_http,
        {**auth_headers_system, **ui_e2e_scope_headers()},
        f"open{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=1,
        shop_patch={"delivery_enabled": True, "pickup_enabled": True},
    )


async def _cart_to_sheet(page: Page, storefront: Storefront) -> None:
    _ = await page.goto(_page_url(storefront.slug), wait_until="load")
    await expect(page.locator(".item").first).to_be_visible()
    await page.locator(f".item[data-pid='{storefront.plain_product_id}'] .add").click()
    await expect(page.locator("#cart.show")).to_be_visible()
    await page.locator("#cart").click()
    await expect(page.locator("#sheet.show")).to_be_visible()


async def _emulator_auth(page: Page, phone: str) -> None:
    await expect(_auth(page).locator(".sheet")).to_be_visible()
    await _enter_phone(page, phone)
    methods = _auth(page).locator("button.method")
    await expect(methods.first).to_be_visible()
    await methods.filter(has_text="Эмулятор").click()


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_zoned_delivery_unverifiable_address_blocks_checkout(
    page: Page, zoned_storefront: Storefront, unique_id: str
) -> None:
    """Зона + геокодер не вернул точку → бейдж «не проверить», кнопка и submit заперты."""
    await _cart_to_sheet(page, zoned_storefront)
    # Доставка — способ по умолчанию: ввод адреса запускает live zone-check.
    await page.locator("#ca").fill("Проспект Несуществующий, д. 999")
    stat = page.locator("#zoneStat")
    await expect(stat).to_have_class("zstat bad", timeout=10_000)
    await expect(stat).to_contain_text("проверить")
    # Кнопка оплаты заблокирована до подтверждённой точки внутри зоны.
    await expect(page.locator("#payBtn")).to_be_disabled()
    # Прямой submit тоже не доходит до авторизации.
    await page.evaluate("submit()")
    await page.wait_for_timeout(400)
    assert await _auth(page).locator(".sheet").count() == 0 or not await _auth(
        page
    ).locator(".sheet").is_visible()


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_closed_shop_disables_checkout(
    page: Page,
    shop_client_http: httpx2.AsyncClient,
    shop_worker: None,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    """Магазин закрыт по расписанию → предупреждение + кнопка заказа выключена."""
    storefront = await _create_storefront(
        shop_client_http,
        {**auth_headers_system, **ui_e2e_scope_headers()},
        f"closed{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=1,
        shop_patch={
            "pickup_enabled": True,
            "working_hours": dict.fromkeys(
                (str(d) for d in range(7)), "00:00-00:00"
            ),
        },
    )
    await _cart_to_sheet(page, storefront)
    warn = page.locator(".minwarn", has_text="Сейчас закрыто")
    await expect(warn).to_be_visible()
    await expect(page.locator("#payBtn")).to_be_disabled()
    # Прямой submit тоже не доходит до авторизации.
    await page.evaluate("submit()")
    await page.wait_for_timeout(400)
    assert not await _auth(page).locator(".sheet").is_visible()


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_zoned_pickup_bypasses_address_and_zone(
    page: Page, zoned_storefront: Storefront, unique_id: str
) -> None:
    """Самовывоз на зонированной витрине: адрес не спрашивают, заказ идёт к авторизации."""
    await _cart_to_sheet(page, zoned_storefront)
    await page.locator(".seg button", has_text="Самовывоз").click()
    await expect(page.locator("#ca")).to_have_count(0)
    await expect(page.locator("#zoneStat")).to_have_count(0)
    await expect(page.locator("#payBtn")).to_be_enabled()
    await page.locator("#payBtn").click()
    await expect(_auth(page).locator(".sheet")).to_be_visible()


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_saved_address_chip_prefills_second_checkout(
    page: Page,
    open_storefront: Storefront,
    shop_client_http: httpx2.AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    """Адрес первой доставки → чип в следующем чекауте; выбор чипа заполняет поле."""
    phone = _phone(unique_id)
    address = "Тверская улица, дом 10"
    await _cart_to_sheet(page, open_storefront)
    await page.locator("#ca").fill(address)
    await page.locator("#payBtn").click()
    await _emulator_auth(page, phone)
    await expect(page.locator(".done .code")).to_be_visible(timeout=15_000)

    # Второй визит той же витрины — сессия покупателя переиспользуется,
    # сохранённый адрес приходит чипом поверх поля ввода.
    await page.goto(_page_url(open_storefront.slug), wait_until="load")
    await expect(page.locator(".item").first).to_be_visible()
    await page.locator(
        f".item[data-pid='{open_storefront.plain_product_id}'] .add"
    ).click()
    await page.locator("#cart").click()
    await expect(page.locator("#sheet.show")).to_be_visible()

    chip = page.locator("#addrChips .achip").first
    await expect(chip).to_be_visible(timeout=10_000)
    await expect(chip).to_contain_text("Тверская")
    await chip.click()
    await expect(page.locator("#ca")).to_have_value(address)

    # Заказ с выбранным чипом доходит до done без повторной авторизации.
    await page.locator("#payBtn").click()
    await expect(page.locator(".done .code")).to_be_visible(timeout=15_000)
