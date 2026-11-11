"""Документационный сценарий Stock: номенклатура склада.

Товары заводят операции (tools/интеграции) — интерфейс «Номенклатура»
показывает справочник: артикул, название, метод оценки, цену и учёт
по партиям/сериям.
"""

from __future__ import annotations

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.stock_e2e_helpers import (
    stock_e2e_nav,
    stock_e2e_op,
    stock_e2e_open,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="stock",
    tag="products",
    doc_slug="products-catalog",
    title="Номенклатура: товары склада",
    title_en="Catalog: warehouse products",
    description=(
        "**Для чего:** «Номенклатура» — справочник товаров склада: "
        "артикул, название, метод оценки стоимости и правило учёта "
        "партий.\n\n"
        "**Какие проблемы решает:** вы поймёте, что видно по каждому "
        "товару — как склад считает стоимость остатка (FIFO или "
        "стандартная цена) и ведёт ли товар серии или сроки годности.\n\n"
        "**Результат:** товар виден в номенклатуре с артикулом, ценой "
        "и методом оценки."
    ),
    description_en=(
        "**Purpose:** the Catalog is the warehouse product book: "
        "SKU, name, valuation method and the lot-tracking rule.\n\n"
        "**Problems solved:** you will understand what each product "
        "shows — how the warehouse costs the on-hand value (FIFO or "
        "standard price) and whether the product tracks lots or "
        "expiry dates.\n\n"
        "**Result:** the product is listed in the catalog with its "
        "SKU, price and valuation method."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_products_catalog(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)

    uoms = await stock_e2e_op(
        page, "stock/uoms_list", "stock/uoms_list/requested"
    )
    uom_id = next(u["uom_id"] for u in uoms["items"] if u["name"] == "Units")

    product_name = f"Кофе зерновой {unique_id[:4]}"
    product = await stock_e2e_op(
        page,
        "stock/product_create",
        "stock/product_create/requested",
        {
            "name": product_name,
            "sku": f"BEAN-{unique_id[:6].upper()}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "standard_price": "450",
            "tracking": "none",
            "is_storable": True,
        },
    )
    assert product["product_id"]

    await stock_e2e_nav(page, 'stock_products', page_selector="stock-products-page")
    row = page.locator(
        "stock-products-page table tbody tr", has_text=product_name
    )
    await expect(row).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте «Номенклатуру»",
        page,
        screenshot_name="products-list",
        label_en="Open the Catalog",
        details=(
            "В меню слева выберите «Номенклатура» — это список всех "
            "товаров склада. Новый товар виден сразу: артикул, "
            "название, метод оценки, стандартная цена и учёт партий."
        ),
        details_en=(
            "Choose «Catalog» in the left menu — it lists every "
            "warehouse product. The new product appears at once: "
            "SKU, name, valuation method, standard price and lot "
            "tracking."
        ),
    )

    await scenario.step(
        "Что означают колонки",
        page,
        screenshot_name="products-columns",
        label_en="What the columns mean",
        details=(
            "**Демонстрация результата.** «Метод оценки» решает, как "
            "считать стоимость остатка: FIFO списывает партии от "
            "старой к новой, стандартная цена фиксирует стоимость "
            "карточкой. «Учёт» показывает, ведётся ли товар по "
            "партиям или сериям — для сроков годности и гарантий.\n\n"
            "**Итог.** Теперь вы читаете карточку товара в "
            "номенклатуре и понимаете, как склад оценивает его "
            "остаток."
        ),
        details_en=(
            "**Result demonstration.** Valuation method decides how "
            "on-hand cost is computed: FIFO consumes batches oldest "
            "to newest, standard price fixes the cost on the card. "
            "Tracking shows whether the product is kept by lots or "
            "serials — for expiry dates and warranties.\n\n"
            "**Summary.** You can now read a product row in the "
            "catalog and understand how its stock is valued."
        ),
    )
