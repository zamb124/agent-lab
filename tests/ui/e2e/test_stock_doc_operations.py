"""Документационные сценарии Stock: движения, тара, инвентаризация, настройки.

Данные готовит тот же op-канал, что и SPA; пользовательский путь — через UI:
журнал движений, карточка тары, пересчёт ячейки и справочники склада.
"""

from __future__ import annotations

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.stock_e2e_helpers import (
    stock_e2e_nav,
    stock_e2e_op,
    stock_e2e_open,
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
        page.locator("stock-transfer-page h1")
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
        page.locator("stock-packages-page .meta")
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
    await wh_page.locator(".head platform-button").first.locator("button").click()
    form = wh_page.locator(".create-panel")
    await expect(form).to_be_visible(timeout=15_000)
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

    save = form.locator("platform-button[variant='primary']")
    await save.locator("button").click()
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
    wh_filter = st_page.locator(".head platform-searchable-combobox")
    await wh_filter.locator("input").click()
    wh_option = wh_filter.locator("li.item").filter(
        has_text=f"Склад-филиал {unique_id[:4]}"
    )
    await expect(wh_option.first).to_be_visible(timeout=15_000)
    await wh_option.first.click()
    await st_page.locator(".head platform-button").first.locator("button").click()
    st_form = st_page.locator(".create-panel")
    await expect(st_form).to_be_visible(timeout=15_000)
    st_fields = st_form.locator("platform-field")
    await ui_set_platform_field(st_fields.nth(0), f"Стеллаж {unique_id[:4]}")
    await ui_set_platform_field(st_fields.nth(3), "30")
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

    await st_form.locator("platform-button[variant='primary']").locator(
        "button"
    ).click()
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
