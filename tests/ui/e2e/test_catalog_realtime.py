"""Онлайн-обновление списков товаров: shared-каталог → push → SPA без перезагрузки.

Мутации идут через REST-клиенты теста, а не через сокет самой страницы —
строка может появиться только по push ``catalog/product/*``
(delivery=company → Centrifugo → extraEffect ресурса → refetch).
"""

from __future__ import annotations

import re

import httpx2
import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.stock_e2e_helpers import stock_e2e_nav, stock_e2e_open
from tests.ui.e2e.test_shop_storefront_desktop import _create_storefront
from tests.ui.e2e_worker import ui_e2e_scope_headers
from tests.ui.harness import AppUI

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_stock_products_live_create_and_barcodes(
    stock_client_http: httpx2.AsyncClient,
    stock_ui: AppUI,
    ui_page_system: Page,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    """Создание товара извне → строка появляется сама; PATCH баркодов обновляет ячейку."""
    page = ui_page_system
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)
    await stock_e2e_nav(page, "stock_products", page_selector="stock-products-page")

    uoms = (
        await stock_client_http.get("/stock/api/v1/uoms", headers=headers)
    ).json()["items"]
    uom_id = next(u["uom_id"] for u in uoms if u["name"] == "Units")

    product_name = f"RT товар {unique_id[:6]}"
    resp = await stock_client_http.post(
        "/stock/api/v1/products",
        json={
            "name": product_name,
            "sku": f"RT-{unique_id[:6].upper()}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "tracking": "none",
            "is_storable": True,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    product_id = resp.json()["product_id"]

    row = page.locator("stock-products-page table tbody tr", has_text=product_name)
    await expect(row).to_be_visible(timeout=15_000)

    barcode = f"46{unique_id[:11].zfill(11)}"
    resp = await stock_client_http.patch(
        f"/stock/api/v1/catalog-products/{product_id}",
        json={"product_id": product_id, "barcodes": [barcode]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    await expect(row).to_contain_text(barcode, timeout=15_000)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_stock_products_live_attach_from_shop(
    shop_client_http: httpx2.AsyncClient,
    stock_client_http: httpx2.AsyncClient,
    shop_worker: None,
    stock_ui: AppUI,
    ui_page_system: Page,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    """Товар созданный в Shop и подключённый к складу появляется в списке онлайн."""
    _ = shop_worker
    page = ui_page_system
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    storefront = await _create_storefront(
        shop_client_http,
        headers,
        f"at{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=1,
        publish=False,
    )

    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)
    await stock_e2e_nav(page, "stock_products", page_selector="stock-products-page")

    uoms = (
        await stock_client_http.get("/stock/api/v1/uoms", headers=headers)
    ).json()["items"]
    uom_id = next(u["uom_id"] for u in uoms if u["name"] == "Units")

    resp = await stock_client_http.post(
        "/stock/api/v1/products",
        json={
            "product_id": storefront.plain_product_id,
            "name": storefront.plain_product_name,
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "tracking": "none",
            "is_storable": True,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    row = page.locator(
        f"stock-products-page tr[data-product-id='{storefront.plain_product_id}']"
    )
    await expect(row).to_be_visible(timeout=15_000)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_shop_menu_live_master_rename_from_stock(
    shop_client_http: httpx2.AsyncClient,
    stock_client_http: httpx2.AsyncClient,
    shop_worker: None,
    shop_ui: AppUI,
    stock_service: None,
    ui_page_system: Page,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    """Переименование мастер-карточки через Stock → меню Shop обновляется онлайн."""
    _ = shop_worker, stock_service
    page = ui_page_system
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    storefront = await _create_storefront(
        shop_client_http,
        headers,
        f"rt{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=1,
        publish=False,
    )

    await page.set_viewport_size(_DESKTOP)
    await page.goto(
        f"{shop_ui.spa_url()}{storefront.shop_id}/menu", wait_until="load"
    )
    await expect(
        page.locator("shop-menu-page").get_by_text(storefront.plain_product_name).first
    ).to_be_visible(timeout=30_000)

    renamed = f"RT переименовано {unique_id[:4]}"
    resp = await stock_client_http.patch(
        f"/stock/api/v1/catalog-products/{storefront.plain_product_id}",
        json={"product_id": storefront.plain_product_id, "name": renamed},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    await expect(
        page.locator("shop-menu-page").get_by_text(renamed).first
    ).to_be_visible(timeout=15_000)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_stock_products_live_facet_policy_update(
    stock_client_http: httpx2.AsyncClient,
    stock_ui: AppUI,
    ui_page_system: Page,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    """Правка учётной политики (tracking) извне → ячейка фасета обновляется онлайн."""
    page = ui_page_system
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)
    await stock_e2e_nav(page, "stock_products", page_selector="stock-products-page")

    uoms = (
        await stock_client_http.get("/stock/api/v1/uoms", headers=headers)
    ).json()["items"]
    uom_id = next(u["uom_id"] for u in uoms if u["name"] == "Units")

    product_name = f"RT политика {unique_id[:6]}"
    resp = await stock_client_http.post(
        "/stock/api/v1/products",
        json={
            "name": product_name,
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "tracking": "none",
            "is_storable": True,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    product_id = resp.json()["product_id"]

    row = page.locator(f"stock-products-page tr[data-product-id='{product_id}']")
    await expect(row).to_be_visible(timeout=15_000)

    resp = await stock_client_http.patch(
        f"/stock/api/v1/products/{product_id}",
        json={"product_id": product_id, "tracking": "serial"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    await expect(row).to_contain_text("serial", timeout=15_000)

    overlay_name = f"RT складское {unique_id[:4]}"
    resp = await stock_client_http.patch(
        f"/stock/api/v1/products/{product_id}",
        json={"product_id": product_id, "overlay": {"name": overlay_name}},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    await expect(row).to_contain_text(overlay_name, timeout=15_000)
    await expect(row).not_to_contain_text(product_name)

    resp = await stock_client_http.patch(
        f"/stock/api/v1/catalog-products/{product_id}",
        json={"product_id": product_id, "is_archived": True},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    await expect(row).to_have_class(re.compile(r"off"), timeout=15_000)
    await expect(row.locator(".ptag")).to_be_visible()


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_shop_menu_live_listing_price_and_archive(
    shop_client_http: httpx2.AsyncClient,
    stock_client_http: httpx2.AsyncClient,
    shop_worker: None,
    shop_ui: AppUI,
    stock_service: None,
    ui_page_system: Page,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    """Листинг: цена извне → карточка онлайн; архив мастера → метка архива онлайн."""
    _ = shop_worker, stock_service
    page = ui_page_system
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    storefront = await _create_storefront(
        shop_client_http,
        headers,
        f"pa{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=1,
        publish=False,
    )

    await page.set_viewport_size(_DESKTOP)
    await page.goto(
        f"{shop_ui.spa_url()}{storefront.shop_id}/menu", wait_until="load"
    )
    card = page.locator("shop-menu-page .card", has_text=storefront.plain_product_name)
    await expect(card).to_be_visible(timeout=30_000)

    new_price = 77700
    resp = await shop_client_http.patch(
        f"/shop/api/v1/shops/{storefront.shop_id}/products/{storefront.plain_product_id}",
        json={"price_minor": new_price},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    await expect(card.locator(".price")).to_contain_text("777", timeout=15_000)

    overlay_name = f"RT витринное {unique_id[:4]}"
    resp = await shop_client_http.patch(
        f"/shop/api/v1/shops/{storefront.shop_id}/products/{storefront.plain_product_id}",
        json={"name": overlay_name},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    overlay_card = page.locator("shop-menu-page .card", has_text=overlay_name)
    await expect(overlay_card).to_be_visible(timeout=15_000)

    resp = await shop_client_http.patch(
        f"/shop/api/v1/shops/{storefront.shop_id}/products/{storefront.plain_product_id}",
        json={"name": None},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    await expect(card).to_be_visible(timeout=15_000)

    resp = await stock_client_http.patch(
        f"/stock/api/v1/catalog-products/{storefront.plain_product_id}",
        json={"product_id": storefront.plain_product_id, "is_archived": True},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    await expect(card).to_have_class(re.compile(r"archived"), timeout=15_000)

    resp = await stock_client_http.patch(
        f"/stock/api/v1/catalog-products/{storefront.plain_product_id}",
        json={"product_id": storefront.plain_product_id, "is_archived": False},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    await expect(card).not_to_have_class(re.compile(r"archived"), timeout=15_000)

    resp = await shop_client_http.delete(
        f"/shop/api/v1/shops/{storefront.shop_id}/products/{storefront.plain_product_id}",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    await expect(card).not_to_be_visible(timeout=15_000)

    await page.locator("shop-menu-page").get_by_text("All items").first.click()

    created_name = f"RT новинка {unique_id[:4]}"
    resp = await shop_client_http.post(
        f"/shop/api/v1/shops/{storefront.shop_id}/products",
        json={"name": created_name, "price_minor": 100},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    await expect(
        page.locator("shop-menu-page .card", has_text=created_name)
    ).to_be_visible(timeout=15_000)
