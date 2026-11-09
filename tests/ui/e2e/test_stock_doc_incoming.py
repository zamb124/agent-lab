"""Документационный сценарий Stock: провести поступление товара на склад.

UI склада — первый срез: данные создают операции (tools/интеграции), а в
интерфейсе пользователь ведёт документ по статусам. Подготовка склада, товара
и черновика поступления идёт тем же op-каналом, что и SPA; дальше — только UI.
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
    tag="getting-started",
    doc_slug="stock-incoming",
    title="Проводим поступление товара на склад",
    title_en="Process a goods receipt into the warehouse",
    description=(
        "**Для чего:** эта инструкция поможет принять поставку: открыть "
        "документ поступления и провести его до появления остатка на складе.\n\n"
        "**Какие проблемы решает:** вы узнаете, где живут складские документы, "
        "что означают статусы «черновик → подтверждён → зарезервирован → "
        "проведён» и как убедиться, что товар числится на складе.\n\n"
        "**Результат:** поступление проведено, а пульс склада показывает "
        "полученное количество."
    ),
    description_en=(
        "**Purpose:** this guide helps you receive a delivery: open the "
        "receipt document and process it until the stock appears on hand.\n\n"
        "**Problems solved:** you will learn where warehouse documents live, "
        "what the states «draft → confirmed → reserved → done» mean, and how "
        "to verify the goods are counted in stock.\n\n"
        "**Result:** the receipt is validated and the warehouse pulse shows "
        "the received quantity."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_stock_incoming_receipt(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)

    # --- Подготовка данных тем же op-каналом, что использует SPA ---
    warehouses = await stock_e2e_op(page, "stock/warehouses", "stock/warehouses/list_requested")
    existing_codes = [w["code"] for w in warehouses["items"]]
    # Код строго меньше минимального существующего: пульс главной всегда
    # показывает первый по коду склад — наш гарантированно первый.
    warehouse_code = ("0" + min(existing_codes)) if existing_codes else "MAIN"
    warehouse = await stock_e2e_op(
        page,
        "stock/warehouse_create", "stock/warehouse_create/requested",
        {"code": warehouse_code, "name": f"Основной склад {unique_id[:4]}"},
    )
    warehouse_id = warehouse["warehouse_id"]

    uoms = await stock_e2e_op(page, "stock/uoms_list", "stock/uoms_list/requested")
    uom_id = next(u["uom_id"] for u in uoms["items"] if u["name"] == "Units")

    product_name = f"Кофе зерновой {unique_id[:4]}"
    product = await stock_e2e_op(
        page,
        "stock/product_create", "stock/product_create/requested",
        {
            "name": product_name,
            "sku": f"BEAN-{unique_id[:6]}",
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

    transfer = await stock_e2e_op(
        page,
        "stock/transfer_create", "stock/transfer_create/requested",
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
    assert transfer["state"] == "draft"

    # --- Пользовательский маршрут по UI ---
    await stock_e2e_nav(page, 1, page_selector="stock-transfers-page")
    await scenario.step(
        "Откройте раздел «Переводы»",
        page,
        screenshot_name="transfers-journal",
        label_en="Open the Transfers section",
        details=(
            "В меню слева выберите «Переводы». Здесь журнал всех складских "
            "документов: поступления от поставщиков, отгрузки покупателям и "
            "внутренние перемещения. Новое поступление видно в статусе "
            "«черновик»."
        ),
        details_en=(
            "Choose «Transfers» in the left menu. This is the journal of all "
            "warehouse documents: supplier receipts, customer deliveries and "
            "internal moves. The new receipt is shown as «draft»."
        ),
    )

    await stock_e2e_open_transfer(page, transfer_id)
    await scenario.step(
        "Откройте документ поступления",
        page,
        screenshot_name="transfer-draft",
        label_en="Open the receipt document",
        details=(
            "Кликните по строке документа — откроется карточка. Проверьте "
            "строки: товар, количество и зона приёмки. Сверху — кнопки "
            "действий, которые ведут документ по статусам."
        ),
        details_en=(
            "Click the document row — the card opens. Check the lines: "
            "product, quantity and the receiving zone. The action buttons on "
            "top move the document through its states."
        ),
    )

    await stock_e2e_transfer_action(page, 0, "stock/transfer_confirm", "assigned")
    await scenario.step(
        "Подтвердите документ",
        page,
        screenshot_name="transfer-confirmed",
        label_en="Confirm the document",
        details=(
            "Нажмите «Подтвердить»: склад согласует документ, а система сразу "
            "резервирует место под поставку. Статус становится «зарезервирован» — "
            "задания на приёмку готовы, осталось принять товар фактически."
        ),
        details_en=(
            "Click «Confirm»: the warehouse agrees the document and the system "
            "immediately reserves space for the delivery. The state becomes "
            "«reserved» — put-away tasks are ready, only the physical receipt "
            "is left."
        ),
    )

    await stock_e2e_transfer_action(page, 2, "stock/transfer_validate", "done")
    await scenario.step(
        "Проведите поступление",
        page,
        screenshot_name="transfer-done",
        label_en="Validate the receipt",
        details=(
            "Когда товар принят фактически, нажмите «Провести». Статус станет "
            "«проведён»: количество зачислено на склад, а стоимость записана в "
            "оценку запасов по цене из документа."
        ),
        details_en=(
            "Once the goods are physically received, click «Validate». The "
            "state becomes «done»: the quantity is posted to the warehouse "
            "and its cost is recorded in stock valuation."
        ),
    )

    await stock_e2e_nav(page, 0, page_selector="stock-home-page")
    quant_row = page.locator(
        "stock-home-page table tbody tr", has_text=product_id
    ).first
    await expect(quant_row).to_be_visible(timeout=15_000)
    await expect(quant_row).to_contain_text("12")
    await scenario.step(
        "Проверьте остаток на пульсе склада",
        page,
        screenshot_name="pulse-quant-visible",
        label_en="Check the on-hand quantity on the warehouse pulse",
        details=(
            "**Демонстрация результата.** Вернитесь на главную «Склада»: в "
            "таблице остатков появилась строка товара с принятым количеством. "
            "Ниже пульс показывает проведённый документ.\n\n"
            "**Итог.** Теперь вы умеете находить поступление в журнале, "
            "проводить его по статусам и проверять остаток на пульсе склада."
        ),
        details_en=(
            "**Result demonstration.** Return to the Stock home page: the "
            "on-hand table now shows the product row with the received "
            "quantity. Below, the pulse lists the validated document.\n\n"
            "**Summary.** Now you can find a receipt in the journal, process "
            "it through the states, and verify stock on the warehouse pulse."
        ),
    )
