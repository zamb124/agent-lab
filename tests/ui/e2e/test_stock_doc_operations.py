"""Документационные сценарии Stock: движения, тара, инвентаризация, настройки.

Данные готовит тот же op-канал, что и SPA; пользовательский путь — через UI:
журнал движений, карточка тары, пересчёт ячейки и справочники склада.
"""

from __future__ import annotations

from typing import Any

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.stock_e2e_helpers import (
    stock_e2e_nav,
    stock_e2e_op,
    stock_e2e_open,
    stock_e2e_pick_warehouse,
)
from tests.ui.harness import AppUI, ui_set_platform_field
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


async def _ctx(page: Page, unique_id: str) -> dict[str, str]:
    """Склад + товар + Units + зона и ячейка: контекст операционных документов."""
    warehouse = await stock_e2e_op(
        page,
        "stock/warehouse_create", "stock/warehouse_create/requested",
        {"code": f"0-{unique_id[:8].upper()}", "name": f"Склад {unique_id[:4]}"},
    )
    uoms = await stock_e2e_op(page, "stock/uoms_list", "stock/uoms_list/requested")
    uom_id = next(u["uom_id"] for u in uoms["items"] if u["name"] == "Units")
    product = await stock_e2e_op(
        page,
        "stock/product_create", "stock/product_create/requested",
        {
            "name": f"Кофе зерновой {unique_id[:4]}",
            "sku": f"COF-{unique_id[:6]}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "standard_price": "0",
            "tracking": "none",
            "is_storable": True,
        },
    )
    zone = await stock_e2e_op(
        page,
        "stock/location_create", "stock/location_create/requested",
        {
            "warehouse_id": warehouse["warehouse_id"],
            "name": f"Зона {unique_id[:4]}",
            "usage": "view",
        },
    )
    bin_loc = await stock_e2e_op(
        page,
        "stock/location_create", "stock/location_create/requested",
        {
            "warehouse_id": warehouse["warehouse_id"],
            "parent_id": zone["location_id"],
            "name": f"Ячейка {unique_id[:4]}",
            "usage": "bin",
            "pick_sequence": 10,
        },
    )
    return {
        "warehouse_id": warehouse["warehouse_id"],
        "uom_id": uom_id,
        "product_id": product["product_id"],
        "zone_id": zone["location_id"],
        "bin_id": bin_loc["location_id"],
    }


async def _receive(
    page: Page,
    ctx: dict[str, str],
    qty: str,
    dest_location_id: str | None = None,
) -> str:
    """Приход → подтверждение → проведение: остаток на месте назначения."""
    op_types = await stock_e2e_op(
        page,
        "stock/operation_types_list", "stock/operation_types_list/requested",
        {"warehouse_id": ctx["warehouse_id"]},
    )
    op_in = next(
        op["operation_type_id"] for op in op_types["items"] if op["code"] == "incoming"
    )
    move: dict[str, object] = {
        "product_id": ctx["product_id"],
        "product_qty": qty,
        "uom_id": ctx["uom_id"],
        "unit_price": "150",
    }
    if dest_location_id is not None:
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
    transfer_id = transfer["transfer_id"]
    await stock_e2e_op(
        page,
        "stock/transfer_confirm", "stock/transfer_confirm/requested",
        {"transfer_id": transfer_id},
    )
    await stock_e2e_op(
        page,
        "stock/transfer_validate", "stock/transfer_validate/requested",
        {"transfer_id": transfer_id},
    )
    return transfer_id


