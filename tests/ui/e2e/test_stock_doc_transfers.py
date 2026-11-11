"""Документационные сценарии Stock: журнал переводов и перемещение между локациями.

Данные готовит тот же op-канал, что и SPA; пользовательский путь — через UI:
журнал документов, карточка перевода, действия по статусам.
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


async def _prepare_stock_ctx(page: Page, unique_id: str) -> dict[str, str]:
    """Склад + товар + Units: минимальный контекст документов."""
    warehouses = await stock_e2e_op(page, "stock/warehouses", "stock/warehouses/list_requested")
    existing_codes = [w["code"] for w in warehouses["items"]]
    warehouse_code = ("0" + min(existing_codes)) if existing_codes else "MAIN"
    warehouse = await stock_e2e_op(
        page,
        "stock/warehouse_create", "stock/warehouse_create/requested",
        {"code": warehouse_code, "name": f"Склад {unique_id[:4]}"},
    )
    uoms = await stock_e2e_op(page, "stock/uoms_list", "stock/uoms_list/requested")
    uom_id = next(u["uom_id"] for u in uoms["items"] if u["name"] == "Units")
    product = await stock_e2e_op(
        page,
        "stock/product_create", "stock/product_create/requested",
        {
            "name": f"Чай листовой {unique_id[:4]}",
            "sku": f"TEA-{unique_id[:6]}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "standard_price": "0",
            "tracking": "none",
            "is_storable": True,
        },
    )
    return {
        "warehouse_id": warehouse["warehouse_id"],
        "uom_id": uom_id,
        "product_id": product["product_id"],
    }


async def _create_incoming(
    page: Page,
    ctx: dict[str, str],
    qty: str,
    dest_location_id: str | None = None,
) -> str:
    """Приход `incoming` в статусе draft на склад контекста."""
    op_types = await stock_e2e_op(
        page,
        "stock/operation_types_list", "stock/operation_types_list/requested",
        {"warehouse_id": ctx["warehouse_id"]},
    )
    op_in = next(op["operation_type_id"] for op in op_types["items"] if op["code"] == "incoming")
    move: dict[str, object] = {
        "product_id": ctx["product_id"],
        "product_qty": qty,
        "uom_id": ctx["uom_id"],
        "unit_price": "120",
    }
    if dest_location_id:
        move["location_dest_id"] = dest_location_id
    transfer = await stock_e2e_op(
        page,
        "stock/transfer_create", "stock/transfer_create/requested",
        {
            "warehouse_id": ctx["warehouse_id"],
            "operation_type_id": op_in,
            "moves": [move],
        },
    )
    return transfer["transfer_id"]


@pytest.mark.scenario(
    service="stock",
    tag="transfers",
    doc_slug="transfers-journal",
    title="Журнал переводов: статусы документов",
    title_en="Transfers journal: document states",
    description=(
        "**Для чего:** «Переводы» — журнал всех складских документов: "
        "поступления, отгрузки и внутренние перемещения.\n\n"
        "**Какие проблемы решает:** вы увидите, как читать статусы документа "
        "«черновик → зарезервирован → проведён», где найти нужный документ "
        "и что показывает его карточка.\n\n"
        "**Результат:** вы ориентируетесь в журнале и открываете карточку "
        "любого складского документа."
    ),
    description_en=(
        "**Purpose:** «Transfers» is the journal of all warehouse documents: "
        "receipts, deliveries and internal moves.\n\n"
        "**Problems solved:** you will learn to read document states "
        "«draft → reserved → done», find the document you need and open "
        "its card.\n\n"
        "**Result:** you can navigate the journal and open any warehouse "
        "document's card."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_transfers_journal(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)
    ctx = await _prepare_stock_ctx(page, unique_id)
    draft_id = await _create_incoming(page, ctx, "8")

    await stock_e2e_nav(page, 1, page_selector="stock-transfers-page")
    draft_row = page.locator(f"stock-transfers-page tr[data-id='{draft_id}']")
    await expect(draft_row).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте «Переводы»",
        page,
        screenshot_name="journal-states",
        label_en="Open Transfers",
        details=(
            "В меню слева выберите «Переводы» — это журнал всех складских "
            "документов. В строке видны тип операции, статус и время: "
            "новый документ начинается со статуса «черновик» — он ещё не "
            "влияет на остатки."
        ),
        details_en=(
            "Choose «Transfers» in the left menu — the journal of all "
            "warehouse documents. Each row shows the operation type, state "
            "and time: a new document starts as «draft» — it does not "
            "affect stock yet."
        ),
    )

    await stock_e2e_open_transfer(page, draft_id)
    await scenario.step(
        "Откройте карточку документа",
        page,
        screenshot_name="journal-open-card",
        label_en="Open the document card",
        details=(
            "Клик по строке открывает карточку: шапка со статусом и кнопки "
            "действий, ниже — строки документа с товаром и количеством. "
            "Кнопки сверху ведут документ по жизненному циклу: «Подтвердить» "
            "резервирует задание, «Провести» списывает или зачисляет "
            "остатки.\n\n"
            "**Итог.** Журнал — это контрольная лента склада: любое "
            "движение товара вы найдёте здесь и проверите по карточке."
        ),
        details_en=(
            "Click the row to open the card: a header with the state and "
            "action buttons, and document lines with product and quantity "
            "below. The buttons move the document through its lifecycle: "
            "«Confirm» reserves the task, «Validate» posts the stock.\n\n"
            "**Summary.** The journal is the warehouse's control feed: "
            "every goods movement is listed here and verifiable in its card."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="transfers",
    doc_slug="transfer-between-locations",
    title="Перемещение товара между ячейками склада",
    title_en="Moving stock between warehouse bins",
    description=(
        "**Для чего:** внутреннее перемещение перекладывает остаток товара "
        "из одной ячейки в другую — например, из зоны приёмки на место "
        "хранения.\n\n"
        "**Какие проблемы решает:** вы узнаете, как оформить перемещение, "
        "провести его по статусам и убедиться, что товар сменил ячейку.\n\n"
        "**Результат:** перемещение проведено — остаток ушёл из исходной "
        "ячейки и появился в целевой."
    ),
    description_en=(
        "**Purpose:** an internal transfer moves a product's stock from "
        "one bin to another — e.g. from the receiving zone to its storage "
        "slot.\n\n"
        "**Problems solved:** you will learn how to register a move, push "
        "it through the states and verify the goods changed bins.\n\n"
        "**Result:** the move is validated — the stock left the source "
        "bin and appeared in the destination."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_transfer_between_locations(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)
    ctx = await _prepare_stock_ctx(page, unique_id)
    warehouse_id = ctx["warehouse_id"]

    zone = await stock_e2e_op(
        page,
        "stock/location_create", "stock/location_create/requested",
        {"warehouse_id": warehouse_id, "name": f"Зона {unique_id[:4]}", "usage": "view"},
    )
    bin_a = await stock_e2e_op(
        page,
        "stock/location_create", "stock/location_create/requested",
        {
            "warehouse_id": warehouse_id,
            "parent_id": zone["location_id"],
            "name": f"A-{unique_id[:2].upper()}",
            "usage": "bin",
            "pick_sequence": 10,
        },
    )
    bin_b = await stock_e2e_op(
        page,
        "stock/location_create", "stock/location_create/requested",
        {
            "warehouse_id": warehouse_id,
            "parent_id": zone["location_id"],
            "name": f"B-{unique_id[:2].upper()}",
            "usage": "bin",
            "pick_sequence": 20,
        },
    )

    # Остаток в зоне приёмки: приход проведён до done. Финальную ячейку выбирает
    # putaway — читаем, куда товар реально лёг.
    receipt_id = await _create_incoming(page, ctx, "10", dest_location_id=zone["location_id"])
    await stock_e2e_nav(page, 1, page_selector="stock-transfers-page")
    await stock_e2e_open_transfer(page, receipt_id)
    await stock_e2e_transfer_action(page, 0, "stock/transfer_confirm", "assigned")
    await stock_e2e_transfer_action(page, 2, "stock/transfer_validate", "done")
    receipt = await stock_e2e_op(
        page,
        "stock/transfer_item", "stock/transfer_item/requested",
        {"transfer_id": receipt_id},
    )
    receipt_dest = receipt["moves"][0]["location_dest_id"]
    src_bin_id, dst_bin_id = (
        (bin_a["location_id"], bin_b["location_id"])
        if receipt_dest == bin_a["location_id"]
        else (bin_b["location_id"], bin_a["location_id"])
    )

    # Внутреннее перемещение из ячейки, где лежит остаток, во вторую ячейку.
    op_types = await stock_e2e_op(
        page,
        "stock/operation_types_list", "stock/operation_types_list/requested",
        {"warehouse_id": warehouse_id},
    )
    op_internal = next(
        op["operation_type_id"] for op in op_types["items"] if op["code"] == "internal"
    )
    move = await stock_e2e_op(
        page,
        "stock/transfer_create", "stock/transfer_create/requested",
        {
            "warehouse_id": warehouse_id,
            "operation_type_id": op_internal,
            "moves": [
                {
                    "product_id": ctx["product_id"],
                    "product_qty": "4",
                    "uom_id": ctx["uom_id"],
                    "location_id": src_bin_id,
                    "location_dest_id": dst_bin_id,
                }
            ],
        },
    )
    move_id = move["transfer_id"]

    await stock_e2e_nav(page, 1, page_selector="stock-transfers-page")
    move_row = page.locator(f"stock-transfers-page tr[data-id='{move_id}']")
    await expect(move_row).to_be_visible(timeout=30_000)
    await scenario.step(
        "Найдите перемещение в журнале",
        page,
        screenshot_name="internal-transfer-row",
        label_en="Find the move in the journal",
        details=(
            "Внутреннее перемещение создаёт документ с типом «внутренний». "
            "В журнале «Переводы» он виден рядом с поступлением: у него те "
            "же статусы и та же карточка — из строки «откуда» в строку "
            "«куда»."
        ),
        details_en=(
            "An internal move creates an «internal» document. In the "
            "«Transfers» journal it sits next to the receipt: same states "
            "and the same card — a line «from» and a line «to»."
        ),
    )

    await stock_e2e_open_transfer(page, move_id)
    await stock_e2e_transfer_action(page, 0, "stock/transfer_confirm", "assigned")
    await scenario.step(
        "Подтвердите перемещение",
        page,
        screenshot_name="internal-transfer-reserved",
        label_en="Confirm the move",
        details=(
            "Нажмите «Подтвердить» — система резервирует 4 шт. в исходной "
            "ячейке: они ещё на месте, но уже недоступны для других "
            "операций. Статус — «зарезервирован»."
        ),
        details_en=(
            "Click «Confirm» — the system reserves 4 units in the source "
            "bin: they are still there but unavailable for other "
            "operations. The state becomes «reserved»."
        ),
    )

    await stock_e2e_transfer_action(page, 2, "stock/transfer_validate", "done")
    await scenario.step(
        "Проведите перемещение",
        page,
        screenshot_name="internal-transfer-done",
        label_en="Validate the move",
        details=(
            "Когда товар физически переложен, нажмите «Провести». Статус "
            "«проведён» — остаток снят с ячейки A и зачислен в ячейку B.\n\n"
            "**Итог.** Любая перестановка на складе оформляется документом: "
            "журнал показывает, что и откуда куда переехало, а остатки "
            "остаются точными."
        ),
        details_en=(
            "Once the goods are physically moved, click «Validate». The "
            "«done» state means the stock left bin A and was posted to "
            "bin B.\n\n"
            "**Summary.** Every rearrangement in the warehouse is a "
            "document: the journal shows what moved where, and the stock "
            "figures stay exact."
        ),
    )
