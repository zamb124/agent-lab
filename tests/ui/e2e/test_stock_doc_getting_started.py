"""Документационный сценарий Stock: обзорный тур по разделу «Склад».

Первое знакомство пользователя со складом: пульс на главной, каталог товаров,
дерево локаций и журнал документов. Подготовка минимального набора данных
(склад и один товар) идёт тем же op-каналом, что и SPA.
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
    tag="getting-started",
    doc_slug="stock-overview",
    title="Знакомимся со складом: обзор, товары, ячейки, документы",
    title_en="Meet the warehouse: overview, products, bins, documents",
    description=(
        "**Для чего:** первый визит в раздел «Склад» — за пять минут понять, "
        "где что живёт и как устроены основные экраны.\n\n"
        "**Какие проблемы решает:** вы узнаете, где смотреть остатки и "
        "стоимость запасов, где каталог товаров, где карта ячеек склада и "
        "где журнал всех складских документов.\n\n"
        "**Результат:** вы ориентируетесь в меню склада и знаете, какой "
        "экран открыть для нужной задачи."
    ),
    description_en=(
        "**Purpose:** your first visit to the Warehouse section — learn in "
        "five minutes where everything lives.\n\n"
        "**Problems solved:** you will know where to see stock and its "
        "value, where the product catalog is, where the bin map lives, and "
        "where the journal of all warehouse documents is.\n\n"
        "**Result:** you can navigate the warehouse menu and know which "
        "screen to open for each task."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_stock_overview(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)

    # --- Минимальный набор данных тем же op-каналом, что и SPA ---
    warehouse_code = f"0-{unique_id[:8].upper()}"
    _ = await stock_e2e_op(
        page,
        "stock/warehouse_create", "stock/warehouse_create/requested",
        {"code": warehouse_code, "name": f"Основной склад {unique_id[:4]}"},
    )
    uoms = await stock_e2e_op(page, "stock/uoms_list", "stock/uoms_list/requested")
    uom_id = next(u["uom_id"] for u in uoms["items"] if u["name"] == "Units")
    await stock_e2e_op(
        page,
        "stock/product_create", "stock/product_create/requested",
        {
            "name": f"Кофе зерновой {unique_id[:4]}",
            "sku": f"BEAN-{unique_id[:6]}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "standard_price": "0",
            "tracking": "none",
            "is_storable": True,
        },
    )

    # --- Пользовательский маршрут по UI ---
    await expect(page.locator("stock-home-page")).to_be_visible(timeout=15_000)
    await scenario.step(
        "Откройте раздел «Склад»",
        page,
        screenshot_name="stock-home",
        label_en="Open the Warehouse section",
        details=(
            "В меню приложений выберите «Склад». Открывается главная — "
            "«пульс» склада: сколько товара лежит, сколько зарезервировано, "
            "какая сумма числится в запасах и что происходит с документами "
            "прямо сейчас."
        ),
        details_en=(
            "Choose «Warehouse» in the app menu. The home page opens — the "
            "warehouse «pulse»: how much stock is on hand, how much is "
            "reserved, the value held in stock, and what is happening with "
            "documents right now."
        ),
    )

    await stock_e2e_nav(page, 'stock_products', page_selector="stock-products-page")
    await scenario.step(
        "Посмотрите каталог товаров",
        page,
        screenshot_name="stock-products",
        label_en="Browse the product catalog",
        details=(
            "Пункт «Товары» — справочник всего, что хранится на складе: "
            "название, артикул, единица измерения и метод оценки. Здесь "
            "проверяют, заведён ли товар, прежде чем принимать поставку."
        ),
        details_en=(
            "The «Products» item is the catalog of everything stored: name, "
            "SKU, unit of measure and valuation method. Check here whether "
            "a product exists before receiving a delivery."
        ),
    )

    await stock_e2e_nav(page, 'stock_locations', page_selector="stock-locations-page")
    await scenario.step(
        "Откройте карту ячеек склада",
        page,
        screenshot_name="stock-locations",
        label_en="Open the warehouse bin map",
        details=(
            "Пункт «Локации» показывает структуру склада: зоны приёмки, "
            "отгрузки и ячейки хранения. По типу локации видно её роль — "
            "например, «приёмка» куда ставят поставку, или «полка» где "
            "товар лежит постоянно."
        ),
        details_en=(
            "The «Locations» item shows the warehouse structure: receiving "
            "and shipping zones and storage bins. The location type shows "
            "its role — e.g. «receiving» where deliveries go, or a «bin» "
            "where goods stay."
        ),
    )

    await stock_e2e_nav(page, 'stock_transfers', page_selector="stock-transfers-page")
    await scenario.step(
        "Загляните в журнал документов",
        page,
        screenshot_name="stock-transfers",
        label_en="Look into the documents journal",
        details=(
            "Пункт «Переводы» — журнал всех складских документов: "
            "поступления, отгрузки и перемещения. По статусу видно, на "
            "каком этапе документ: черновик, зарезервирован или проведён."
        ),
        details_en=(
            "The «Transfers» item is the journal of all warehouse "
            "documents: receipts, deliveries and internal moves. The state "
            "shows the document stage: draft, reserved or done."
        ),
    )

    await stock_e2e_nav(page, 'stock_valuation', page_selector="stock-valuation-page")
    await scenario.step(
        "Откройте денежную оценку запасов",
        page,
        screenshot_name="stock-valuation",
        label_en="Open stock valuation",
        details=(
            "**Демонстрация результата.** Пункт «Оценка» — журнал стоимости "
            "запасов: каждый приход и расход записывает слой с количеством, "
            "ценой и итоговой стоимостью.\n\n"
            "**Итог.** Вы знаете карту раздела: главная — пульс и остатки, "
            "«Товары» — справочник, «Локации» — ячейки, «Переводы» — "
            "документы, «Оценка» — деньги в запасах."
        ),
        details_en=(
            "**Result demonstration.** The «Valuation» item is the stock "
            "value journal: every receipt and issue records a layer with "
            "quantity, price and total value.\n\n"
            "**Summary.** You know the section map: home — pulse and stock, "
            "«Products» — catalog, «Locations» — bins, «Transfers» — "
            "documents, «Valuation» — money in stock."
        ),
    )