@pytest.mark.scenario(
    service="stock",
    tag="locations",
    doc_slug="moves-journal",
    title="Журнал движений: каждая строка товара под контролем",
    title_en="Moves journal: every stock line under control",
    description=(
        "**Для чего:** «Движения» — лента всех строк товара: куда приехало, "
        "откуда уехало и в каком статусе.\n\n"
        "**Какие проблемы решает:** журнал документов показывает документ "
        "целиком, а здесь видна каждая строка отдельно — удобно ответить "
        "«где сейчас этот товар».\n\n"
        "**Результат:** вы фильтруете движения по складу и статусу и "
        "переходите к документу одной строкой."
    ),
    description_en=(
        "**Purpose:** «Moves» is the feed of every stock line: where it "
        "arrived, where it left from and in which state.\n\n"
        "**Problems solved:** the documents journal shows a whole document, "
        "here each line stands alone — the quickest answer to «where is "
        "this product now».\n\n"
        "**Result:** you filter moves by warehouse and state and jump to "
        "the document in one click."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_moves_journal(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)
    ctx = await _ctx(page, unique_id)
    _ = await _receive(page, ctx, "8", dest_location_id=ctx["bin_id"])

    await stock_e2e_nav(page, 'stock_moves', page_selector="stock-moves-page")
    row = page.locator("stock-moves-page tbody tr").filter(
        has_text=f"Кофе зерновой {unique_id[:4]}"
    )
    await expect(row.first).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте «Движения»",
        page,
        screenshot_name="moves-rows",
        label_en="Open Moves",
        details=(
            "В разделе «Локации» выберите «Движения» — каждая строка это "
            "одно перемещение товара: дата, откуда и куда, количество и "
            "статус. Сверху — фильтры по складу, ячейке и товару."
        ),
        details_en=(
            "In the «Locations» section choose «Moves» — each row is one "
            "goods movement: date, from and to, quantity and state. "
            "Warehouse, bin and product filters sit on top."
        ),
    )

    segments = page.locator(
        "stock-moves-page platform-segmented-control button.segment"
    )
    await segments.nth(4).click()
    await expect(row.first).to_be_visible(timeout=30_000)
    await scenario.step(
        "Отфильтруйте проведённые",
        page,
        screenshot_name="moves-filtered-done",
        label_en="Filter validated moves",
        details=(
            "Переключатель статусов оставляет только нужные строки — "
            "например «проведённые». Бейдж в колонке «Статус» показывает "
            "этап каждой строки."
        ),
        details_en=(
            "The state switcher keeps only the rows you need — e.g. "
            "«done». The badge in the State column shows each line's stage."
        ),
    )

    await row.first.locator("a.link").click()
    await expect(
        page.locator("stock-transfer-page page-header")
    ).to_be_visible(timeout=15_000)
    await scenario.step(
        "Перейдите к документу",
        page,
        screenshot_name="moves-open-transfer",
        label_en="Jump to the document",
        details=(
            "Номер в последней колонке открывает карточку документа, "
            "которому принадлежит строка. Так вы быстро проверяете, какой "
            "приход или перемещение двигает остаток.\n\n"
            "**Итог.** Движения отвечают на вопрос «что происходило с "
            "товаром» по каждой строке, а не только по документу целиком."
        ),
        details_en=(
            "The number in the last column opens the card of the document "
            "the line belongs to — a quick way to see which receipt or "
            "transfer moved the stock.\n\n"
            "**Summary.** Moves answer «what happened to the goods» line "
            "by line, not only per document."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="locations",
    doc_slug="packages-containers",
    title="Тара и упаковки: что внутри и куда её везти",
    title_en="Containers and packages: contents and moves",
    description=(
        "**Для чего:** палеты, короба и тележки — отдельные «ячейки» склада. "
        "Экран «Упаковки» показывает, что лежит в каждой таре и где она "
        "стоит.\n\n"
        "**Какие проблемы решает:** не нужно искать товар по ячейкам — "
        "выбираете палету и видите её содержимое, а кнопка «Переместить» "
        "перевозит её целиком вместе со всем внутри.\n\n"
        "**Результат:** вы открыли палету, проверили содержимое и "
        "переместили её в другую зону."
    ),
    description_en=(
        "**Purpose:** pallets, boxes and carts are warehouse «bins» of "
        "their own. The Packages screen shows what is inside each "
        "container and where it stands.\n\n"
        "**Problems solved:** no need to hunt goods across bins — pick a "
        "pallet and see its contents, and «Move» relocates it whole, "
        "contents included.\n\n"
        "**Result:** you opened a pallet, checked its contents and moved "
        "it to another zone."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_packages_containers(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)
    ctx = await _ctx(page, unique_id)

    pallet_type = await stock_e2e_op(
        page,
        "stock/container_type_create", "stock/container_type_create/requested",
        {
            "warehouse_id": ctx["warehouse_id"],
            "name": f"Европалета {unique_id[:4]}",
            "kind": "pallet",
        },
    )
    pallet = await stock_e2e_op(
        page,
        "stock/container_create", "stock/container_create/requested",
        {
            "warehouse_id": ctx["warehouse_id"],
            "parent_location_id": ctx["zone_id"],
            "container_type_id": pallet_type["container_type_id"],
            "name": f"Палета-{unique_id[:4]}",
            "barcode": f"PLT-{unique_id[:6]}",
        },
    )
    pallet_id = pallet["location_id"]
    # Приход кладёт товар по putaway-рефлексу (не обязательно на палету);
    # укладка в тару — внутренний трансфер, для него рефлекс не срабатывает.
    _ = await _receive(page, ctx, "6", dest_location_id=ctx["bin_id"])
    quants = await stock_e2e_op(
        page, "stock/quants", "stock/quants/list_requested",
        {"warehouse_id": ctx["warehouse_id"], "product_id": ctx["product_id"]},
    )
    quant_loc = next(
        q["location_id"] for q in quants["items"]
        if q["product_id"] == ctx["product_id"]
    )
    op_types = await stock_e2e_op(
        page,
        "stock/operation_types_list", "stock/operation_types_list/requested",
        {"warehouse_id": ctx["warehouse_id"]},
    )
    op_internal = next(
        op["operation_type_id"] for op in op_types["items"]
        if op["code"] == "internal"
    )
    pack = await stock_e2e_op(
        page,
        "stock/transfer_create", "stock/transfer_create/requested",
        {
            "warehouse_id": ctx["warehouse_id"],
            "operation_type_id": op_internal,
            "moves": [
                {
                    "product_id": ctx["product_id"],
                    "product_qty": "6",
                    "uom_id": ctx["uom_id"],
                    "location_id": quant_loc,
                    "location_dest_id": pallet_id,
                }
            ],
        },
    )
    await stock_e2e_op(
        page,
        "stock/transfer_confirm", "stock/transfer_confirm/requested",
        {"transfer_id": pack["transfer_id"]},
    )
    await stock_e2e_op(
        page,
        "stock/transfer_validate", "stock/transfer_validate/requested",
        {"transfer_id": pack["transfer_id"]},
    )

    await stock_e2e_nav(page, 'stock_packages', page_selector="stock-packages-page")
    card = page.locator("stock-packages-page .pkg").filter(
        has_text=f"Палета-{unique_id[:4]}"
    )
    await expect(card.first).to_be_visible(timeout=30_000)
    contents = page.locator("stock-packages-page .main table")
    await card.first.click()
    await expect(contents).to_contain_text(
        f"Кофе зерновой {unique_id[:4]}", timeout=30_000
    )
    await scenario.step(
        "Откройте палету и проверьте содержимое",
        page,
        screenshot_name="container-contents",
        label_en="Open the pallet and check contents",
        details=(
            "Слева — список всей тары: палеты, короба, тележки. Клик "
            "открывает карточку: текущее место и таблица содержимого — "
            "какой товар и сколько внутри."
        ),
        details_en=(
            "The list on the left shows all containers: pallets, boxes, "
            "carts. Clicking opens the card: current location and a "
            "contents table — which goods and how much is inside."
        ),
    )

    move_btn = page.locator(
        "stock-packages-page .main platform-button[variant='secondary']"
    ).first
    await move_btn.locator("button").click()
    dest_combo = page.locator(
        "stock-packages-page .move-bar platform-searchable-combobox"
    )
    await dest_combo.locator("input").click()
    option = dest_combo.locator("li.item").filter(
        has_text=f"Ячейка {unique_id[:4]}"
    )
    await expect(option.first).to_be_visible(timeout=15_000)
    await option.first.click()
    apply = page.locator(
        "stock-packages-page .move-bar platform-button[variant='primary']"
    )
    await apply.locator("button").click()
    await expect(
        page.locator("stock-packages-page page-header .subtitle")
    ).to_contain_text(f"Ячейка {unique_id[:4]}", timeout=30_000)
    await scenario.step(
        "Переместите палету целиком",
        page,
        screenshot_name="container-moved",
        label_en="Move the whole pallet",
        details=(
            "Кнопка «Переместить» предлагает выбрать новое место — зону "
            "или ячейку. После подтверждения палета и всё её содержимое "
            "числятся уже там: тащить товар поштучно не нужно.\n\n"
            "**Итог.** Тара — полноценная ячейка: содержимое видно, а "
            "перемещение оформляется одним действием."
        ),
        details_en=(
            "The «Move» button asks for a new spot — a zone or a bin. "
            "After confirming, the pallet and everything inside it belong "
            "to the new location: no piece-by-piece hauling needed.\n\n"
            "**Summary.** A container is a full-fledged bin: contents are "
            "visible, and relocation takes a single action."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="locations",
    doc_slug="inventory-count",
    title="Инвентаризация: сверить факт с учётом",
    title_en="Inventory count: reconcile actual vs recorded",
    description=(
        "**Для чего:** периодический пересчёт ячеек держит остатки честными: "
        "вводите фактическое количество, система показывает расхождение и "
        "проводит корректировку.\n\n"
        "**Какие проблемы решает:** товар теряется, бьётся, пересортивается "
        "— без пересчёта учёт расходится с полкой. Здесь видно, какие ячейки "
        "пора пересчитать.\n\n"
        "**Результат:** вы внесли факт, применили пересчёт — остаток "
        "подровнялся под реальность."
    ),
    description_en=(
        "**Purpose:** periodic bin counts keep stock honest: enter the "
        "actual quantity, the system shows the gap and posts an "
        "adjustment.\n\n"
        "**Problems solved:** goods get lost, broken or mixed up — without "
        "counts the records drift from the shelf. The screen shows which "
        "bins are due for counting.\n\n"
        "**Result:** you entered the actual count, applied it — the "
        "recorded stock now matches reality."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_inventory_count(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)
    ctx = await _ctx(page, unique_id)
    _ = await _receive(page, ctx, "10", dest_location_id=ctx["bin_id"])

    await stock_e2e_nav(page, 'stock_inventory', page_selector="stock-inventory-page")
    wh_combo = page.locator(
        "stock-inventory-page platform-searchable-combobox"
    )
    wh_input = wh_combo.locator("input")
    await wh_input.click()
    await wh_input.fill(f"Склад {unique_id[:4]}")
    wh_option = wh_combo.locator("li.item").filter(
        has_text=f"Склад {unique_id[:4]}"
    )
    await expect(wh_option.first).to_be_visible(timeout=15_000)
    await wh_option.first.click()
    due = page.locator("stock-inventory-page .due").filter(
        has_text=f"Ячейка {unique_id[:4]}"
    )
    await expect(due.first).to_be_visible(timeout=30_000)
    await scenario.step(
        "Выберите ячейку из списка «пора считать»",
        page,
        screenshot_name="inventory-due-list",
        label_en="Pick a bin from the due list",
        details=(
            "Слева собраны ячейки, которые пора пересчитать: давно не "
            "считали или не считали вовсе. Клик по ячейке открывает "
            "остатки внутри неё."
        ),
        details_en=(
            "The list on the left collects bins due for counting: not "
            "counted for a while or never at all. Clicking a bin opens "
            "the stock inside it."
        ),
    )

    fact = page.locator("stock-inventory-page [data-count-input]")
    # WS-загрузка остатков может падать под нагрузкой — пользователь
    # кликает ячейку повторно, повторяя запрос quants.
    for _ in range(3):
        await due.first.click()
        try:
            await expect(fact.first).to_be_visible(timeout=15_000)
            break
        except AssertionError:
            continue
    else:
        await expect(fact.first).to_be_visible(timeout=15_000)
    await ui_set_platform_field(fact.first, "7")
    set_btn = page.locator(
        "stock-inventory-page tbody platform-button[variant='secondary']"
    ).first
    await set_btn.locator("button").click()
    await scenario.step(
        "Введите фактическое количество",
        page,
        screenshot_name="inventory-fact-entered",
        label_en="Enter the actual quantity",
        details=(
            "В колонке «Факт» впишите, сколько реально лежит на полке, и "
            "нажмите галочку — система запомнит значение и подсветит "
            "расхождение с учётным количеством."
        ),
        details_en=(
            "In the «Actual» column type what is really on the shelf and "
            "press the checkmark — the system records the value and "
            "highlights the gap versus the book quantity."
        ),
    )

    apply_btn = page.locator(
        "stock-inventory-page .main platform-button[variant='primary']"
    ).first
    await apply_btn.locator("button").click()
    confirm = page.locator("platform-confirm-modal")
    await expect(confirm).to_be_visible(timeout=15_000)
    await confirm.locator(".btn-primary").click()
    qty_cell = page.locator("stock-inventory-page tbody td.num").first
    await expect(qty_cell).to_contain_text("7", timeout=30_000)
    await scenario.step(
        "Примените пересчёт",
        page,
        screenshot_name="inventory-applied",
        label_en="Apply the count",
        details=(
            "«Применить» проводит корректировку: учётное количество "
            "подравнивается под факт, а разница уходит в журнал "
            "движений.\n\n"
            "**Итог.** Пять минут с мобильным на полке — и учёт снова "
            "совпадает с реальностью."
        ),
        details_en=(
            "«Apply» posts the adjustment: the recorded quantity is "
            "aligned with the actual count, and the difference lands in "
            "the moves journal.\n\n"
            "**Summary.** Five minutes on the shelf with a mobile — and "
            "the records match reality again."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="settings",
    doc_slug="settings-warehouse",
    title="Настройки склада: склады, типы хранения, тара",
    title_en="Warehouse settings: warehouses, storage and container types",
    description=(
        "**Для чего:** раздел «Настройки» держит справочники склада: сами "
        "склады, типы хранения ячеек и виды тары.\n\n"
        "**Какие проблемы решает:** новый склад или новый вид палеты "
        "заводится здесь — без него не создать ячейки и тару нужного "
        "вида.\n\n"
        "**Результат:** вы завели склад и тип хранения через формы "
        "настроек."
    ),
    description_en=(
        "**Purpose:** the «Settings» section holds warehouse references: "
        "the warehouses themselves, bin storage types and container "
        "kinds.\n\n"
        "**Problems solved:** a new warehouse or a new pallet kind is "
        "registered here — bins and containers of the right kind cannot "
        "be created without it.\n\n"
        "**Result:** you registered a warehouse and a storage type via "
        "the settings forms."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_settings_warehouse(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)

    await stock_e2e_nav(
        page, 'stock_warehouses', page_selector="stock-warehouses-page"
    )
    wh_page = page.locator("stock-warehouses-page")
    await wh_page.locator("page-header platform-button[data-create]").first.locator("button").click()
    form = page.locator("stock-entity-form-modal")
    await expect(form.locator("platform-field").first).to_be_visible(timeout=15_000)
    fields = form.locator("platform-field")
    await ui_set_platform_field(fields.nth(0), f"2-{unique_id[:6].upper()}")
    await ui_set_platform_field(fields.nth(1), f"Склад-филиал {unique_id[:4]}")
    await scenario.step(
        "Заведите новый склад",
        page,
        screenshot_name="warehouse-create-form",
        label_en="Register a new warehouse",
        details=(
            "В «Настройки → Склады» нажмите «Создать» и заполните код и "
            "название. Схема склада (layout) и стратегия списания (FIFO/"
            "FEFO/LIFO) уже подобраны разумными значениями — меняйте при "
            "необходимости."
        ),
        details_en=(
            "In «Settings → Warehouses» click «Create» and fill in code "
            "and name. Layout preset and removal strategy (FIFO/FEFO/"
            "LIFO) come with sensible defaults — adjust if needed."
        ),
    )

    await form.locator(".header-save-btn").click()
    row = wh_page.locator("tbody tr").filter(
        has_text=f"Склад-филиал {unique_id[:4]}"
    )
    await expect(row.first).to_be_visible(timeout=30_000)
    await scenario.step(
        "Склад появился в справочнике",
        page,
        screenshot_name="warehouse-in-table",
        label_en="Warehouse appears in the directory",
        details=(
            "Новый склад сразу в таблице — с кодом, схемой и стратегией. "
            "Ниже на этой же странице для выбранного склада видны типы "
            "операций: приход, отгрузка, внутренние перемещения."
        ),
        details_en=(
            "The new warehouse is in the table right away — with its "
            "code, layout and strategy. Below on the same page the "
            "operation types of the selected warehouse are shown: "
            "receipt, delivery, internal moves."
        ),
    )

    await stock_e2e_nav(
        page, 'stock_storage_types', page_selector="stock-storage-types-page"
    )
    st_page = page.locator("stock-storage-types-page")
    await stock_e2e_pick_warehouse(st_page, f"Склад-филиал {unique_id[:4]}")
    await st_page.locator("page-header platform-button[data-create]").first.locator("button").click()
    st_form = page.locator("stock-entity-form-modal")
    await expect(st_form.locator("platform-field").first).to_be_visible(timeout=15_000)
    st_fields = st_form.locator("platform-field")
    await ui_set_platform_field(st_fields.nth(1), f"Стеллаж {unique_id[:4]}")
    await ui_set_platform_field(st_fields.nth(4), "30")
    await scenario.step(
        "Создайте тип хранения",
        page,
        screenshot_name="storage-type-form",
        label_en="Create a storage type",
        details=(
            "«Настройки → Типы хранения» задают правила ячейки: лимит "
            "тары, вес и интервал пересчёта в днях — он решает, когда "
            "ячейка попадёт в инвентаризацию. Выберите склад, нажмите "
            "«Создать» и заполните форму."
        ),
        details_en=(
            "«Settings → Storage types» define bin rules: container "
            "limit, weight and the count interval in days — it decides "
            "when the bin lands on the inventory list. Pick a warehouse, "
            "click «Create» and fill the form."
        ),
    )

    await st_form.locator(".header-save-btn").click()
    st_row = st_page.locator("tbody tr").filter(
        has_text=f"Стеллаж {unique_id[:4]}"
    )
    await expect(st_row.first).to_be_visible(timeout=30_000)
    await scenario.step(
        "Тип хранения готов к работе",
        page,
        screenshot_name="storage-type-created",
        label_en="Storage type is ready",
        details=(
            "Тип появился в таблице склада — теперь его можно назначать "
            "ячейкам. Так же настраиваются виды тары, ресурсы склада, "
            "правила размещения и пополнения в соседних разделах "
            "настроек.\n\n"
            "**Итог.** Справочники склада ведутся в одном месте: склад "
            "создан, правила его ячеек заданы."
        ),
        details_en=(
            "The type appears in the warehouse table — now it can be "
            "assigned to bins. Container kinds, warehouse resources, "
            "putaway and reorder rules are configured the same way in "
            "the neighbouring settings sections.\n\n"
            "**Summary.** Warehouse references live in one place: the "
            "warehouse is created and its bin rules are set."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="settings",
    doc_slug="settings-uoms",
    title="Единицы измерения и упаковки",
    title_en="Units of measure and packagings",
    description=(
        "**Для чего:** раздел «Единицы измерения» ведёт два справочника: "
        "базовые ЕИ компании (штуки, килограммы, свои «ящики») и упаковки "
        "товаров («короб 24 шт» со своим штрихкодом).\n\n"
        "**Какие проблемы решает:** без ЕИ товар не завести, а без "
        "упаковки ТСД не поймёт скан кода целого короба.\n\n"
        "**Результат:** создана своя ЕИ, к товару привязана упаковка, "
        "лишняя ЕИ удалена — справочник соответствует реальным меркам "
        "склада."
    ),
    description_en=(
        "**Purpose:** the «Units of measure» section maintains two "
        "directories: company base UoMs (units, kilograms, custom "
        "«crates») and product packagings («box of 24» with its own "
        "barcode).\n\n"
        "**Problems solved:** a product cannot be registered without a "
        "UoM, and the mobile scanner cannot decode a full-box barcode "
        "without a packaging.\n\n"
        "**Result:** a custom UoM is created, a packaging is bound to "
        "the product, the spare UoM is deleted — the directory matches "
        "real warehouse measures."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(240)
async def test_settings_uoms(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)

    uoms = await stock_e2e_op(page, "stock/uoms_list", "stock/uoms_list/requested")
    uom_id = next(u["uom_id"] for u in uoms["items"] if u["name"] == "Units")
    product = await stock_e2e_op(
        page,
        "stock/product_create", "stock/product_create/requested",
        {
            "name": f"Сахар {unique_id[:4]}",
            "sku": f"SUG-{unique_id[:6]}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "standard_price": "0",
            "tracking": "none",
            "is_storable": True,
        },
    )

    await stock_e2e_nav(
        page, 'stock_uoms', page_selector="stock-uoms-page"
    )
    uoms_page = page.locator("stock-uoms-page")

    await uoms_page.locator(".section platform-button").first.locator("button").click()
    modal = page.locator("stock-entity-form-modal")
    await expect(modal.locator("platform-field").first).to_be_visible(timeout=15_000)
    fields = modal.locator("platform-field")
    await ui_set_platform_field(fields.nth(0), f"Ящик {unique_id[:4]}")
    await ui_set_platform_field(fields.nth(1), "unit")
    await ui_set_platform_field(fields.nth(2), "12")
    await scenario.step(
        "Создайте свою единицу измерения",
        page,
        screenshot_name="uom-create-modal",
        label_en="Create a custom unit of measure",
        details=(
            "В «Настройки → Единицы измерения» нажмите «Создать» рядом с "
            "«Базовые ЕИ»: имя, категория и коэффициент к базе. Ящик ×12 "
            "означает «один ящик — это 12 штук»."
        ),
        details_en=(
            "In «Settings → Units of measure» click «Create» next to "
            "«Base UoMs»: name, category and the factor to base. A "
            "crate ×12 means «one crate equals twelve units»."
        ),
    )

    await modal.locator(".header-save-btn").click()
    row = uoms_page.locator("tbody tr").filter(has_text=f"Ящик {unique_id[:4]}")
    await expect(row.first).to_be_visible(timeout=15_000)
    await scenario.step(
        "ЕИ появилась в справочнике",
        page,
        screenshot_name="uom-in-table",
        label_en="The UoM appears in the directory",
        details=(
            "Новая ЕИ сразу в таблице базовых — её можно назначать "
            "товарам базовой единицей. Системные «Units», «kg», «m» "
            "помечены как эталонные и не удаляются."
        ),
        details_en=(
            "The new UoM is in the base table right away — it can be "
            "assigned as a product base unit. System «Units», «kg», "
            "«m» are marked reference and cannot be deleted."
        ),
    )

    await uoms_page.locator(".section platform-button").nth(1).locator("button").click()
    pkg_modal = page.locator("stock-entity-form-modal")
    await expect(pkg_modal.locator("platform-field").first).to_be_visible(timeout=15_000)
    pkg_fields = pkg_modal.locator("platform-field")
    await ui_set_platform_field(pkg_fields.nth(0), product["product_id"])
    await ui_set_platform_field(pkg_fields.nth(1), f"Короб-24 {unique_id[:4]}")
    await ui_set_platform_field(pkg_fields.nth(2), "24")
    await pkg_modal.locator(".header-save-btn").click()
    pkg_row = uoms_page.locator("tbody tr").filter(has_text=f"Короб-24 {unique_id[:4]}")
    await expect(pkg_row.first).to_be_visible(timeout=15_000)
    await scenario.step(
        "Привяжите упаковку к товару",
        page,
        screenshot_name="packaging-in-table",
        label_en="Bind a packaging to the product",
        details=(
            "В секции «Упаковки» выберите товар, имя упаковки и "
            "количество базовых ЕИ внутри. Скан такой упаковки на ТСД "
            "считается как «24 штуки» — считать поштучно не нужно."
        ),
        details_en=(
            "In the «Packagings» section pick the product, the "
            "packaging name and how many base units it holds. Scanning "
            "such a packaging on the mobile counts as «24 units» — no "
            "piece-by-piece counting."
        ),
    )

    uom_row = uoms_page.locator("tbody tr").filter(has_text=f"Ящик {unique_id[:4]}")
    await uom_row.first.locator(".icon-btn").click()
    confirm = page.locator("platform-confirm-modal")
    await expect(confirm.locator("button.btn-danger")).to_be_visible(timeout=10_000)
    await confirm.locator("button.btn-danger").click()
    await expect(uom_row.first).to_be_hidden(timeout=15_000)
    await scenario.step(
        "Удалите лишнюю ЕИ",
        page,
        screenshot_name="uom-deleted",
        label_en="Delete the spare UoM",
        details=(
            "Своя ЕИ удаляется корзиной с подтверждением — пока она не "
            "стала базовой у товара. Упаковки удаляются так же из своей "
            "секции.\n\n"
            "**Итог.** Мерки склада описаны полностью: базовые ЕИ для "
            "товаров, упаковки — для быстрого скана."
        ),
        details_en=(
            "A custom UoM is deleted via the trash icon with "
            "confirmation — as long as no product uses it as base. "
            "Packagings are deleted the same way in their section.\n\n"
            "**Summary.** Warehouse measures are fully described: base "
            "UoMs for products, packagings for fast scanning."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="settings",
    doc_slug="settings-catalogs",
    title="Справочники: техника, правила размещения и маршруты",
    title_en="Catalogs: equipment, putaway and reorder rules, routes",
    description=(
        "**Для чего:** в «Настройках» живут рабочие справочники склада: "
        "единицы техники (погрузчики, тележки), правила «куда класть "
        "товар» и «когда пополнять», а также типы маршрутов.\n\n"
        "**Какие проблемы решает:** без техники ТСД не выдаст задание "
        "на погрузчик, без правил размещения система не подскажет ячейку "
        "хранения, а без правил пополнения зона отбора пустеет "
        "незаметно.\n\n"
        "**Результат:** заведён тип техники и сам погрузчик, ячейкам "
        "назначено правило размещения, товару — правило пополнения, "
        "создан тип маршрута."
    ),
    description_en=(
        "**Purpose:** the «Settings» section holds the working "
        "directories: equipment units (forklifts, carts), «where to "
        "store» putaway rules, «when to refill» reorder rules, and "
        "route types.\n\n"
        "**Problems solved:** without equipment the scanner cannot "
        "dispatch a forklift task, without putaway rules the system "
        "cannot suggest a storage bin, and without reorder rules the "
        "pick zone silently runs dry.\n\n"
        "**Result:** an equipment type and a forklift are registered, "
        "bins get a putaway rule, the product gets a reorder rule, "
        "and a route type is created."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_settings_catalogs(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)
    ctx = await _ctx(page, unique_id)

    # --- Тип ресурса + сам ресурс ----------------------------------------
    await stock_e2e_nav(
        page, 'stock_resources', page_selector="stock-resources-page"
    )
    res_page = page.locator("stock-resources-page")
    await stock_e2e_pick_warehouse(res_page, f"Склад {unique_id[:4]}")
    await res_page.locator(".section platform-button").locator("button").click()
    type_modal = page.locator("stock-entity-form-modal")
    await expect(type_modal.locator("platform-field").first).to_be_visible(timeout=15_000)
    type_fields = type_modal.locator("platform-field")
    await ui_set_platform_field(type_fields.nth(0), ctx["warehouse_id"])
    await ui_set_platform_field(type_fields.nth(1), f"Погрузчик {unique_id[:4]}")
    await ui_set_platform_field(type_fields.nth(3), "4")
    await scenario.step(
        "Опишите вид техники",
        page,
        screenshot_name="resource-type-create",
        label_en="Describe the equipment kind",
        details=(
            "В «Настройки → Ресурсы» нижняя секция — «Типы ресурсов». "
            "«Создать» задаёт, что это за техника: название, сколько "
            "уровней груза поднимает и предельный вес."
        ),
        details_en=(
            "In «Settings → Resources» the bottom section is «Resource "
            "types». «Create» describes the equipment: name, how many "
            "load levels it lifts and the weight limit."
        ),
    )
    await type_modal.locator(".header-save-btn").click()
    type_row = res_page.locator("tbody tr").filter(
        has_text=f"Погрузчик {unique_id[:4]}"
    )
    await expect(type_row.first).to_be_visible(timeout=15_000)
    types: dict[str, Any] = await page.evaluate(
        """async (wh) => {
            const r = await fetch(`/stock/api/v1/resource-types?warehouse_id=${wh}`);
            return await r.json();
        }""",
        ctx["warehouse_id"],
    )
    type_id = next(
        (t["resource_type_id"] for t in types.get("items", [])
         if t["name"] == f"Погрузчик {unique_id[:4]}"),
        None,
    )
    assert type_id is not None, f"resource type не найден в списке: {types}"

    await res_page.locator("page-header platform-button[data-create]").locator("button").click()
    res_modal = page.locator("stock-entity-form-modal")
    await expect(res_modal.locator("platform-field").first).to_be_visible(timeout=15_000)
    res_fields = res_modal.locator("platform-field")
    await ui_set_platform_field(res_fields.nth(0), ctx["warehouse_id"])
    await ui_set_platform_field(res_fields.nth(1), f"FORK-{unique_id[:4]}")
    await ui_set_platform_field(res_fields.nth(2), type_id)
    await ui_set_platform_field(res_fields.nth(3), f"RES-{unique_id[:6]}")
    await res_modal.locator(".header-save-btn").click()
    res_row = res_page.locator("tbody tr").filter(has_text=f"FORK-{unique_id[:4]}")
    await expect(res_row.first).to_be_visible(timeout=15_000)
    await scenario.step(
        "Заведите единицу техники",
        page,
        screenshot_name="resource-in-table",
        label_en="Register an equipment unit",
        details=(
            "Кнопка «Создать» в шапке добавляет конкретную единицу: "
            "код, тип из нижней секции и штрихкод для привязки к ТСД. "
            "Теперь погрузчик можно указывать в заданиях."
        ),
        details_en=(
            "The header «Create» button registers a concrete unit: "
            "code, its type from the bottom section and a barcode for "
            "scanner pairing. The forklift can now be assigned to "
            "tasks."
        ),
    )

    # --- Правило размещения -----------------------------------------------
    await stock_e2e_nav(
        page, 'stock_putaway_rules', page_selector="stock-putaway-rules-page"
    )
    putaway_page = page.locator("stock-putaway-rules-page")
    await stock_e2e_pick_warehouse(putaway_page, f"Склад {unique_id[:4]}")
    await putaway_page.locator("page-header platform-button[data-create]").locator("button").click()
    put_modal = page.locator("stock-entity-form-modal")
    await expect(put_modal.locator("platform-field").first).to_be_visible(timeout=15_000)
    put_fields = put_modal.locator("platform-field")
    await ui_set_platform_field(put_fields.nth(0), ctx["warehouse_id"])
    await ui_set_platform_field(put_fields.nth(1), ctx["zone_id"])
    await ui_set_platform_field(put_fields.nth(2), ctx["bin_id"])
    await ui_set_platform_field(put_fields.nth(3), ctx["product_id"])
    await ui_set_platform_field(put_fields.nth(4), "10")
    await expect(put_modal.locator(".header-save-btn")).to_be_enabled(timeout=10_000)
    await put_modal.locator(".header-save-btn").click()
    await expect(put_modal).to_be_hidden(timeout=15_000)
    put_row = putaway_page.locator("tbody tr").filter(has_text=f"Зона {unique_id[:4]}")
    await expect(put_row.first).to_be_visible(timeout=15_000)
    await scenario.step(
        "Назначьте правило размещения",
        page,
        screenshot_name="putaway-rule-in-table",
        label_en="Assign a putaway rule",
        details=(
            "«Настройки → Правила размещения» отвечают на вопрос «куда "
            "убрать приехавший товар»: из зоны приёмки — в конкретную "
            "ячейку хранения. Порядок «Sequence» решает, какое правило "
            "срабатывает первым."
        ),
        details_en=(
            "«Settings → Putaway rules» answers «where does incoming "
            "stock go»: from the receiving zone into a concrete storage "
            "bin. «Sequence» decides which rule fires first."
        ),
    )

    # --- Правило пополнения ------------------------------------------------
    op_types = await stock_e2e_op(
        page,
        "stock/operation_types_list", "stock/operation_types_list/requested",
        {"warehouse_id": ctx["warehouse_id"]},
    )
    op_in = next(
        op["operation_type_id"] for op in op_types["items"] if op["code"] == "incoming"
    )
    await stock_e2e_nav(
        page, 'stock_reorder_rules', page_selector="stock-reorder-rules-page"
    )
    reorder_page = page.locator("stock-reorder-rules-page")
    await stock_e2e_pick_warehouse(reorder_page, f"Склад {unique_id[:4]}")
    await reorder_page.locator("page-header platform-button[data-create]").locator("button").click()
    re_modal = page.locator("stock-entity-form-modal")
    await expect(re_modal.locator("platform-field").first).to_be_visible(timeout=15_000)
    re_fields = re_modal.locator("platform-field")
    await ui_set_platform_field(re_fields.nth(0), ctx["warehouse_id"])
    await ui_set_platform_field(re_fields.nth(1), ctx["product_id"])
    await ui_set_platform_field(re_fields.nth(2), ctx["bin_id"])
    await ui_set_platform_field(re_fields.nth(3), "5")
    await ui_set_platform_field(re_fields.nth(4), "20")
    await ui_set_platform_field(re_fields.nth(5), op_in)
    await re_modal.locator(".header-save-btn").click()
    re_row = reorder_page.locator("tbody tr").filter(has_text=f"Кофе зерновой {unique_id[:4]}")
    await expect(re_row.first).to_be_visible(timeout=15_000)
    await scenario.step(
        "Задайте минимум и максимум запаса",
        page,
        screenshot_name="reorder-rule-in-table",
        label_en="Set the min and max stock",
        details=(
            "«Правила пополнения» следят за ячейкой: упало ниже "
            "минимума — система предложит документ пополнения до "
            "максимума. Сначала выберите склад в панели фильтра — "
            "тогда в форме появятся его виды операций."
        ),
        details_en=(
            "«Reorder rules» watch the bin: below the minimum the "
            "system suggests a replenishment up to the maximum. Pick "
            "the warehouse in the filter bar first — its operation "
            "types appear in the form."
        ),
    )

    # --- Партии оценки ------------------------------------------------------
    await _receive(page, ctx, "25", ctx["bin_id"])
    await stock_e2e_nav(
        page, 'stock_valuation_batches', page_selector="stock-valuation-batches-page"
    )
    batches_page = page.locator("stock-valuation-batches-page")
    batch_row = batches_page.locator("tbody tr").filter(
        has_text=f"Кофе зерновой {unique_id[:4]}"
    )
    await ui_set_platform_field(
        batches_page.locator("[data-valuation-search] platform-field"),
        f"Кофе зерновой {unique_id[:4]}",
    )
    await expect(batch_row.first).to_be_visible(timeout=15_000)
    await scenario.step(
        "Проверьте партию запаса",
        page,
        screenshot_name="valuation-batch-in-table",
        label_en="Check the stock layer",
        details=(
            "«Оценка → Партии» показывает каждую приёмку отдельной "
            "строкой: сколько пришло, по какой цене и сколько осталось. "
            "Только что проведённый приход виден сразу — это и есть "
            "слой, который уйдёт первым по FIFO."
        ),
        details_en=(
            "«Valuation → Batches» lists each receipt as its own row: "
            "how much arrived, at what price and what is left. The "
            "receipt just posted is right there — the layer that FIFO "
            "consumes first."
        ),
    )

    # --- Маршрут ------------------------------------------------------------
    await stock_e2e_nav(
        page, 'stock_routes', page_selector="stock-routes-page"
    )
    routes_page = page.locator("stock-routes-page")
    await routes_page.locator("page-header platform-button[data-create]").locator("button").click()
    route_modal = page.locator("stock-entity-form-modal")
    await expect(route_modal.locator("platform-field").first).to_be_visible(timeout=15_000)
    route_fields = route_modal.locator("platform-field")
    await ui_set_platform_field(route_fields.nth(0), f"Сборка {unique_id[:4]}")
    await ui_set_platform_field(route_fields.nth(1), f"RT-{unique_id[:4]}")
    await route_modal.locator(".header-save-btn").click()
    route_row = routes_page.locator("tbody tr").filter(has_text=f"Сборка {unique_id[:4]}")
    await expect(route_row.first).to_be_visible(timeout=15_000)
    await scenario.step(
        "Создайте тип маршрута",
        page,
        screenshot_name="route-in-table",
        label_en="Create a route type",
        details=(
            "«Маршруты» описывают путь заказа по складам — например "
            "«комплектация → проверка → отгрузка». Здесь задаётся "
            "название и код типа, шаги добавляются в карточке "
            "маршрута.\n\n"
            "**Итог.** Справочники склада заведены: техника готова к "
            "заданиям, размещение и пополнение работают по правилам, "
            "тип маршрута ждёт своих шагов."
        ),
        details_en=(
            "«Routes» describe an order's path across warehouses — "
            "e.g. «picking → checking → shipping». The type gets a "
            "name and a code here; steps are added on the route "
            "card.\n\n"
            "**Summary.** The warehouse directories are ready: "
            "equipment is taskable, putaway and reorder work by rules, "
            "and the route type awaits its steps."
        ),
    )
