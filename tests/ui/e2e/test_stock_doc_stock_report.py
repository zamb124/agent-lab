"""Документационный сценарий Stock: отчёт «Остатки по локациям».

Приход делается операциями (create → confirm → validate) — сценарий
показывает отчёт остатков: группировка по локациям с субсуммами,
раскрытие группы до строки товара и итог по выборке.
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
    tag="stock-report",
    doc_slug="stock-by-location",
    title="Остатки по локациям: где что лежит",
    title_en="Stock by location: what sits where",
    description=(
        "**Для чего:** отчёт «Остатки по локациям» отвечает на вопрос "
        "«где лежит товар и сколько свободно»: строки группируются по "
        "адресам склада с субсуммами по каждой ячейке.\n\n"
        "**Какие проблемы решает:** не нужно открывать каждую ячейку "
        "по отдельности — отчёт показывает весь склад сразу, а "
        "переключатель группировки разворачивает ту же выборку по "
        "товарам.\n\n"
        "**Результат:** на экране — группы «локация → товары» с "
        "количеством, резервом и доступным остатком по каждой ячейке "
        "и итогом внизу."
    ),
    description_en=(
        "**Purpose:** the Stock by location report answers «where "
        "does stock sit and how much is free»: rows are grouped by "
        "warehouse addresses with per-location subtotals.\n\n"
        "**Problems solved:** no need to open each bin separately — "
        "the report shows the whole warehouse at once, and the "
        "grouping switch pivots the same selection by product.\n\n"
        "**Result:** the screen shows location → product groups with "
        "quantity, reserved and available per bin and a grand total."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_stock_by_location_report(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)

    warehouse_code = f"0-{unique_id[:8].upper()}"
    warehouse = await stock_e2e_op(
        page,
        "stock/warehouse_create",
        "stock/warehouse_create/requested",
        {"code": warehouse_code, "name": f"Склад {unique_id[:4]}"},
    )
    warehouse_id = warehouse["warehouse_id"]

    uoms = await stock_e2e_op(page, "stock/uoms_list", "stock/uoms_list/requested")
    uom_id = next(u["uom_id"] for u in uoms["items"] if u["name"] == "Units")
    product_name = f"Виджет {unique_id[:4]}"
    product = await stock_e2e_op(
        page,
        "stock/product_create",
        "stock/product_create/requested",
        {
            "name": product_name,
            "sku": f"WDG-{unique_id[:4]}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "standard_price": "0",
            "tracking": "none",
            "is_storable": True,
            "category": "general",
        },
    )
    product_id = product["product_id"]

    op_types = await stock_e2e_op(
        page,
        "stock/operation_types_list", "stock/operation_types_list/requested",
        {"warehouse_id": warehouse_id},
    )
    op_in = next(
        op["operation_type_id"]
        for op in op_types["items"]
        if op["code"] == "incoming"
    )
    transfer = await stock_e2e_op(
        page,
        "stock/transfer_create",
        "stock/transfer_create/requested",
        {
            "warehouse_id": warehouse_id,
            "operation_type_id": op_in,
            "moves": [
                {
                    "product_id": product_id,
                    "product_qty": "12",
                    "uom_id": uom_id,
                    "unit_price": "450",
                }
            ],
        },
    )
    transfer_id = transfer["transfer_id"]
    await stock_e2e_op(
        page,
        "stock/transfer_confirm",
        "stock/transfer_confirm/requested",
        {"transfer_id": transfer_id},
    )
    await stock_e2e_op(
        page,
        "stock/transfer_validate",
        "stock/transfer_validate/requested",
        {"transfer_id": transfer_id, "create_backorder": False},
    )

    await stock_e2e_nav(
        page, "stock_stock_report", page_selector="stock-stock-report-page"
    )
    group_row = page.locator("stock-stock-report-page tr.group").first
    await expect(group_row).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте «Остатки по локациям»",
        page,
        screenshot_name="stock-report-groups",
        label_en="Open Stock by location",
        details=(
            "В меню слева выберите «Локации → Остатки по локациям». "
            "Строки сгруппированы по адресам склада: заголовок группы "
            "показывает локацию и её субсумму — количество, резерв и "
            "доступно. Клик по группе сворачивает и раскрывает товары "
            "внутри."
        ),
        details_en=(
            "Choose «Locations → Stock by location» in the left menu. "
            "Rows are grouped by warehouse addresses: the group header "
            "shows the location and its subtotal — quantity, reserved "
            "and available. Clicking a group collapses or expands the "
            "products inside."
        ),
    )

    await group_row.click()
    product_row = page.locator(
        "stock-stock-report-page tbody tr", has_text=product_name
    ).first
    await expect(product_row).to_be_visible(timeout=15_000)
    await expect(
        page.locator("stock-stock-report-page tr.total")
    ).to_be_visible(timeout=15_000)

    await scenario.step(
        "Раскройте группу и сверьте итог",
        page,
        screenshot_name="stock-report-total",
        label_en="Expand a group and check the total",
        details=(
            "**Демонстрация результата.** Внутри группы — товары "
            "ячейки с количеством, резервом и доступным остатком; "
            "строка «Итого» внизу суммирует всю выборку. "
            "Переключатель «по локациям / по товарам» над таблицей "
            "меняет разрез: та же выборка группируется по товарам — "
            "удобно ответить «в каких ячейках лежит эта позиция».\n\n"
            "**Итог.** Один отчёт отвечает на оба вопроса — «что "
            "лежит в ячейке» и «где лежит товар»."
        ),
        details_en=(
            "**Result demonstration.** Inside the group are the bin's "
            "products with quantity, reserved and available; the "
            "grand total row at the bottom sums the whole selection. "
            "The «by location / by product» switch above the table "
            "pivots the same selection by product — handy to answer "
            "«which bins hold this item».\n\n"
            "**Summary.** One report answers both questions — «what "
            "sits in this bin» and «where does this product sit»."
        ),
    )
