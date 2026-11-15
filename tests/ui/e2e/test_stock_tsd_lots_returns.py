"""Документационные сценарии Stock TSD: партии, серийники, возвраты.

Физические маршруты оператора с прослеживаемостью: приёмка партийного
товара с вводом номера партии и срока годности с этикетки, приёмка
серийных устройств по одному SN за скан, возврат от покупателя по
обратной накладной и отбор партии по FEFO («сначала — что скорее
испортится»).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.stock_e2e_helpers import (
    TSD_VIEWPORT,
    stock_quant_qty,
    stock_rest,
    tsd_commit,
    tsd_open,
    tsd_pick_warehouse,
    tsd_qty,
    tsd_scan,
    tsd_seed_document,
    tsd_seed_product_image,
    tsd_seed_stock,
    tsd_seed_warehouse,
    tsd_set_platform_field,
    tsd_wait_ws_open,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


def _expiry(days: int) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).date().isoformat()


@pytest.mark.scenario(
    service="stock",
    tag="tsd-receive",
    doc_slug="stock-tsd-receive-lots",
    title="Приёмка партийного товара: номер партии и срок годности",
    title_en="Receiving lot-tracked stock: lot number and expiry date",
    description=(
        "**Для чего:** продукты, лекарства и косметику складам принято "
        "вести партиями — каждая поставка имеет свой номер и «годен до». "
        "Без этого нельзя понять, что просрочено, и отгружать старое "
        "раньше нового.\n\n"
        "**Какие проблемы решает:** терминал сам просит номер партии и "
        "срок годности ровно в тот момент, когда они нужны — после скана "
        "ячейки, до количества. Если на упаковке есть только бумажная "
        "этикетка, данные вводятся руками в два коротких поля.\n\n"
        "**Результат:** два партийных товара приняты каждый в свою "
        "партию, сроки годности записаны, партии видны в справочнике "
        "и на остатках."
    ),
    description_en=(
        "**Purpose:** food, pharma and cosmetics are managed in lots — "
        "each delivery has its own number and «best before» date. "
        "Without this you cannot tell what expired or ship oldest "
        "first.\n\n"
        "**Problems solved:** the terminal asks for the lot number and "
        "expiry exactly when needed — after the bin scan, before "
        "quantity. With only a paper label, data is typed into two "
        "short fields.\n\n"
        "**Result:** two lot-tracked products received into their own "
        "lots, expiry dates recorded, lots visible in the catalogue "
        "and on stock."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_receive_lots(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(TSD_VIEWPORT)
    await tsd_open(page, stock_ui)

    # --- Топология + два партийных товара ---
    seed = await tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    bin_b = seed["bin_b"]
    uom_id = seed["uom_id"]
    product_1 = await stock_rest(
        page, "POST", "/products",
        {
            "name": f"Молоко паст. {unique_id[:4]}",
            "sku": f"MILK-{unique_id[:6]}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "standard_price": "0",
            "tracking": "lot",
            "is_storable": True,
            "barcodes": [f"BC-M-{unique_id[:6]}"],
        },
    )
    product_2 = await stock_rest(
        page, "POST", "/products",
        {
            "name": f"Творог {unique_id[:4]}",
            "sku": f"CURD-{unique_id[:6]}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "standard_price": "0",
            "tracking": "lot",
            "is_storable": True,
            "barcodes": [f"BC-C-{unique_id[:6]}"],
        },
    )
    await tsd_seed_product_image(
        page, str(product_1["product_id"]), color="#4a90d9", label="МОЛ"
    )
    await tsd_seed_product_image(
        page, str(product_2["product_id"]), color="#d9a04a", label="ТВОР"
    )
    await tsd_pick_warehouse(page, unique_id)

    # --- Приёмка 1: молоко → ячейка А → партия со сроком → количество ---
    await tsd_scan(page, f"BC-M-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Молоко паст. {unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "Отсканируйте партийный товар",
        page,
        screenshot_name="tsd-lot-product-card",
        label_en="Scan a lot-tracked product",
        details=(
            "Карточка партийного товара выглядит как у обычного — "
            "фото и остатки по ячейкам. «Принять» стартует сессию "
            "приёмки, разница появится на шаге количества: терминал "
            "попросит партию."
        ),
        details_en=(
            "The lot-tracked product card looks like a regular one — "
            "photo and per-bin stock. «Receive» starts the session; "
            "the difference appears at the quantity step: the "
            "terminal asks for a lot."
        ),
    )
    await sheet.locator(".action[data-action='receive']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")

    lot_panel = run.locator(".lot-panel")
    await expect(lot_panel).to_be_visible(timeout=15_000)
    await tsd_set_platform_field(
        lot_panel.locator("platform-field.lot-input").first, f"LOT-M-{unique_id[:6]}"
    )
    await tsd_set_platform_field(
        lot_panel.locator("platform-field.lot-date"), _expiry(45)
    )
    await scenario.step(
        "Введите номер партии и «годен до»",
        page,
        screenshot_name="tsd-lot-entry",
        label_en="Enter the lot number and expiry",
        details=(
            "Вместо клавиатуры цифр — компактная панель партии: "
            "номер с бумажной этикетки и дата «годен до». Если на "
            "упаковке напечатан GS1-код — сканируйте его, оба поля "
            "заполнятся сами."
        ),
        details_en=(
            "Instead of the numpad — a compact lot panel: the number "
            "from the paper label and the «best before» date. If the "
            "box has a GS1 code — scan it and both fields fill "
            "themselves."
        ),
    )
    await lot_panel.locator(".lot-ok").click()
    numpad = run.locator(".qty-panel .numpad")
    await expect(numpad).to_be_visible(timeout=15_000)
    await tsd_qty(page, "8")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    line_row = run.locator(".line-row").first
    await expect(line_row).to_contain_text(f"LOT-M-{unique_id[:6]}", timeout=10_000)
    await scenario.step(
        "Проверьте строку приёмки",
        page,
        screenshot_name="tsd-lot-line-review",
        label_en="Check the receiving line",
        details=(
            "Строка исполнения показывает товар и введённую партию "
            "рядом с количеством — до проводки видно, что именно "
            "уложится на остаток и с каким номером партии."
        ),
        details_en=(
            "The execution line shows the product and the entered "
            "lot next to the quantity — before committing you see "
            "exactly what lands on stock and under which lot "
            "number."
        ),
    )
    await tsd_commit(page)

    # --- Приёмка 2: творог → ячейка Б → вторая партия ---
    await tsd_scan(page, f"BC-C-{unique_id[:6]}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator(".action[data-action='receive']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    await expect(run).to_be_visible(timeout=15_000)
    await tsd_scan(page, f"BIN-B-{unique_id[:6]}")
    await expect(lot_panel).to_be_visible(timeout=15_000)
    await tsd_set_platform_field(
        lot_panel.locator("platform-field.lot-input").first, f"LOT-C-{unique_id[:6]}"
    )
    await tsd_set_platform_field(
        lot_panel.locator("platform-field.lot-date"), _expiry(10)
    )
    await lot_panel.locator(".lot-ok").click()
    await expect(numpad).to_be_visible(timeout=15_000)
    await tsd_qty(page, "4")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await tsd_commit(page)

    # --- Факт: два лота заведены со сроками, остатки лежат под ними ---
    lots = await stock_rest(
        page, "GET", f"/lots?product_id={product_1['product_id']}"
    )
    lot_m = next(l for l in lots["items"] if l["name"] == f"LOT-M-{unique_id[:6]}")
    assert lot_m["expiration_at"] is not None
    lots_2 = await stock_rest(
        page, "GET", f"/lots?product_id={product_2['product_id']}"
    )
    lot_c = next(l for l in lots_2["items"] if l["name"] == f"LOT-C-{unique_id[:6]}")
    assert lot_c["expiration_at"] is not None
    qty_1 = await stock_quant_qty(page, warehouse_id, product_1["product_id"], bin_a["location_id"])
    qty_2 = await stock_quant_qty(page, warehouse_id, product_2["product_id"], bin_b["location_id"])
    assert qty_1 == Decimal("8")
    assert qty_2 == Decimal("4")

    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Молоко паст. {unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "Отсканируйте ячейку — остаток принят по партии",
        page,
        screenshot_name="tsd-lot-bin-contents",
        label_en="Scan the bin — stock received under the lot",
        details=(
            "**Демонстрация результата.** Ячейка показывает принятое "
            "количество, а справочник партий (раздел «Партии» на "
            "компьютере) — обе новые партии со сроками «годен до»: "
            "по ним система отберёт сначала то, что испортится "
            "раньше.\n\n"
            "**Итог.** Приёмка партийного товара: скан товара → "
            "ячейка → номер партии и «годен до» → количество → "
            "проводка. Партии заводятся на лету, повторный номер "
            "находит уже существующую."
        ),
        details_en=(
            "**Result demonstration.** The bin shows the received "
            "quantity, and the lots catalogue («Lots» on the "
            "desktop) lists both new lots with «best before» dates — "
            "the system will pick what expires earlier first.\n\n"
            "**Summary.** Receiving lot-tracked stock: scan product "
            "→ bin → lot number and expiry → quantity → commit. "
            "Lots are created on the fly; an existing number reuses "
            "the lot."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="tsd-receive",
    doc_slug="stock-tsd-serials",
    title="Приёмка серийных устройств: один скан — одна штука",
    title_en="Receiving serialized devices: one scan, one unit",
    description=(
        "**Для чего:** технику и дорогие товары учитывают по "
        "серийным номерам — каждая единица уникальна, по ней идут "
        "гарантия и возвраты.\n\n"
        "**Какие проблемы решает:** терминал знает, что серийник — "
        "это всегда ровно одна штука: поле количества не показывается "
        "вообще, ввод номера сразу фиксирует единицу. Повторный "
        "серийник система не пропустит — одна единица не может лежать "
        "на складе дважды.\n\n"
        "**Результат:** три серийных устройства приняты по одному "
        "скану каждое, остаток — три позиции по штуке под своими SN."
    ),
    description_en=(
        "**Purpose:** electronics and high-value goods are tracked "
        "by serial number — every unit is unique and drives "
        "warranty and returns.\n\n"
        "**Problems solved:** the terminal knows a serial is always "
        "exactly one unit: no quantity field at all, entering the "
        "number records one instantly. A duplicate serial is "
        "rejected — one unit cannot sit on the warehouse twice.\n\n"
        "**Result:** three serialized devices received, one scan "
        "each — stock holds three single units under their SNs."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_serials(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(TSD_VIEWPORT)
    await tsd_open(page, stock_ui)

    seed = await tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    uom_id = seed["uom_id"]
    product = await stock_rest(
        page, "POST", "/products",
        {
            "name": f"Сканер-кольцо {unique_id[:4]}",
            "sku": f"RING-{unique_id[:6]}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "standard_price": "0",
            "tracking": "serial",
            "is_storable": True,
            "barcodes": [f"BC-R-{unique_id[:6]}"],
        },
    )
    await tsd_seed_product_image(
        page, str(product["product_id"]), color="#7b4ad9", label="SN"
    )
    await tsd_pick_warehouse(page, unique_id)

    await tsd_scan(page, f"BC-R-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator(".action[data-action='receive']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")

    lot_panel = run.locator(".lot-panel")
    await expect(lot_panel).to_be_visible(timeout=15_000)
    await expect(run.locator(".numpad")).to_have_count(0)
    await tsd_set_platform_field(
        lot_panel.locator("platform-field.lot-input").first, f"SN-1-{unique_id[:6]}"
    )
    await scenario.step(
        "Введите серийный номер первого устройства",
        page,
        screenshot_name="tsd-serial-entry",
        label_en="Enter the first device serial",
        details=(
            "Для серийного товара на шаге количества — одно поле "
            "серийника, цифровой клавиатуры нет: система сама ставит "
            "количество 1. После подтверждения строка сразу "
            "фиксируется."
        ),
        details_en=(
            "For a serialized product the quantity step is a single "
            "serial field, no numpad: the system sets quantity 1 "
            "itself. The line is recorded right after confirming."
        ),
    )
    await lot_panel.locator(".lot-ok").click()
    line_row = run.locator(".line-row").first
    await expect(line_row).to_be_visible(timeout=15_000)
    await expect(line_row).to_contain_text(f"SN-1-{unique_id[:6]}", timeout=10_000)

    # --- Второй и третий серийники тем же жестом: товар → ячейка → SN ---
    for n in ("2", "3"):
        await tsd_scan(page, f"BC-R-{unique_id[:6]}")
        await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
        await expect(lot_panel).to_be_visible(timeout=15_000)
        await tsd_set_platform_field(
            lot_panel.locator("platform-field.lot-input").first, f"SN-{n}-{unique_id[:6]}"
        )
        await lot_panel.locator(".lot-ok").click(timeout=12_000)
    await expect(run.locator(".line-row")).to_have_count(3, timeout=15_000)
    await scenario.step(
        "Добавьте остальные серийники",
        page,
        screenshot_name="tsd-serial-lines",
        label_en="Add the remaining serials",
        details=(
            "Каждый серийник — своя строка исполнения: после "
            "фиксации сканируйте товар и вводите следующий номер. "
            "Список строк показывает все SN до проводки."
        ),
        details_en=(
            "Each serial is its own execution line: after recording, "
            "scan the product and enter the next number. The lines "
            "list shows every SN before commit."
        ),
    )
    await tsd_commit(page)

    # --- Факт: три серийных лота по единице, каждый — свой квант ---
    lots = await stock_rest(
        page, "GET", f"/lots?product_id={product['product_id']}"
    )
    lot_by_name = {l["name"]: l["lot_id"] for l in lots["items"]}
    serials = {f"SN-{n}-{unique_id[:6]}" for n in (1, 2, 3)}
    assert serials <= set(lot_by_name)
    quants = await stock_rest(
        page,
        "GET",
        f"/quants?warehouse_id={warehouse_id}&product_id={product['product_id']}",
    )
    rows = [q for q in quants["items"] if q["location_id"] == bin_a["location_id"]]
    assert {q["lot_id"] for q in rows} == {lot_by_name[sn] for sn in serials}
    assert {Decimal(str(q["quantity"])) for q in rows} == {Decimal("1")}

    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Сканер-кольцо {unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "Отсканируйте ячейку — три устройства на остатке",
        page,
        screenshot_name="tsd-serial-bin-contents",
        label_en="Scan the bin — three devices on stock",
        details=(
            "**Демонстрация результата.** Ячейка показывает остаток "
            "«3» — три принятых устройства, каждое под своим "
            "серийником. По ним система узнает конкретную единицу "
            "при отгрузке и возврате.\n\n"
            "**Итог.** Серийный товар принимается по одному скану "
            "на единицу — без поля количества; дубликат номера "
            "система отклонит."
        ),
        details_en=(
            "**Result demonstration.** The bin shows stock «3» — "
            "three received devices, each under its own serial. "
            "The system recognises the exact unit on shipment and "
            "returns.\n\n"
            "**Summary.** Serialized stock is received one scan per "
            "unit — no quantity field; a duplicate number is "
            "rejected."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="tsd-document",
    doc_slug="stock-tsd-return",
    title="Возврат от покупателя: обратная накладная и приёмка",
    title_en="Customer return: reverse order and receiving",
    description=(
        "**Для чего:** покупатель вернул товар — складу нужен "
        "обратный документ и физическая приёмка возврата на "
        "терминале, чтобы единицы вернулись на остатки.\n\n"
        "**Какие проблемы решает:** кнопка «Возврат» на карточке "
        "исполненной накладной создаёт обратный документ сама — "
        "номера, строки и количества переписывать не нужно; терминал "
        "сразу открывает приёмку по нему.\n\n"
        "**Результат:** по отгруженной накладной создан возврат, "
        "обе позиции приняты обратно на ячейки, остатки восстановлены."
    ),
    description_en=(
        "**Purpose:** a customer returned goods — the warehouse "
        "needs a reverse document and physical receiving on the "
        "handheld so units land back on stock.\n\n"
        "**Problems solved:** the «Return» button on the completed "
        "order card creates the reverse document itself — no "
        "retyping numbers, lines or quantities; the terminal opens "
        "receiving for it immediately.\n\n"
        "**Result:** a return was created from the shipped order, "
        "both lines received back into bins, stock restored."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_return(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(TSD_VIEWPORT)
    await tsd_open(page, stock_ui)

    seed = await tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    bin_b = seed["bin_b"]
    product_1 = seed["product_1"]
    product_2 = seed["product_2"]
    uom_id = seed["uom_id"]
    await tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "5"},
            {"location_dest_id": bin_b["location_id"], "product_id": product_2["product_id"], "quantity": "6"},
        ],
    )
    transfer = await tsd_seed_document(
        page,
        warehouse_id,
        unique_id,
        [
            {
                "product_id": product_1["product_id"],
                "product_qty": "2",
                "uom_id": uom_id,
                "location_id": bin_a["location_id"],
            },
            {
                "product_id": product_2["product_id"],
                "product_qty": "3",
                "uom_id": uom_id,
                "location_id": bin_b["location_id"],
            },
        ],
    )
    # Отгрузка исполнена: документ «done» — физически товар уехал.
    await stock_rest(
        page,
        "POST",
        f"/transfers/{transfer['transfer_id']}/validate",
        {"transfer_id": transfer["transfer_id"]},
    )

    await tsd_pick_warehouse(page, unique_id)

    # --- Скан отгруженной накладной → карточка → «Возврат» ---
    await tsd_scan(page, f"DOC-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(transfer["name"], timeout=15_000)
    await scenario.step(
        "Отсканируйте исполненную накладную",
        page,
        screenshot_name="tsd-return-doc-card",
        label_en="Scan the completed order",
        details=(
            "Карточка исполненной накладной показывает кнопку "
            "«Возврат» — покупатель привёз товар обратно, и склад "
            "оформляет приём по тем же строкам."
        ),
        details_en=(
            "The completed order card shows a «Return» button — "
            "the customer brought goods back and the warehouse "
            "receives them along the same lines."
        ),
    )
    await sheet.locator(".action[data-action='return']").click()
    await expect(sheet).to_have_count(0, timeout=30_000)
    await scenario.step(
        "Нажмите «Возврат» — документ проведён",
        page,
        screenshot_name="tsd-return-created",
        label_en="Tap «Return» — the document is posted",
        details=(
            "Возврат — это факт, а не заявка: покупатель уже привёз "
            "товар, поэтому обратная накладная создаётся и проводится "
            "одним нажатием — строки и остатки откатываются сразу."
        ),
        details_en=(
            "A return is a fact, not a request: the customer already "
            "brought the goods, so the reverse order is created and "
            "posted with one tap — lines and stock roll back at once."
        ),
    )

    # --- Факт: обратная накладная проведена, остатки восстановлены ---
    transfers = await stock_rest(
        page, "GET", f"/transfers?warehouse_id={warehouse_id}"
    )
    returned = [t for t in transfers["items"] if t["return_of_id"] == transfer["transfer_id"]]
    assert len(returned) == 1
    ret = returned[0]
    assert ret["state"] == "done"
    assert ret["name"].endswith("/RET/00001")
    qty_1 = await stock_quant_qty(page, warehouse_id, product_1["product_id"], bin_a["location_id"])
    qty_2 = await stock_quant_qty(page, warehouse_id, product_2["product_id"], bin_b["location_id"])
    assert qty_1 == Decimal("5")
    assert qty_2 == Decimal("6")

    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Кофе зерновой {unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "Отсканируйте ячейку — остаток восстановлен",
        page,
        screenshot_name="tsd-return-bin-contents",
        label_en="Scan the bin — stock restored",
        details=(
            "**Демонстрация результата.** Ячейка показывает "
            "первоначальный остаток — возвращённые единицы легли "
            "обратно, возвратный документ проведён.\n\n"
            "**Итог.** Возврат оформляется с терминала в одно "
            "касание: скан накладной → «Возврат» — остатки "
            "совпадают с фактом."
        ),
        details_en=(
            "**Result demonstration.** The bin shows the original "
            "stock — returned units landed back, the return "
            "document is posted.\n\n"
            "**Summary.** A return is processed on the handheld "
            "in one tap: scan the order → «Return» — stock "
            "matches reality."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="tsd-document-pick",
    doc_slug="stock-tsd-fefo-pick",
    title="Отбор партий по FEFO: сначала то, что скорее испортится",
    title_en="FEFO lot picking: what expires sooner goes first",
    description=(
        "**Для чего:** на складе несколько партий одного товара с "
        "разными сроками — отгружать надо раньше испорченное, иначе "
        "свежая партия уйдёт, а старая сгниёт на полке.\n\n"
        "**Какие проблемы решает:** склад с FEFO-стратегией сам "
        "резервирует партию с ближайшим «годен до» — терминал "
        "ведёт оператора именно за ней, а не за удобной с верхней "
        "полки.\n\n"
        "**Результат:** из двух партий система зарезервировала и "
        "отобрала раннюю, остаток ранней уменьшился, поздняя цела."
    ),
    description_en=(
        "**Purpose:** the warehouse holds several lots of one "
        "product with different expirations — you must ship what "
        "spoils sooner, otherwise fresh stock leaves and the old "
        "lot rots on the shelf.\n\n"
        "**Problems solved:** a FEFO warehouse reserves the lot "
        "with the nearest «best before» itself — the terminal "
        "walks the operator to exactly that one, not whatever is "
        "handy on the top shelf.\n\n"
        "**Result:** of two lots the system reserved and picked "
        "the earlier one — its stock decreased, the later lot is "
        "untouched."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_doc_fefo_pick(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(TSD_VIEWPORT)
    await tsd_open(page, stock_ui)

    # --- Склад с FEFO-стратегией отбора ---
    warehouse = await stock_rest(
        page, "POST", "/warehouses",
        {
            "code": f"F-{unique_id[:8].upper()}",
            "name": f"FEFO-склад {unique_id[:4]}",
            "removal_strategy": "fefo",
        },
    )
    warehouse_id = warehouse["warehouse_id"]
    zone = await stock_rest(
        page, "POST", "/locations",
        {
            "warehouse_id": warehouse_id,
            "name": f"Зона {unique_id[:4]}",
            "usage": "view",
        },
    )
    bin_a = await stock_rest(
        page, "POST", "/locations",
        {
            "warehouse_id": warehouse_id,
            "parent_id": zone["location_id"],
            "name": f"Ячейка А{unique_id[:3]}",
            "usage": "bin",
            "barcode": f"BIN-A-{unique_id[:6]}",
        },
    )
    uoms = await stock_rest(page, "GET", "/uoms")
    uom_id = next(u["uom_id"] for u in uoms["items"] if u["name"] == "Units")
    product = await stock_rest(
        page, "POST", "/products",
        {
            "name": f"Йогурт {unique_id[:4]}",
            "sku": f"YOG-{unique_id[:6]}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "standard_price": "0",
            "tracking": "lot",
            "is_storable": True,
            "barcodes": [f"BC-Y-{unique_id[:6]}"],
        },
    )
    await tsd_seed_product_image(
        page, str(product["product_id"]), color="#d94a7a", label="ЙОГ"
    )
    # Две партии в одной ячейке: ранняя «годна до +10», поздняя «+60» —
    # лежат через adhoc-коммит с партией и сроком на строках.
    await stock_rest(
        page, "POST", "/scan/adhoc-commit",
        {
            "warehouse_id": warehouse_id,
            "operation_code": "incoming",
            "context": {
                "flow": "receive",
                "step": "review",
                "lines": [
                    {
                        "location_id": None,
                        "location_dest_id": bin_a["location_id"],
                        "product_id": product["product_id"],
                        "quantity": "4",
                        "lot_name": f"LOT-OLD-{unique_id[:6]}",
                        "expiration_date": _expiry(10),
                    },
                    {
                        "location_id": None,
                        "location_dest_id": bin_a["location_id"],
                        "product_id": product["product_id"],
                        "quantity": "6",
                        "lot_name": f"LOT-NEW-{unique_id[:6]}",
                        "expiration_date": _expiry(60),
                    },
                ],
            },
        },
    )
    # Отгрузка на 2 шт: FEFO обязан зарезервировать LOT-OLD.
    transfer = await tsd_seed_document(
        page,
        warehouse_id,
        unique_id,
        [
            {
                "product_id": product["product_id"],
                "product_qty": "2",
                "uom_id": uom_id,
                "location_id": bin_a["location_id"],
            },
        ],
    )
    lines = await stock_rest(
        page, "POST", "/move-lines/queue", {"warehouse_id": warehouse_id, "limit": 50}
    )
    line = next(l for l in lines["items"] if l["product_id"] == product["product_id"])
    lots = await stock_rest(page, "GET", f"/lots?product_id={product['product_id']}")
    lot_old = next(l for l in lots["items"] if l["name"] == f"LOT-OLD-{unique_id[:6]}")
    assert line["lot_id"] == lot_old["lot_id"], (
        f"FEFO должен взять раннюю партию: {line} vs {lots}"
    )

    # --- Выбор FEFO-склада: код `F-`, общий хелпер смотрит `0-` ---
    await page.reload(wait_until="domcontentloaded")
    await expect(page.locator("stock-tsd-home-page")).to_be_visible(timeout=30_000)
    await tsd_wait_ws_open(page)
    card = page.locator(
        "stock-tsd-home-page .warehouse-card",
        has_text=f"F-{unique_id[:8].upper()}",
    )
    await expect(card).to_be_visible(timeout=30_000)
    await card.click()

    # --- Исполнение: терминал ведёт за ранней партией ---
    await tsd_scan(page, f"DOC-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator("button.action").click()
    await expect(sheet).to_have_count(0, timeout=35_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)
    expected = run.locator(".expected")
    await expect(expected).to_be_visible(timeout=15_000)
    await scenario.step(
        "Подсказка ведёт за партией с ближайшим сроком",
        page,
        screenshot_name="tsd-fefo-expected",
        label_en="The hint points to the earliest-expiry lot",
        details=(
            "Строка документа уже зарезервировала раннюю партию — "
            "подсказка ведёт к её ячейке. Оператору не нужно "
            "сравнивать даты на этикетках: выбор сделала стратегия "
            "склада."
        ),
        details_en=(
            "The document line already reserved the earlier lot — "
            "the hint points to its bin. The operator does not "
            "compare label dates: the warehouse strategy made the "
            "choice."
        ),
    )
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await tsd_scan(page, f"BC-Y-{unique_id[:6]}")
    # Партийный товар на отборе: подтверждаем зарезервированную партию
    # номером с этикетки — терминал просит её тем же полем, что на
    # приёмке, и резерв сойдётся только с правильной партией.
    lot_panel = run.locator(".lot-panel")
    await expect(lot_panel).to_be_visible(timeout=15_000)
    await tsd_set_platform_field(
        lot_panel.locator("platform-field.lot-input").first, f"LOT-OLD-{unique_id[:6]}"
    )
    await lot_panel.locator(".lot-ok").click()
    numpad = run.locator(".qty-panel .numpad")
    await expect(numpad).to_be_visible(timeout=15_000)
    await tsd_qty(page, "2")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await tsd_commit(page)

    # --- Факт: списалась ранняя партия, поздняя цела ---
    quants = await stock_rest(
        page,
        "GET",
        f"/quants?warehouse_id={warehouse_id}&product_id={product['product_id']}",
    )
    lot_new = next(l for l in lots["items"] if l["name"] == f"LOT-NEW-{unique_id[:6]}")
    by_lot = {q["lot_id"]: Decimal(str(q["quantity"])) for q in quants["items"]}
    assert by_lot.get(lot_old["lot_id"]) == Decimal("2"), by_lot
    assert by_lot.get(lot_new["lot_id"]) == Decimal("6"), by_lot

    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Йогурт {unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "Отсканируйте ячейку — списана именно ранняя партия",
        page,
        screenshot_name="tsd-fefo-bin-contents",
        label_en="Scan the bin — the earlier lot was taken",
        details=(
            "**Демонстрация результата.** Остаток ячейки «8»: из 10 "
            "штук списаны 2 именно партии «годен до +10 дней» — "
            "проверить можно в разделе «Партии» на компьютере, где "
            "каждая партия показывает свой срок.\n\n"
            "**Итог.** На FEFO-складе партии с ближайшим сроком "
            "уходят первыми автоматически — оператору остаётся "
            "сканировать то, куда ведёт терминал."
        ),
        details_en=(
            "**Result demonstration.** Bin stock is «8»: of 10 "
            "units, 2 were taken exactly from the «best before +10 "
            "days» lot — checkable in «Lots» on the desktop where "
            "each lot shows its date.\n\n"
            "**Summary.** On a FEFO warehouse the nearest-expiry "
            "lots leave first automatically — the operator just "
            "scans where the terminal leads."
        ),
    )
