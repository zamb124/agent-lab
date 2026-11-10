"""Документационный сценарий Stock: оценка запасов.

«Оценка» — журнал стоимостных слоёв: каждый приход пишет слой с ценой,
списания читают слои в порядке метода оценки (fifo). Сценарий показывает,
как документ превращается в деньги на складе.
"""

from __future__ import annotations

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.stock_e2e_helpers import (
    stock_e2e_nav,
    stock_e2e_op,
    stock_e2e_open,
    stock_e2e_open_transfer,
    stock_e2e_transfer_action,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="stock",
    tag="valuation",
    doc_slug="valuation-report",
    title="Оценка запасов: во сколько обходится склад",
    title_en="Stock valuation: what the warehouse is worth",
    description=(
        "**Для чего:** «Оценка» показывает запасы в деньгах: каждый приход "
        "записывает слой с количеством и ценой, списания забирают слои по "
        "методу оценки товара.\n\n"
        "**Какие проблемы решает:** вы увидите, где искать стоимость "
        "остатков, откуда берётся цена в учёте и почему два прихода по "
        "разной цене — это два разных слоя.\n\n"
        "**Результат:** в журнале оценки видны слои прихода с ценами — "
        "стоимость склада прозрачна."
    ),
    description_en=(
        "**Purpose:** «Valuation» shows stock in money terms: every "
        "receipt writes a layer with quantity and price, and issues "
        "consume layers in the product's valuation order.\n\n"
        "**Problems solved:** you will learn where to find the value of "
        "on-hand stock, where the accounting price comes from and why two "
        "receipts at different prices are two separate layers.\n\n"
        "**Result:** the valuation journal shows inbound layers with "
        "prices — the warehouse's value is transparent."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_valuation_report(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)

    warehouses = await stock_e2e_op(page, "stock/warehouses", "stock/warehouses/list_requested")
    existing_codes = [w["code"] for w in warehouses["items"]]
    warehouse_code = ("0" + min(existing_codes)) if existing_codes else "MAIN"
    warehouse = await stock_e2e_op(
        page,
        "stock/warehouse_create", "stock/warehouse_create/requested",
        {"code": warehouse_code, "name": f"Склад {unique_id[:4]}"},
    )
    warehouse_id = warehouse["warehouse_id"]

    uoms = await stock_e2e_op(page, "stock/uoms_list", "stock/uoms_list/requested")
    uom_id = next(u["uom_id"] for u in uoms["items"] if u["name"] == "Units")
    product = await stock_e2e_op(
        page,
        "stock/product_create", "stock/product_create/requested",
        {
            "name": f"Какао {unique_id[:4]}",
            "sku": f"CCAO-{unique_id[:6]}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "standard_price": "0",
            "tracking": "none",
            "is_storable": True,
        },
    )
    product_id = product["product_id"]

    op_types = await stock_e2e_op(
        page,
        "stock/operation_types_list", "stock/operation_types_list/requested",
        {"warehouse_id": warehouse_id},
    )
    op_in = next(op["operation_type_id"] for op in op_types["items"] if op["code"] == "incoming")

    # Два прихода по разной цене — два слоя в оценке.
    for qty, price in (("10", "200"), ("6", "260")):
        transfer = await stock_e2e_op(
            page,
            "stock/transfer_create", "stock/transfer_create/requested",
            {
                "warehouse_id": warehouse_id,
                "operation_type_id": op_in,
                "moves": [
                    {
                        "product_id": product_id,
                        "product_qty": qty,
                        "uom_id": uom_id,
                        "unit_price": price,
                    }
                ],
            },
        )
        transfer_id = transfer["transfer_id"]
        await stock_e2e_nav(page, 1, page_selector="stock-transfers-page")
        await stock_e2e_open_transfer(page, transfer_id)
        await stock_e2e_transfer_action(page, 0, "stock/transfer_confirm", "assigned")
        await stock_e2e_transfer_action(page, 2, "stock/transfer_validate", "done")
        await stock_e2e_nav(page, 1, page_selector="stock-transfers-page")

    await stock_e2e_nav(page, 4, page_selector="stock-valuation-page")
    rows = page.locator("stock-valuation-page table tbody tr", has_text=product_id)
    await expect(rows.first).to_be_visible(timeout=30_000)
    await expect(rows).to_have_count(2, timeout=15_000)
    await scenario.step(
        "Откройте «Оценку»",
        page,
        screenshot_name="valuation-layers",
        label_en="Open Valuation",
        details=(
            "В меню слева выберите «Оценку». Каждая проведённая приёмка "
            "записала стоимостной слой: у одного товара две строки — 10 шт. "
            "по 200 и 6 шт. по 260, как в документах. Тип «inbound» "
            "показывает, что слой пришёл с поступлением."
        ),
        details_en=(
            "Choose «Valuation» in the left menu. Every validated receipt "
            "wrote a cost layer: the same product has two rows — 10 units "
            "at 200 and 6 at 260, exactly as in the documents. The "
            "«inbound» type shows the layer came from a receipt."
        ),
    )

    await scenario.step(
        "Как это читать",
        page,
        screenshot_name="valuation-read",
        label_en="How to read it",
        details=(
            "**Демонстрация результата.** Стоимость склада — сумма живых "
            "слоёв: 10×200 + 6×260 = 3560 по этому товару. Когда товар "
            "уходит, слои списываются в порядке метода оценки (для fifo — "
            "сначала более ранний приход), поэтому себестоимость отгрузки "
            "всегда посчитана из реальных цен, а не «в среднем».\n\n"
            "**Итог.** Оценка — это стоимостной леджер склада: отсюда "
            "видно, во сколько обошёлся каждый приход и сколько денег "
            "сейчас лежит на полках."
        ),
        details_en=(
            "**Result demonstration.** The warehouse's value is the sum "
            "of live layers: 10×200 + 6×260 = 3560 for this product. When "
            "goods leave, layers are consumed in the valuation order "
            "(fifo takes the earliest receipt first), so the delivery's "
            "cost of goods always comes from real prices.\n\n"
            "**Summary.** Valuation is the warehouse's cost ledger: it "
            "shows what each receipt cost and how much money is on the "
            "shelves right now."
        ),
    )
