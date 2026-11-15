"""Документационный сценарий Stock TSD: терминал оператора `/stock/tsd`.

Физический маршрут приёмки: выбор склада → скан товара → карточка с
остатками → «Принять» → скан ячейки → количество → проводка. Сканы
идут по нативному каналу `stock/tsd:native_scan` — тому же контракту,
что аппаратный сканер и DataWedge-мост Capacitor-оболочки.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.stock_e2e_helpers import (
    TSD_VIEWPORT,
    stock_quant_qty,
    stock_quant_row,
    stock_rest,
    tsd_commit,
    tsd_commit_click,
    tsd_open,
    tsd_pick_warehouse,
    tsd_qty,
    tsd_scan,
    tsd_seed_document,
    tsd_seed_product_image,
    tsd_seed_stock,
    tsd_seed_warehouse,
    tsd_wait_step,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="stock",
    tag="tsd-receive",
    doc_slug="stock-tsd-receive",
    title="Приёмка на терминале: скан товара, ячейки и проводка",
    title_en="Receiving on the handheld: product scan, bin scan, commit",
    description=(
        "**Для чего:** повседневная работа оператора склада — принять "
        "поставку на ТСД/телефоне без компьютера и бумажных накладных.\n\n"
        "**Какие проблемы решает:** терминал сам ведёт по шагам — что "
        "сканировать дальше подсказывает экран; скан любого товара "
        "показывает его карточку с остатками и действиями.\n\n"
        "**Результат:** два товара приняты в ячейки склада, остатки "
        "видны прямо на терминале."
    ),
    description_en=(
        "**Purpose:** daily warehouse operator work — receive a "
        "delivery on a handheld or phone without a desktop or paper "
        "documents.\n\n"
        "**Problems solved:** the terminal guides the operator — the "
        "screen tells what to scan next; scanning any product opens "
        "its card with stock and actions.\n\n"
        "**Result:** two products received into warehouse bins, "
        "stock visible right on the terminal."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_receive(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(TSD_VIEWPORT)
    await tsd_open(page, stock_ui)

    # --- Набор данных через REST-зеркала op'ов (у ТСД нет фабрик справочников) ---
    seed = await tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    bin_b = seed["bin_b"]
    product_1 = seed["product_1"]
    product_2 = seed["product_2"]

    # --- Выбор склада ---
    card = page.locator(
        "stock-tsd-home-page .warehouse-card",
        has_text=f"Склад {unique_id[:4]}",
    )
    await expect(card).to_be_visible(timeout=30_000)
    await scenario.step(
        "Выберите склад на терминале",
        page,
        screenshot_name="tsd-warehouse-pick",
        label_en="Pick the warehouse on the handheld",
        details=(
            "Терминал открывается списком складов компании — оператор "
            "выбирает свой один раз за смену. Крупные карточки удобно "
            "жать в перчатках."
        ),
        details_en=(
            "The terminal opens with a company warehouse list — the "
            "operator picks theirs once per shift. Large cards are "
            "easy to tap with gloves on."
        ),
    )
    await card.click()

    # --- Скан товара вне сессии: карточка сущности ---
    await tsd_scan(page, f"BC-1-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Кофе зерновой {unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "Отсканируйте товар — откроется его карточка",
        page,
        screenshot_name="tsd-product-card",
        label_en="Scan a product — its card opens",
        details=(
            "Скан любого штрихкода на рабочем столе открывает карточку "
            "сущности: у товара — название, фото и остатки по ячейкам "
            "(подгружаются асинхронно), у ячейки — содержимое, у накладной "
            "— вход в исполнение. Из карточки товара доступны действия: "
            "принять, переместить, посчитать."
        ),
        details_en=(
            "Scanning any barcode on the work screen opens an entity "
            "card: a product shows name, photo and per-bin stock "
            "(loaded asynchronously), a bin shows its contents, a "
            "document opens execution. Product card actions: receive, "
            "move, count."
        ),
    )

    # --- Приёмка товара 1: карточка → поток → ячейка → количество ---
    await sheet.locator(".action[data-action='receive']").click()
    # Лист уходит с анимацией — ждём демонтажа, чтобы не перехватывал клики.
    await expect(sheet).to_have_count(0, timeout=15_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)
    # Товар уже отсканирован — машина ждёт ячейку-приёмник.
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await expect(run.locator(".qty-panel")).to_be_visible(timeout=15_000)
    await tsd_qty(page, "5")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    # Строка исполнения: товар резолвится в имя, не в сырой id.
    line_row = run.locator(".line-row").first
    await expect(line_row).to_contain_text(
        f"Кофе зерновой {unique_id[:4]}", timeout=10_000
    )
    await scenario.step(
        "Приёмка: скан ячейки и количества",
        page,
        screenshot_name="tsd-receive-review",
        label_en="Receiving: bin and quantity scans",
        details=(
            "«Принять» из карточки товара стартует сессию приёмки — "
            "товар уже подставлен, терминал просит ячейку. Скан ячейки, "
            "количество на экранной клавиатуре — строка готова к проводке."
        ),
        details_en=(
            "«Receive» from the product card starts a receiving session — "
            "the product is already filled in, the terminal asks for a "
            "bin. Scan the bin, enter quantity on the numpad — the line "
            "is ready to commit."
        ),
    )
    await tsd_commit(page)

    # --- Приёмка товара 2 в другую ячейку тем же маршрутом ---
    await tsd_scan(page, f"BC-2-{unique_id[:6]}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator(".action[data-action='receive']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    await expect(run).to_be_visible(timeout=15_000)
    await tsd_scan(page, f"BIN-B-{unique_id[:6]}")
    await expect(run.locator(".qty-panel")).to_be_visible(timeout=15_000)
    await tsd_qty(page, "12")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await tsd_commit(page)

    # --- Проводки проверяем леджером, не глазами ---
    qty_1 = await stock_quant_qty(page, warehouse_id, product_1["product_id"], bin_a["location_id"])
    qty_2 = await stock_quant_qty(page, warehouse_id, product_2["product_id"], bin_b["location_id"])
    assert qty_1 == Decimal("5")
    assert qty_2 == Decimal("12")

    # --- Скан ячейки: содержимое с остатками обоих приёмок ---
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Ячейка А{unique_id[:3]}", timeout=15_000)
    await expect(sheet).to_contain_text(f"Кофе зерновой {unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "Отсканируйте ячейку — видно её содержимое",
        page,
        screenshot_name="tsd-bin-contents",
        label_en="Scan a bin — see its contents",
        details=(
            "**Демонстрация результата.** Скан ячейки показывает "
            "физическое содержимое: товары и количества, только что "
            "принятые терминалом. Отсюда же — перемещение и инвентаризация "
            "ячейки в один жест.\n\n"
            "**Итог.** Приёмка на терминале: скан товара → «Принять» → "
            "скан ячейки → количество → проводка; остатки видны сразу "
            "в карточке ячейки."
        ),
        details_en=(
            "**Result demonstration.** Scanning a bin shows its physical "
            "contents: products and quantities just received on the "
            "terminal. From here — moving and counting the bin in one "
            "tap.\n\n"
            "**Summary.** Receiving on the handheld: scan product → "
            "«Receive» → scan bin → quantity → commit; stock is "
            "immediately visible in the bin card."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="tsd-move",
    doc_slug="stock-tsd-move",
    title="Перемещение на терминале: товар из ячейки в ячейку",
    title_en="Moving stock on the handheld: bin to bin",
    description=(
        "**Для чего:** переборка и пополнение — оператор переносит "
        "товар между ячейками прямо у стеллажа, без журнала и "
        "компьютера.\n\n"
        "**Какие проблемы решает:** терминал ведёт по маршруту "
        "«источник → приёмник → количество», остатки на карточке "
        "товара видны до начала переноса.\n\n"
        "**Результат:** два товара частично перемещены из ячейки А "
        "в ячейку Б, остатки обновлены мгновенно."
    ),
    description_en=(
        "**Purpose:** replenishment and re-slotting — the operator "
        "moves stock between bins right at the rack, no desktop or "
        "paper trail.\n\n"
        "**Problems solved:** the terminal walks the route "
        "«source → destination → quantity»; the product card shows "
        "current per-bin stock before the move starts.\n\n"
        "**Result:** two products partially moved from bin A to bin "
        "B, stock updated instantly."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_move(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(TSD_VIEWPORT)
    await tsd_open(page, stock_ui)

    # --- Топология и остаток на ячейке А ---
    seed = await tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    bin_b = seed["bin_b"]
    product_1 = seed["product_1"]
    product_2 = seed["product_2"]
    await tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "5"},
            {"location_dest_id": bin_a["location_id"], "product_id": product_2["product_id"], "quantity": "8"},
        ],
    )

    await tsd_pick_warehouse(page, unique_id)

    # --- Скан товара: карточка показывает, где он лежит ---
    await tsd_scan(page, f"BC-1-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Кофе зерновой {unique_id[:4]}", timeout=15_000)
    # Остатки грузятся асинхронно — строка «ячейка × количество».
    await expect(sheet).to_contain_text(f"Ячейка А{unique_id[:3]}", timeout=15_000)
    await scenario.step(
        "Отсканируйте товар — видно, где он лежит",
        page,
        screenshot_name="tsd-move-card",
        label_en="Scan a product — see where it sits",
        details=(
            "Карточка товара сразу отвечает на вопрос «где брать»: "
            "строки остатков «ячейка → количество» подгружаются "
            "асинхронно, не блокируя сканер. Кнопка «Переместить» "
            "стартует перенос — товар уже подставлен в строку."
        ),
        details_en=(
            "The product card answers «where to pick from» instantly: "
            "per-bin stock rows load asynchronously without blocking "
            "the scanner. «Move» starts a relocation — the product is "
            "already in the line."
        ),
    )

    # --- Перенос 1: источник А → приёмник Б → количество ---
    await sheet.locator(".action[data-action='move']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)
    # Машина ждёт источник: оператор сканирует ячейку, из которой берёт.
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await tsd_wait_step(page, "dest")
    await tsd_scan(page, f"BIN-B-{unique_id[:6]}")
    await expect(run.locator(".qty-panel")).to_be_visible(timeout=15_000)
    await tsd_qty(page, "2")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await scenario.step(
        "Источник → приёмник → количество → проводка",
        page,
        screenshot_name="tsd-move-review",
        label_en="Source → destination → quantity → commit",
        details=(
            "Маршрут переноса — два скана ячеек и цифра: терминал "
            "проверяет, что обе ячейки принадлежат складу сессии и "
            "хранят остаток. Строка review показывает направление "
            "«источник → приёмник» и количество."
        ),
        details_en=(
            "The move route is two bin scans and a digit: the terminal "
            "verifies both bins belong to the session warehouse and "
            "hold stock. The review line shows the «source → "
            "destination» route and quantity."
        ),
    )
    await tsd_commit(page)

    # --- Перенос 2 тем же маршрутом ---
    await tsd_scan(page, f"BC-2-{unique_id[:6]}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator(".action[data-action='move']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    await expect(run).to_be_visible(timeout=15_000)
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await tsd_wait_step(page, "dest")
    await tsd_scan(page, f"BIN-B-{unique_id[:6]}")
    await expect(run.locator(".qty-panel")).to_be_visible(timeout=15_000)
    await tsd_qty(page, "3")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await tsd_commit(page)

    # --- Остатки после двух переносов ---
    assert await stock_quant_qty(page, warehouse_id, product_1["product_id"], bin_a["location_id"]) == Decimal("3")
    assert await stock_quant_qty(page, warehouse_id, product_2["product_id"], bin_a["location_id"]) == Decimal("5")
    assert await stock_quant_qty(page, warehouse_id, product_1["product_id"], bin_b["location_id"]) == Decimal("2")
    assert await stock_quant_qty(page, warehouse_id, product_2["product_id"], bin_b["location_id"]) == Decimal("3")

    # --- Скан ячейки Б: оба перенесённых товара на месте ---
    await tsd_scan(page, f"BIN-B-{unique_id[:6]}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Кофе зерновой {unique_id[:4]}", timeout=15_000)
    await expect(sheet).to_contain_text(f"Чай листовой {unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "Отсканируйте ячейку-приёмник — товар на месте",
        page,
        screenshot_name="tsd-move-bin-b",
        label_en="Scan the destination bin — stock is there",
        details=(
            "**Демонстрация результата.** Ячейка Б показывает оба "
            "перенесённых товара с новыми остатками — перемещение "
            "прошло по леджеру, а не только на экране.\n\n"
            "**Итог.** Перенос на терминале: скан товара → «Переместить» "
            "→ источник → приёмник → количество → проводка."
        ),
        details_en=(
            "**Result demonstration.** Bin B shows both moved products "
            "with new quantities — the move hit the ledger, not just "
            "the screen.\n\n"
            "**Summary.** Moving on the handheld: scan product → "
            "«Move» → source → destination → quantity → commit."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="tsd-count",
    doc_slug="stock-tsd-count",
    title="Пересчёт ячейки на терминале: факт против остатка",
    title_en="Cycle counting a bin on the handheld",
    description=(
        "**Для чего:** циклический пересчёт — оператор пересчитывает "
        "физический остаток ячейки, система фиксирует факт для "
        "сверки с учётным.\n\n"
        "**Какие проблемы решает:** один скан ячейки открывает "
        "пересчёт — товары набираются подряд в одну сессию, расхождение "
        "фиксируется для утверждения.\n\n"
        "**Результат:** два товара пересчитаны с отклонениями, факт "
        "записан на остатки ячейки."
    ),
    description_en=(
        "**Purpose:** cycle counting — the operator recounts a bin's "
        "physical stock; the system records the counted fact for "
        "reconciliation against book stock.\n\n"
        "**Problems solved:** one bin scan opens the count — products "
        "are entered one after another in a single session, variance "
        "is recorded for approval.\n\n"
        "**Result:** two products counted with variances, the counted "
        "fact is written onto the bin's stock."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_count(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(TSD_VIEWPORT)
    await tsd_open(page, stock_ui)

    # --- Топология и остаток на ячейке А ---
    seed = await tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    product_1 = seed["product_1"]
    product_2 = seed["product_2"]
    await tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "5"},
            {"location_dest_id": bin_a["location_id"], "product_id": product_2["product_id"], "quantity": "8"},
        ],
    )

    await tsd_pick_warehouse(page, unique_id)

    # --- Скан ячейки: карточка с содержимым и действием «Посчитать» ---
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Кофе зерновой {unique_id[:4]}", timeout=15_000)
    await expect(sheet).to_contain_text(f"Чай листовой {unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "Отсканируйте ячейку — учётное содержимое",
        page,
        screenshot_name="tsd-count-sheet",
        label_en="Scan a bin — book contents",
        details=(
            "Карточка ячейки показывает учётный остаток: «Кофе» — 5, "
            "«Чай» — 8. Кнопка «Посчитать» стартует цикл-пересчёт — "
            "ячейка уже подставлена как источник, осталось набирать "
            "товары подряд."
        ),
        details_en=(
            "The bin card shows book stock: «Coffee» — 5, «Tea» — 8. "
            "«Count» starts a cycle count — the bin is already the "
            "source; just scan products one after another."
        ),
    )

    # --- Пересчёт: товар 1 факт 4 (минус 1), товар 2 факт 7 (минус 1) ---
    await sheet.locator(".action[data-action='count']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)
    await tsd_scan(page, f"BC-1-{unique_id[:6]}")
    await expect(run.locator(".qty-panel")).to_be_visible(timeout=15_000)
    await tsd_qty(page, "4")
    # После первой строки машина снова ждёт товар — ячейка удержана.
    await tsd_wait_step(page, "review")
    await tsd_scan(page, f"BC-2-{unique_id[:6]}")
    await tsd_wait_step(page, "quantity")
    await tsd_qty(page, "7")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await expect(run.locator(".line-row")).to_have_count(2, timeout=15_000)
    await scenario.step(
        "Пересчитайте товары подряд — строки в одну проводку",
        page,
        screenshot_name="tsd-count-review",
        label_en="Count products in a row — one commit",
        details=(
            "Пересчёт идёт потоком: скан товара → фактическое "
            "количество → следующий товар. Ячейка удерживается между "
            "строками — пересканировать её не нужно. Review показывает "
            "обе строки перед проводкой."
        ),
        details_en=(
            "Counting is a flow: scan product → counted quantity → "
            "next product. The bin stays between lines — no need to "
            "rescan it. Review shows both lines before commit."
        ),
    )
    await tsd_commit(page)

    # --- Факт пересчёта записан на остатки (дельта уходит на утверждение) ---
    row_1 = await stock_quant_row(page, warehouse_id, product_1["product_id"], bin_a["location_id"])
    row_2 = await stock_quant_row(page, warehouse_id, product_2["product_id"], bin_a["location_id"])
    assert Decimal(str(row_1["inventory_quantity"])) == Decimal("4")
    assert Decimal(str(row_2["inventory_quantity"])) == Decimal("7")


@pytest.mark.scenario(
    service="stock",
    tag="tsd-container-move",
    doc_slug="stock-tsd-container-move",
    title="Перевоз тары на терминале: паллета вместе с товаром",
    title_en="Moving a container on the handheld: pallet and all",
    description=(
        "**Для чего:** перевозка паллеты/короба целиком — содержимое "
        "едет вместе с тарой, разбирать и пересканировать каждый "
        "товар не нужно.\n\n"
        "**Какие проблемы решает:** один скан тары показывает её "
        "содержимое; перемещение — скан целевой ячейки, товар внутри "
        "остаётся привязан к таре.\n\n"
        "**Результат:** паллета с товаром переподвешена под новую "
        "ячейку — в системе и физически одна операция."
    ),
    description_en=(
        "**Purpose:** relocating a pallet/box as a unit — its contents "
        "travel with it, no unpacking or re-scanning every item.\n\n"
        "**Problems solved:** one container scan shows its contents; "
        "moving it takes a single destination scan — stock inside "
        "stays bound to the container.\n\n"
        "**Result:** a loaded pallet is re-hung under a new bin — one "
        "operation in the system and on the floor."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_container_move(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(TSD_VIEWPORT)
    await tsd_open(page, stock_ui)

    # --- Топология + паллета с остатком внутри ---
    seed = await tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    bin_b = seed["bin_b"]
    product_1 = seed["product_1"]
    # Паллета стоит в ячейке А: дети допустимы только под view/container/bin.
    pallet_type = await stock_rest(
        page, "POST", "/container-types",
        {
            "warehouse_id": warehouse_id,
            "name": f"Европаллета {unique_id[:4]}",
            "kind": "pallet",
        },
    )
    pallet = await stock_rest(
        page, "POST", "/containers",
        {
            "warehouse_id": warehouse_id,
            "parent_location_id": bin_a["location_id"],
            "container_type_id": pallet_type["container_type_id"],
            "name": f"Паллета {unique_id[:4]}",
            "barcode": f"PLT-{unique_id[:6]}",
        },
    )
    await tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": pallet["location_id"], "product_id": product_1["product_id"], "quantity": "10"},
        ],
    )

    await tsd_pick_warehouse(page, unique_id)

    # --- Скан паллеты: карточка тары с содержимым ---
    await tsd_scan(page, f"PLT-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Паллета {unique_id[:4]}", timeout=15_000)
    await expect(sheet).to_contain_text(f"Кофе зерновой {unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "Отсканируйте паллету — видно её груз",
        page,
        screenshot_name="tsd-container-card",
        label_en="Scan a pallet — see its load",
        details=(
            "Тара — тоже локация: карточка паллеты показывает товар "
            "внутри неё. «Переместить» перевезёт паллету целиком — "
            "строки набирать не нужно."
        ),
        details_en=(
            "A container is a location too: the pallet card shows the "
            "stock inside. «Move» relocates the whole pallet — no "
            "lines to enter."
        ),
    )

    # --- Перевоз: скан целевой ячейки → проводка ---
    await sheet.locator(".action[data-action='container_move']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)
    await tsd_scan(page, f"BIN-B-{unique_id[:6]}")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await tsd_commit(page)

    # --- Паллета переподвешена под ячейку Б, остаток поехал с ней ---
    locations = await stock_rest(page, "GET", "/locations", )
    moved = next(
        loc for loc in locations["items"]
        if loc["location_id"] == pallet["location_id"]
    )
    assert moved["parent_id"] == bin_b["location_id"]
    assert await stock_quant_qty(page, warehouse_id, product_1["product_id"], pallet["location_id"]) == Decimal("10")
    await scenario.step(
        "Паллета под новой ячейкой — груз на месте",
        page,
        screenshot_name="tsd-container-moved",
        label_en="Pallet under the new bin — load intact",
        details=(
            "**Демонстрация результата.** Паллета переподвесилась под "
            "ячейку Б одной операцией — остаток остался привязан к "
            "таре, ничего «разбирать» не пришлось.\n\n"
            "**Итог.** Перевоз тары: скан паллеты → «Переместить» → "
            "скан целевой ячейки → проводка."
        ),
        details_en=(
            "**Result demonstration.** The pallet was re-hung under "
            "bin B in one operation — stock stayed bound to the "
            "container, nothing had to be «unpacked».\n\n"
            "**Summary.** Moving a container: scan pallet → «Move» → "
            "scan destination bin → commit."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="tsd-document-pick",
    doc_slug="stock-tsd-document-pick",
    title="Работа по накладной: скан документа ведёт по позициям",
    title_en="Working a delivery order: document scan drives the lines",
    description=(
        "**Для чего:** исполнение складского документа — оператор "
        "сканирует штрихкод накладной на отгрузку, терминал сам "
        "выбирает поток и подсказывает каждую позицию.\n\n"
        "**Какие проблемы решает:** экран подстраивается под "
        "документ — backend выбирает поток «сборка» по типу операции "
        "и показывает подсказку «ячейка → товар × количество» из "
        "первой исполнимой строки; оператору не нужно знать состав "
        "накладной наизусть.\n\n"
        "**Результат:** обе позиции накладной собраны и проведены, "
        "остатки ячейки уменьшены по леджеру."
    ),
    description_en=(
        "**Purpose:** executing a warehouse document — the operator "
        "scans the delivery order barcode; the terminal picks the "
        "flow itself and suggests every line.\n\n"
        "**Problems solved:** the screen adapts to the document — "
        "the backend chooses the «pick» flow from the operation "
        "type and shows a «bin → product × qty» hint from the first "
        "executable line; the operator needs no printout.\n\n"
        "**Result:** both order lines picked and committed, bin "
        "stock reduced in the ledger."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_document_pick(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(TSD_VIEWPORT)
    await tsd_open(page, stock_ui)

    # --- Топология, остаток и накладная на отгрузку с баркодом ---
    seed = await tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    product_1 = seed["product_1"]
    product_2 = seed["product_2"]
    uom_id = seed["uom_id"]
    await tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "5"},
            {"location_dest_id": bin_a["location_id"], "product_id": product_2["product_id"], "quantity": "8"},
        ],
    )
    op_types = await stock_rest(
        page, "GET", f"/operation-types?warehouse_id={warehouse_id}"
    )
    outgoing_id = next(
        ot["operation_type_id"] for ot in op_types["items"] if ot["code"] == "outgoing"
    )
    transfer = await stock_rest(
        page, "POST", "/transfers",
        {
            "warehouse_id": warehouse_id,
            "operation_type_id": outgoing_id,
            "barcode": f"DOC-{unique_id[:6]}",
            "moves": [
                {
                    "product_id": product_1["product_id"],
                    "product_qty": "5",
                    "uom_id": uom_id,
                    "location_id": bin_a["location_id"],
                },
                {
                    "product_id": product_2["product_id"],
                    "product_qty": "6",
                    "uom_id": uom_id,
                    "location_id": bin_a["location_id"],
                },
            ],
        },
    )
    await stock_rest(page, "POST", f"/transfers/{transfer['transfer_id']}/confirm")
    await stock_rest(page, "POST", f"/transfers/{transfer['transfer_id']}/assign")

    await tsd_pick_warehouse(page, unique_id)

    # --- Рабочий стол: обе строки накладной видны как свободные задания ---
    await expect(page.locator(".task-card").first).to_be_visible(timeout=15_000)
    await scenario.step(
        "Очередь — свободные задания можно взять руками",
        page,
        screenshot_name="tsd-document-queue",
        label_en="Queue — free tasks can be picked manually",
        details=(
            "Рабочий стол: «дайте работу» выдаёт лучшее задание "
            "автоматически, а очередь ниже показывает все исполнимые "
            "строки — оператор физически ближе к другой ячейке и "
            "может тапнуть её сам. Кнопка «отпустить» есть только у "
            "закреплённых за ним строк — у свободных отпускать "
            "нечего."
        ),
        details_en=(
            "The work desk: «give me work» issues the best task "
            "automatically, while the queue below lists every "
            "executable line — the operator may be physically "
            "closer to another bin and can tap it themselves. The "
            "release button appears only on lines claimed by them — "
            "free lines have nothing to release."
        ),
    )

    # --- Скан накладной: карточка документа и вход в исполнение ---
    await tsd_scan(page, f"DOC-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(transfer["name"], timeout=15_000)
    await scenario.step(
        "Отсканируйте накладную — карточка документа",
        page,
        screenshot_name="tsd-document-card",
        label_en="Scan the order — document card",
        details=(
            "Штрихкод накладной резолвится в документ: карточка "
            "показывает номер и число позиций. «Начать исполнение» "
            "открывает сессию — backend сам выбирает поток по типу "
            "операции (отгрузка → сборка)."
        ),
        details_en=(
            "The order barcode resolves to a document: the card shows "
            "the number and line count. «Start execution» opens a "
            "session — the backend picks the flow itself from the "
            "operation type (outgoing → picking)."
        ),
    )

    # --- Исполнение позиции 1: подсказка → ячейка → товар → количество ---
    await sheet.locator("button.action").click()
    # scan_open с повтором: 2×15s бюджета операции под параллельным
    # прогоном — оператор физически ждёт, пока терминал отвечает.
    await expect(sheet).to_have_count(0, timeout=35_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)
    # Подсказка backend'а: первая исполнимая строка — кофе ×4 из ячейки А.
    expected = run.locator(".expected")
    await expect(expected).to_be_visible(timeout=15_000)
    await expect(expected).to_contain_text(f"Кофе зерновой {unique_id[:4]}", timeout=10_000)
    await expect(expected).to_contain_text(f"Ячейка А{unique_id[:3]}", timeout=10_000)
    await scenario.step(
        "Терминал подсказывает первую позицию накладной",
        page,
        screenshot_name="tsd-document-expected",
        label_en="The terminal suggests the first order line",
        details=(
            "Поток «сборка» выбран backend'ом: жёлтая полоса — "
            "подсказка из открытой строки документа «ячейка → товар "
            "× количество». Оператор идёт к указанной ячейке и "
            "сканирует её — пересканировать накладную не нужно."
        ),
        details_en=(
            "The «pick» flow was chosen by the backend: the amber "
            "strip is a hint from the open document line «bin → "
            "product × qty». The operator walks to that bin and "
            "scans it — no need to rescan the document."
        ),
    )
    # --- Перезагрузка терминала внутри сессии: поток и подсказка
    # восстанавливаются из persisted-снапшота — оператор не теряет
    # прогон при обновлении страницы/свапе WebView ---
    _ = await page.reload(wait_until="domcontentloaded")
    await expect(run).to_be_visible(timeout=30_000)
    await expect(expected).to_contain_text(f"Кофе зерновой {unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "Перезагрузка терминала — сессия и подсказка на месте",
        page,
        screenshot_name="tsd-document-reload",
        label_en="Terminal reload — session and hint restored",
        details=(
            "Терминал перезагрузили посреди исполнения — сессия "
            "восстановилась из хранилища: экран прогона и жёлтая "
            "подсказка backend'а на месте, набранное не потеряно. "
            "Оператор просто продолжает сканировать."
        ),
        details_en=(
            "The terminal was reloaded mid-execution — the session "
            "restored from storage: the run screen and the amber "
            "backend hint are in place, nothing collected is lost. "
            "The operator simply keeps scanning."
        ),
    )

    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await tsd_wait_step(page, "product")
    await tsd_scan(page, f"BC-1-{unique_id[:6]}")
    await tsd_wait_step(page, "quantity")
    await tsd_qty(page, "4")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await tsd_commit_click(page)

    # --- Позиция не выбрана целиком: backend продолжает документ —
    # экран остаётся в сессии и подсказывает остаток той же строки ---
    await expect(expected).to_contain_text("×1", timeout=15_000)
    await scenario.step(
        "Коммит части позиции — терминал предлагает добрать остаток",
        page,
        screenshot_name="tsd-document-continuation",
        label_en="Partial commit — the terminal suggests the remainder",
        details=(
            "По документу 5 шт, оператор унёс 4: после проводки "
            "сессия НЕ закрывается — backend подсказывает следующую "
            "исполнимую строку (остаток ×1 той же позиции). Оператор "
            "не возвращается в очередь между ходками к одной ячейке."
        ),
        details_en=(
            "The document wants 5, the operator carried 4: after "
            "the commit the session does NOT close — the backend "
            "suggests the next executable line (the ×1 remainder "
            "of the same position). No queue round-trip between "
            "trips to the same bin."
        ),
    )
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await tsd_wait_step(page, "product")
    await tsd_scan(page, f"BC-1-{unique_id[:6]}")
    await tsd_wait_step(page, "quantity")
    await tsd_qty(page, "1")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await tsd_commit_click(page)

    # --- Позиция 2: backend сам продолжает документ — повторный скан
    # накладной не нужен, следующая исполнимая строка уже на экране ---
    await expect(run).to_be_visible(timeout=15_000)
    expected_2 = run.locator(".expected")
    await expect(expected_2).to_contain_text(f"Чай листовой {unique_id[:4]}", timeout=15_000)
    await tsd_wait_step(page, "start")
    await scenario.step(
        "Документ продолжается — следующая позиция уже предложена",
        page,
        screenshot_name="tsd-document-next-line",
        label_en="The document continues — the next line is suggested",
        details=(
            "Строка кофе закрыта, а накладная — нет: терминал сам "
            "переводит оператора на следующую исполнимую позицию "
            "документа (чай), без возврата в очередь и повторного "
            "скана накладной. Оператор просто идёт дальше."
        ),
        details_en=(
            "The coffee line is done but the order is not: the "
            "terminal moves the operator straight to the next "
            "executable line (tea) — no queue round-trip and no "
            "re-scan of the order. The operator simply walks on."
        ),
    )
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await tsd_wait_step(page, "product")
    await tsd_scan(page, f"BC-2-{unique_id[:6]}")
    await tsd_wait_step(page, "quantity")
    await tsd_qty(page, "6")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await tsd_commit(page)

    # --- Обе позиции проведены: остаток ячейки уменьшен по леджеру ---
    assert await stock_quant_qty(page, warehouse_id, product_1["product_id"], bin_a["location_id"]) == Decimal("0")
    assert await stock_quant_qty(page, warehouse_id, product_2["product_id"], bin_a["location_id"]) == Decimal("2")
    moves = await stock_rest(
        page, "GET", f"/transfers/{transfer['transfer_id']}"
    )
    assert all(m["state"] == "done" for m in moves["moves"]), moves["moves"]

    await scenario.step(
        "Накладная закрыта — остатки сошлись с документом",
        page,
        screenshot_name="tsd-document-done",
        label_en="Order closed — stock matches the document",
        details=(
            "**Демонстрация результата.** Обе позиции накладной "
            "проведены леджером: кофе 5 → 0, чай 8 → 2 — ровно по "
            "спецификациям документа.\n\n"
            "**Итог.** Работа по документу: скан накладной → "
            "«Начать» → подсказка позиции → ячейка → товар → "
            "количество → проводка."
        ),
        details_en=(
            "**Result demonstration.** Both order lines were posted "
            "to the ledger: coffee 5 → 0, tea 8 → 2 — exactly per "
            "the document specs.\n\n"
            "**Summary.** Document work: scan the order → «Start» → "
            "line hint → bin → product → qty → commit."
        ),
    )

    # --- Тот же PWA на широком экране: ноутбук в приёмке/на ПК ---
    await page.set_viewport_size(ViewportSize(width=1440, height=900))
    await expect(page.locator("stock-tsd-home-page")).to_be_visible(timeout=15_000)
    await page.locator("stock-tsd-home-page").evaluate(
        "(el) => el.scrollTo(0, 0)"
    )
    await scenario.step(
        "Тот же терминал на ноутбуке",
        page,
        screenshot_name="tsd-document-desktop",
        label_en="The same terminal on a laptop",
        details=(
            "PWA — один бандл на все экраны: на десктопе рабочий стол "
            "центрирован и не растягивается — очередь, статистика смены "
            "и скан-поле остаются в той же компоновке, что на терминале."
        ),
        details_en=(
            "The PWA is one bundle for all screens: on desktop the "
            "work screen is centered and does not stretch — the queue, "
            "shift stats and scan field keep the same layout as on "
            "the handheld."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="tsd-document-pack",
    doc_slug="stock-tsd-document-pack",
    title="Упаковка по накладной: товар в короб",
    title_en="Packing against an order: product into a box",
    description=(
        "**Для чего:** упаковочное плечо накладной — собранный товар "
        "раскладывается в тару прямо на терминале, короб получает "
        "содержимое в системе одновременно с физическим действием.\n\n"
        "**Какие проблемы решает:** тип операции задаёт поток "
        "«упаковка» — экран просит товар, затем тару и количество; "
        "путать приёмник-ячейку и тару нельзя — машина принимает "
        "только контейнер.\n\n"
        "**Результат:** товар уехал с ячейки внутрь короба — "
        "остаток числится на таре."
    ),
    description_en=(
        "**Purpose:** the packing leg of an order — picked goods go "
        "into a container right on the handheld; the box gets its "
        "contents in the system at the same moment as physically.\n\n"
        "**Problems solved:** the operation type defines the «pack» "
        "flow — the screen asks for product, then container, then "
        "quantity; a bin cannot be mistaken for a box — the machine "
        "accepts containers only.\n\n"
        "**Result:** stock left the bin into the box — the quant "
        "now sits on the container."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_document_pack(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(TSD_VIEWPORT)
    await tsd_open(page, stock_ui)

    # --- Топология, остаток, пустой короб и накладная «pack» ---
    seed = await tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    bin_b = seed["bin_b"]
    product_1 = seed["product_1"]
    uom_id = seed["uom_id"]
    await tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "5"},
        ],
    )
    box_type = await stock_rest(
        page, "POST", "/container-types",
        {
            "warehouse_id": warehouse_id,
            "name": f"Короб {unique_id[:4]}",
            "kind": "box",
        },
    )
    box = await stock_rest(
        page, "POST", "/containers",
        {
            "warehouse_id": warehouse_id,
            "parent_location_id": bin_b["location_id"],
            "container_type_id": box_type["container_type_id"],
            "name": f"Короб {unique_id[:4]}",
            "barcode": f"BOX-{unique_id[:6]}",
        },
    )
    # Плечо упаковки — внутренняя операция (товар остаётся нашим,
    # меняет только носитель: ячейка → короб). OUTGOING-тип не подходит:
    # его конец внешний, а строка «в короб» — внутренняя.
    _ = await tsd_seed_document(
        page, warehouse_id, unique_id,
        [
            {
                "product_id": product_1["product_id"],
                "product_qty": "3",
                "uom_id": uom_id,
                "location_id": bin_a["location_id"],
            },
        ],
        code="internal",
        scan_flow="pack",
    )

    await tsd_pick_warehouse(page, unique_id)

    # --- Скан накладной → исполнение: backend выбрал поток «упаковка» ---
    await tsd_scan(page, f"DOC-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator("button.action").click()
    # scan_open с повтором: 2×15s бюджета операции под параллельным
    # прогоном — оператор физически ждёт, пока терминал отвечает.
    await expect(sheet).to_have_count(0, timeout=35_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)

    # --- Товар → тара → количество ---
    await tsd_scan(page, f"BC-1-{unique_id[:6]}")
    await tsd_wait_step(page, "container")
    await scenario.step(
        "Скан товара — терминал ждёт тару",
        page,
        screenshot_name="tsd-pack-product",
        label_en="Scan the product — terminal awaits the box",
        details=(
            "Поток «упаковка» ведёт жёстко: после товара машина "
            "принимает только контейнер — скан ячейки будет отклонён. "
            "Так терминал не даёт перепутать полку с коробом."
        ),
        details_en=(
            "The «pack» flow is strict: after the product the machine "
            "accepts a container only — a bin scan is rejected. The "
            "terminal cannot mix up a shelf and a box."
        ),
    )
    await tsd_scan(page, f"BOX-{unique_id[:6]}")
    await tsd_wait_step(page, "quantity")
    await tsd_qty(page, "3")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await tsd_commit(page)

    # --- Остаток переехал с ячейки в короб ---
    assert await stock_quant_qty(page, warehouse_id, product_1["product_id"], bin_a["location_id"]) == Decimal("2")
    assert await stock_quant_qty(page, warehouse_id, product_1["product_id"], box["location_id"]) == Decimal("3")

    # --- Скан короба: карточка тары показывает уложенный товар ---
    await tsd_scan(page, f"BOX-{unique_id[:6]}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Короб {unique_id[:4]}", timeout=15_000)
    await expect(sheet).to_contain_text(f"Кофе зерновой {unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "Скан короба — товар внутри",
        page,
        screenshot_name="tsd-pack-box",
        label_en="Scan the box — the product is inside",
        details=(
            "**Демонстрация результата.** Карточка короба показывает "
            "уложенный кофе — упаковка записана леджером, остаток "
            "числится на таре.\n\n"
            "**Итог.** Упаковка по накладной: скан документа → "
            "товар → короб → количество → проводка."
        ),
        details_en=(
            "**Result demonstration.** The box card shows the packed "
            "coffee — packing hit the ledger; the quant sits on the "
            "container.\n\n"
            "**Summary.** Packing against an order: scan document → "
            "product → box → qty → commit."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="tsd-document-ship",
    doc_slug="stock-tsd-document-ship",
    title="Отгрузка по накладной: один скан закрывает плечо",
    title_en="Shipping an order: one scan closes the leg",
    description=(
        "**Для чего:** отгрузочное плечо — упакованные короба "
        "уезжают машиной; пересканировать каждую позицию на воротах "
        "не нужно.\n\n"
        "**Какие проблемы решает:** тип операции задаёт поток "
        "«отгрузка»: скан отгрузочной зоны подтверждает плечо "
        "целиком — все открытые строки документа проводятся одним "
        "коммитом.\n\n"
        "**Результат:** остатки уехали клиенту по накладной без "
        "построчного пересканирования."
    ),
    description_en=(
        "**Purpose:** the shipping leg — packed boxes leave by "
        "truck; re-scanning every line at the dock is unnecessary.\n\n"
        "**Problems solved:** the operation type defines the «ship» "
        "flow: scanning the shipping zone confirms the whole leg — "
        "all open document lines post in one commit.\n\n"
        "**Result:** stock left to the customer per the order, "
        "without line-by-line re-scanning."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_document_ship(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(TSD_VIEWPORT)
    await tsd_open(page, stock_ui)

    # --- Топология, остаток и накладная «ship» на два товара ---
    seed = await tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    product_1 = seed["product_1"]
    product_2 = seed["product_2"]
    uom_id = seed["uom_id"]
    await tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "5"},
            {"location_dest_id": bin_a["location_id"], "product_id": product_2["product_id"], "quantity": "8"},
        ],
    )
    transfer = await tsd_seed_document(
        page, warehouse_id, unique_id,
        [
            {
                "product_id": product_1["product_id"],
                "product_qty": "4",
                "uom_id": uom_id,
                "location_id": bin_a["location_id"],
            },
            {
                "product_id": product_2["product_id"],
                "product_qty": "6",
                "uom_id": uom_id,
                "location_id": bin_a["location_id"],
            },
        ],
        scan_flow="ship",
    )

    await tsd_pick_warehouse(page, unique_id)

    # --- Скан накладной → скан ворот → проводка всего плеча ---
    await tsd_scan(page, f"DOC-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator("button.action").click()
    # scan_open с повтором: 2×15s бюджета операции под параллельным
    # прогоном — оператор физически ждёт, пока терминал отвечает.
    await expect(sheet).to_have_count(0, timeout=35_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)
    # ship-поток: единственный скан — отгрузочная ячейка, позиции
    # набирать не нужно — документ уже знает свой состав.
    await tsd_scan(page, f"BIN-B-{unique_id[:6]}")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await scenario.step(
        "Скан отгрузочной зоны — плечо готово к проводке",
        page,
        screenshot_name="tsd-ship-review",
        label_en="Scan the shipping zone — the leg is ready",
        details=(
            "Поток «отгрузка» не спрашивает позиции: один скан "
            "ворот/зоны подтверждает факт отгрузки — все открытые "
            "строки плеча уйдут одним коммитом без пересканирования "
            "каждого товара. Backend держит привилегию: провести "
            "ship можно только на плече с явным scan_flow=ship."
        ),
        details_en=(
            "The «ship» flow never asks for lines: one dock/zone "
            "scan confirms the shipment — every open leg line posts "
            "in a single commit without re-scanning each product. "
            "The backend guards the privilege: ship commits only on "
            "legs explicitly marked scan_flow=ship."
        ),
    )
    await tsd_commit_click(page)

    # --- Плечо второго товара: сессия продолжается сама —
    # следующая исполнимая строка накладной уже предложена ---
    await expect(run).to_be_visible(timeout=15_000)
    await tsd_wait_step(page, "start")
    await tsd_scan(page, f"BIN-B-{unique_id[:6]}")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await tsd_commit(page)

    # --- Все строки проведены: ячейка пуста по обоим позициям накладной ---
    assert await stock_quant_qty(page, warehouse_id, product_1["product_id"], bin_a["location_id"]) == Decimal("1")
    assert await stock_quant_qty(page, warehouse_id, product_2["product_id"], bin_a["location_id"]) == Decimal("2")
    detail = await stock_rest(page, "GET", f"/transfers/{transfer['transfer_id']}")
    assert all(m["state"] == "done" for m in detail["moves"]), detail["moves"]

    await scenario.step(
        "Накладная отгружена — обе позиции сошлись",
        page,
        screenshot_name="tsd-ship-done",
        label_en="Order shipped — both lines reconciled",
        details=(
            "**Демонстрация результата.** Один скан отгрузочной "
            "закрыл всё плечо: кофе 5 → 1, чай 8 → 2 — обе строки "
            "документа проведены и накладная done.\n\n"
            "**Итог.** Отгрузка: скан накладной → скан ворот → "
            "проводка."
        ),
        details_en=(
            "**Result demonstration.** One dock scan closed the "
            "whole leg: coffee 5 → 1, tea 8 → 2 — both document "
            "lines posted and the order is done.\n\n"
            "**Summary.** Shipping: scan the order → scan the dock → "
            "commit."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="tsd-putaway",
    doc_slug="stock-tsd-putaway",
    title="Размещение: скан товара на стейдже → постоянная ячейка",
    title_en="Putaway: scan the product on staging → permanent bin",
    description=(
        "**Для чего:** принятый товар стоит на стейдже — оператор "
        "увозит его в постоянную ячейку.\n\n"
        "**Какие проблемы решает:** со скана товара открывается "
        "действие «Разместить»: терминал жёстко ведёт — "
        "подтверждение точки отбора, целевая ячейка с подсказкой "
        "«куда положить», количество. Перепутать источник и "
        "приёмник нельзя.\n\n"
        "**Результат:** остаток переехал со стейджа в ячейку "
        "хранения одной внутренней операцией."
    ),
    description_en=(
        "**Purpose:** received goods sit on staging — the operator "
        "takes them to a permanent bin.\n\n"
        "**Problems solved:** scanning the product offers «Put "
        "away»: the terminal strictly guides — confirm the pick "
        "point, target bin with a placement hint, quantity. Source "
        "and destination cannot be mixed up.\n\n"
        "**Result:** stock moved from staging to the storage bin "
        "as one internal operation."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_putaway(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(TSD_VIEWPORT)
    await tsd_open(page, stock_ui)

    # --- Топология и сток на стейдже ---
    seed = await tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    bin_b = seed["bin_b"]
    product_1 = seed["product_1"]
    await tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "5"},
        ],
    )

    await tsd_pick_warehouse(page, unique_id)

    # --- Скан товара на стейдже → действие «Разместить» ---
    await tsd_scan(page, f"BC-1-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator("[data-action='putaway']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)

    # --- Подтверждение стейджа → целевая ячейка → количество ---
    await tsd_wait_step(page, "location")
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await tsd_wait_step(page, "dest")
    await tsd_scan(page, f"BIN-B-{unique_id[:6]}")
    await tsd_wait_step(page, "quantity")
    await scenario.step(
        "Размещение набрано — ячейка приёмник подтверждена сканом",
        page,
        screenshot_name="tsd-putaway-steps",
        label_en="Putaway captured — destination bin scanned",
        details=(
            "Поток «размещение» ведёт по физике действия: взял товар "
            "со стейджа → подтвердил точку отбора → пришёл к целевой "
            "ячейке (экран показывает подсказку «куда положить») → "
            "ввёл количество. Источник и приёмник — разные сканы, "
            "перепутать направление нельзя."
        ),
        details_en=(
            "The «putaway» flow follows the physics: pick the "
            "product from staging → confirm the pick point → arrive "
            "at the target bin (the screen hints «where to put it») → "
            "enter quantity. Source and destination are separate "
            "scans — direction can't flip."
        ),
    )
    await tsd_qty(page, "3")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await tsd_commit(page)

    # --- Остаток переехал со стейджа в хранение ---
    assert await stock_quant_qty(page, warehouse_id, product_1["product_id"], bin_a["location_id"]) == Decimal("2")
    assert await stock_quant_qty(page, warehouse_id, product_1["product_id"], bin_b["location_id"]) == Decimal("3")

    # --- Скан ячейки приёмника: содержимое показывает размещённый товар ---
    await tsd_scan(page, f"BIN-B-{unique_id[:6]}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Кофе зерновой {unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "Скан ячейки хранения — товар размещён",
        page,
        screenshot_name="tsd-putaway-done",
        label_en="Scan the storage bin — the product is put away",
        details=(
            "**Демонстрация результата.** Карточка ячейки "
            "показывает уложенный кофе — размещение записано "
            "леджером, стейдж разгружен.\n\n"
            "**Итог.** Размещение по накладной: скан документа → "
            "товар → стейдж → ячейка → количество → проводка."
        ),
        details_en=(
            "**Result demonstration.** The bin card shows the "
            "stored coffee — putaway hit the ledger; staging is "
            "cleared.\n\n"
            "**Summary.** Putaway against an order: scan document → "
            "product → staging → bin → qty → commit."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="tsd-document-exception",
    doc_slug="stock-tsd-document-exception",
    title="Проблема на линии: недостача репортится прямо из исполнения",
    title_en="Line problem: shortage reported right from execution",
    description=(
        "**Для чего:** оператор пришёл за товаром по заданию — "
        "а полка пуста или товар битый. Исполнение останавливать "
        "нельзя, но факт надо зафиксировать честно.\n\n"
        "**Какие проблемы решает:** кнопка проблемы на экране "
        "исполнения открывает лист: причина, недостача, фото. "
        "Backend укорачивает строку, отпускает резерв пустого места "
        "и ставит ячейке задание пересчёта — книжный остаток "
        "исправит инвентаризация, а не «не нашли».\n\n"
        "**Результат:** недостача записана, резерв снят, сессия "
        "закрыта — следующую работу даст очередь."
    ),
    description_en=(
        "**Purpose:** the operator reached the assigned bin — the "
        "shelf is empty or goods are damaged. Execution shouldn't "
        "stop silently, the fact must be recorded honestly.\n\n"
        "**Problems solved:** the problem button on the run screen "
        "opens a sheet: reason, shortage, photos. The backend "
        "shortens the line, releases the empty spot's reservation "
        "and schedules a recount — the ledger is fixed by "
        "inventory, not by «not found».\n\n"
        "**Result:** shortage recorded, reserve freed, session "
        "closed — the queue gives the next work."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_document_exception(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(TSD_VIEWPORT)
    await tsd_open(page, stock_ui)

    # --- Топология, сток и накладная «pick» на 4 шт ---
    seed = await tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    product_1 = seed["product_1"]
    uom_id = seed["uom_id"]
    await tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "4"},
        ],
    )
    transfer = await tsd_seed_document(
        page, warehouse_id, unique_id,
        [
            {
                "product_id": product_1["product_id"],
                "product_qty": "4",
                "uom_id": uom_id,
                "location_id": bin_a["location_id"],
            },
        ],
    )

    await tsd_pick_warehouse(page, unique_id)

    # --- Скан накладной → исполнение отбора ---
    await tsd_scan(page, f"DOC-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator("button.action").click()
    # scan_open с повтором: 2×15s бюджета операции под параллельным
    # прогоном — оператор физически ждёт, пока терминал отвечает.
    await expect(sheet).to_have_count(0, timeout=35_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)

    # --- Кнопка проблемы → лист: причина «нет на полке» + недостача 2 ---
    await run.locator("[data-action='report-problem']").click()
    exc = page.locator("stock-tsd-exception-sheet")
    await expect(exc).to_be_visible(timeout=15_000)
    await exc.locator(".qty-btn", has_text="+").click()
    await scenario.step(
        "Лист проблемы: причина и недостача",
        page,
        screenshot_name="tsd-exception-sheet",
        label_en="Problem sheet: reason and shortage",
        details=(
            "Оператор физически не может выполнить строку — товара "
            "нет. Лист спрашивает причину и сколько недостаёт; "
            "фото прикладываются как доказательство для эскалации."
        ),
        details_en=(
            "The operator physically cannot fulfil the line — the "
            "goods are missing. The sheet asks the reason and how "
            "many are short; photos attach as escalation evidence."
        ),
    )
    await exc.locator(".submit").click()
    await expect(exc).to_have_count(0, timeout=15_000)
    # Сессия закрыта — оператор вернулся на рабочий стол.
    await expect(run).to_have_count(0, timeout=15_000)

    # --- Строка укорочена на недостачу, резерв пустого места снят ---
    detail = await stock_rest(page, "GET", f"/transfers/{transfer['transfer_id']}")
    assert Decimal(str(detail["lines"][0]["quantity"])) == Decimal("2"), detail["lines"]
    quant = await stock_quant_row(page, warehouse_id, product_1["product_id"], bin_a["location_id"])
    assert Decimal(str(quant["reserved_quantity"])) == Decimal("2"), quant

    await scenario.step(
        "Недостача записана — строка и резерв сошлись",
        page,
        screenshot_name="tsd-exception-done",
        label_en="Shortage recorded — line and reserve reconciled",
        details=(
            "**Демонстрация результата.** Строка укорочена 4 → 2, "
            "резерв на ячейке отпущен — «обещание» на пустое место "
            "снято, никто больше сюда не поедет. Задание пересчёта "
            "ячейки поставлено: книжный остаток исправит "
            "инвентаризация.\n\n"
            "**Итог.** Проблема: исполнение → кнопка → причина + "
            "недостача → репорт."
        ),
        details_en=(
            "**Result demonstration.** The line shortened 4 → 2, "
            "the bin reserve released — the «promise» on the empty "
            "spot is lifted, nobody else will be sent there. A "
            "recount task is set: inventory fixes the book "
            "quantity.\n\n"
            "**Summary.** Problem: execution → button → reason + "
            "shortage → report."
        ),
    )

    # --- «Дайте работу» выдаёт задание пересчёта (оно приоритетнее) ---
    await page.locator(".give-work").click()
    await expect(run).to_be_visible(timeout=30_000)
    # Пересчёт физически: дошёл до ячейки → скан ячейки → скан товара → факт.
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await tsd_wait_step(page, "product")
    await tsd_scan(page, f"BC-1-{unique_id[:6]}")
    await expect(run.locator(".qty-panel")).to_be_visible(timeout=15_000)
    await tsd_qty(page, "8")
    await tsd_wait_step(page, "review")
    await scenario.step(
        "Пересчёт по заданию — факт на месте",
        page,
        screenshot_name="tsd-exception-recount",
        label_en="Recount task — counted fact",
        details=(
            "«Дайте работу» выдало задание пересчёта подозрительной "
            "ячейки — оно приоритетнее добора. Оператор дошёл до "
            "места, отсканировал ячейку и товар, ввёл факт 8: "
            "нашлось больше книжного — дельта уйдёт на утверждение "
            "инвентаризации."
        ),
        details_en=(
            "«Give me work» issued the suspect-bin recount task — it "
            "outranks the remaining pick. The operator walked to the "
            "spot, scanned the bin and the product, entered the "
            "counted 8: more than book — the delta goes to inventory "
            "approval."
        ),
    )
    await tsd_commit(page)
    await expect(run).to_have_count(0, timeout=15_000)

    # --- Задание пересчёта закрыто фактом — не висит в очереди вечно ---
    detail = await stock_rest(page, "GET", f"/transfers/{transfer['transfer_id']}")
    count_lines = [ln for ln in detail["lines"] if ln.get("kind") == "count"]
    assert len(count_lines) == 1, detail["lines"]
    assert count_lines[0]["state"] == "done", count_lines[0]


@pytest.mark.scenario(
    service="stock",
    tag="tsd-context-chips",
    doc_slug="stock-tsd-context-chips",
    title="Контекст смены: зона, волна и техника сужают работу",
    title_en="Shift context: zone, wave and equipment narrow the work",
    description=(
        "**Для чего:** оператор физически стоит в своей зоне со "
        "своей тележкой — показывать ему задания с другого конца "
        "склада бессмысленно. Чипы контекста переводят терминал "
        "в режим «моя зона / моя волна / моя техника».\n\n"
        "**Какие проблемы решает:** привязка — один тап и один "
        "скан: чип зоны взводится и баркод зоны сужает очередь до "
        "поддерева ячеек; волна выбирается из списка отпущенных "
        "диспетчером; тележка привязывается её баркодом и участвует "
        "в выдаче работы (ресурс фильтрует задания по возможностям).\n\n"
        "**Результат:** «дайте работу» выдаёт именно то задание, "
        "которое оператор способен и должен сделать первым."
    ),
    description_en=(
        "**Purpose:** the operator physically stands in their zone "
        "with their cart — showing tasks from the far end of the "
        "warehouse is pointless. Context chips switch the terminal "
        "to «my zone / my wave / my equipment» mode.\n\n"
        "**Problems solved:** binding is one tap and one scan: the "
        "zone chip arms and a zone barcode narrows the queue to "
        "that bin subtree; the wave is picked from the dispatcher-"
        "released list; the cart binds via its barcode and takes "
        "part in work assignment (the resource filters tasks by "
        "capability).\n\n"
        "**Result:** «give me work» issues exactly the task the "
        "operator can and should do first."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_context_chips(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(TSD_VIEWPORT)
    await tsd_open(page, stock_ui)

    # --- Топология: зона А с двумя ячейками + зона Б с ячейкой вне её ---
    seed = await tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    zone = seed["zone"]
    bin_a = seed["bin_a"]
    product_1 = seed["product_1"]
    product_2 = seed["product_2"]
    uom_id = seed["uom_id"]
    # Зона получает баркод — её скан привязывает оператора к поддереву.
    await stock_rest(
        page, "PATCH", f"/locations/{zone['location_id']}",
        {"location_id": zone["location_id"], "barcode": f"ZONE-1-{unique_id[:6]}"},
    )
    zone_b = await stock_rest(
        page, "POST", "/locations",
        {"warehouse_id": warehouse_id, "name": f"Зона Б{unique_id[:3]}", "usage": "view"},
    )
    bin_c = await stock_rest(
        page, "POST", "/locations",
        {
            "warehouse_id": warehouse_id,
            "parent_id": zone_b["location_id"],
            "name": f"Ячейка В{unique_id[:3]}",
            "usage": "bin",
            "barcode": f"BIN-C-{unique_id[:6]}",
        },
    )
    await tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "5"},
            {"location_dest_id": bin_c["location_id"], "product_id": product_2["product_id"], "quantity": "4"},
        ],
    )

    # --- Две накладные: отбор из зоны А (уйдёт в волну) и из зоны Б ---
    doc_1 = await tsd_seed_document(
        page, warehouse_id, unique_id,
        [
            {
                "product_id": product_1["product_id"],
                "product_qty": "3",
                "uom_id": uom_id,
                "location_id": bin_a["location_id"],
            },
        ],
    )
    _ = await tsd_seed_document(
        page, warehouse_id, f"z{unique_id}",
        [
            {
                "product_id": product_2["product_id"],
                "product_qty": "2",
                "uom_id": uom_id,
                "location_id": bin_c["location_id"],
            },
        ],
    )
    detail = await stock_rest(page, "GET", f"/transfers/{doc_1['transfer_id']}")
    move_1_id = detail["moves"][0]["move_id"]
    wave = await stock_rest(
        page, "POST", "/waves",
        {
            "warehouse_id": warehouse_id,
            "name": f"Волна {unique_id[:4]}",
            "move_ids": [move_1_id],
        },
    )
    await stock_rest(
        page, "POST", f"/waves/{wave['wave_id']}/release",
        {"wave_id": wave["wave_id"]},
    )

    # --- Техника с баркодом: скан привязывает тележку к оператору ---
    rtype = await stock_rest(
        page, "POST", "/resource-types",
        {"warehouse_id": warehouse_id, "name": f"Тележка {unique_id[:4]}"},
    )
    await stock_rest(
        page, "POST", "/resources",
        {
            "warehouse_id": warehouse_id,
            "resource_type_id": rtype["resource_type_id"],
            "code": f"T-{unique_id[:4]}",
            "barcode": f"RES-{unique_id[:6]}",
        },
    )

    await tsd_pick_warehouse(page, unique_id)

    # --- Очередь без контекста: оба задания видны ---
    chips = page.locator("stock-tsd-home-page .context-chips .chip")
    cards = page.locator("stock-tsd-home-page .task-card")
    await expect(cards).to_have_count(2, timeout=15_000)

    # --- Чип зоны: тап → баннер «сканируйте зону» → скан сужает очередь ---
    await chips.nth(0).click()
    await expect(page.locator(".pending-banner")).to_be_visible(timeout=10_000)
    await tsd_scan(page, f"ZONE-1-{unique_id[:6]}")
    await expect(chips.nth(0)).to_contain_text(f"ZONE-1-{unique_id[:6]}", timeout=15_000)
    # Ячейка В вне поддерева зоны А — её задание ушло из списка.
    await expect(cards).to_have_count(1, timeout=15_000)
    await scenario.step(
        "Скан зоны — очередь сужена до моего поддерева",
        page,
        screenshot_name="tsd-context-zone",
        label_en="Zone scan — the queue narrows to my subtree",
        details=(
            "Оператор вошёл в зону А: тап по чипу и один скан "
            "баркова зоны — чип подсвечен привязкой, а в очереди "
            "осталась только работа из ячеек этой зоны. Задание "
            "с ячейки В (другая зона) терминал больше не предлагает."
        ),
        details_en=(
            "The operator entered zone A: one tap on the chip and "
            "one scan of the zone barcode — the chip is lit as "
            "bound, and the queue keeps only work from that zone's "
            "bins. The task from bin C (other zone) is no longer "
            "offered."
        ),
    )

    # --- Чип волны: тап → список отпущенных волн → выбор сужает ещё раз ---
    await chips.nth(2).click()
    wave_item = page.locator(".wave-item", has_text=f"Волна {unique_id[:4]}")
    await expect(wave_item).to_be_visible(timeout=15_000)
    await scenario.step(
        "Отпущенные волны — диспетчер нарезал маршрут",
        page,
        screenshot_name="tsd-context-wave-list",
        label_en="Released waves — the dispatcher sliced the route",
        details=(
            "Волна — нарезанный диспетчером маршрут отбора: "
            "терминал показывает только отпущенные волны склада. "
            "Выбор волны — тапом: у партии нет физического баркода."
        ),
        details_en=(
            "A wave is the dispatcher-sliced pick route: the "
            "terminal lists only waves released for this warehouse. "
            "The wave is picked by tap — a batch has no physical "
            "barcode."
        ),
    )
    await wave_item.click()
    await expect(chips.nth(2)).to_contain_text(f"Волна {unique_id[:4]}", timeout=15_000)
    await expect(cards).to_have_count(1, timeout=15_000)
    # Карточка задания несёт бейдж волны — оператор видит привязку.
    await expect(cards.first.locator(".task-wave")).to_contain_text(
        f"Волна {unique_id[:4]}", timeout=15_000
    )

    # --- Чип техники: тап → скан баркода тележки — привязка на сервере ---
    await chips.nth(1).click()
    await expect(page.locator(".pending-banner")).to_be_visible(timeout=10_000)
    await tsd_scan(page, f"RES-{unique_id[:6]}")
    await expect(chips.nth(1)).to_contain_text(f"T-{unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "Контекст собран: зона + волна + тележка",
        page,
        screenshot_name="tsd-context-bound",
        label_en="Context assembled: zone + wave + cart",
        details=(
            "Три чипа привязаны двумя сканами и одним тапом: "
            "терминал теперь отвечает на вопрос «что делать» с "
            "учётом физики — где я стою, какой маршрут отпущен и "
            "на чём я еду. Тележка числится занятой за оператором "
            "на сервере — второй терминал её не уведёт."
        ),
        details_en=(
            "Three chips bound with two scans and one tap: the "
            "terminal now answers «what to do» with physics in "
            "mind — where I stand, which route is released, and "
            "what I'm driving. The cart is server-bound to the "
            "operator — a second terminal can't steal it."
        ),
    )

    # --- «Дайте работу» выдаёт задание из связанного контекста ---
    await page.locator(".give-work").click()
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=30_000)
    await expect(run.locator(".expected")).to_contain_text(
        f"Кофе зерновой {unique_id[:4]}", timeout=15_000
    )
    await scenario.step(
        "«Дайте работу» — первая строка связанного контекста",
        page,
        screenshot_name="tsd-context-give-work",
        label_en="«Give me work» — first line of the bound context",
        details=(
            "**Демонстрация результата.** Выдача прошла через "
            "тройной фильтр зоны + волны + ресурса: исполнение "
            "открылось на строке кофе из зоны А — задании волны. "
            "Строка захвачена за оператором в той же транзакции.\n\n"
            "**Итог.** Контекст: чип зоны → скан → чип волны → тап "
            "→ чип техники → скан → «дайте работу»."
        ),
        details_en=(
            "**Result demonstration.** Issue passed the triple "
            "zone + wave + resource filter: execution opened on "
            "the coffee line from zone A — the wave's task. The "
            "line was claimed for the operator in the same "
            "transaction.\n\n"
            "**Summary.** Context: zone chip → scan → wave chip → "
            "tap → equipment chip → scan → «give me work»."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="tsd-inquiry",
    doc_slug="stock-tsd-inquiry",
    title="Свободный осмотр: скан чего угодно — карточка сущности",
    title_en="Free inquiry: scan anything — entity card follows",
    description=(
        "**Для чего:** оператор может сканировать любой баркод в "
        "любой момент — не думая, на каком он экране: товар, ячейка, "
        "тара или техника — терминал показывает её карточку и "
        "осмысленные действия.\n\n"
        "**Какие проблемы решает:** повторный скан обновляет "
        "открытую карточку по месту, а не плодит стек окон; скан "
        "баркида тележки предлагает привязать её к смене прямо из "
        "карточки.\n\n"
        "**Результат:** три разных скана сменили содержимое одной "
        "карточки; техника привязана без входа в меню."
    ),
    description_en=(
        "**Purpose:** the operator can scan any barcode at any "
        "moment — regardless of the current screen: product, bin, "
        "container or equipment — the terminal shows its card with "
        "meaningful actions.\n\n"
        "**Problems solved:** a rescan refreshes the open card in "
        "place instead of stacking windows; scanning a cart barcode "
        "offers binding it to the shift right from the card.\n\n"
        "**Result:** three different scans swapped the contents of "
        "a single card; equipment bound without opening menus."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_inquiry_rescan(
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
    product_1 = seed["product_1"]
    product_2 = seed["product_2"]
    await tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "5"},
            {"location_dest_id": bin_a["location_id"], "product_id": product_2["product_id"], "quantity": "8"},
        ],
    )
    # Техника с баркодом — скан вне «взведённого» чипа открывает её карточку.
    rtype = await stock_rest(
        page, "POST", "/resource-types",
        {"warehouse_id": warehouse_id, "name": f"Тележка {unique_id[:4]}"},
    )
    await stock_rest(
        page, "POST", "/resources",
        {
            "warehouse_id": warehouse_id,
            "resource_type_id": rtype["resource_type_id"],
            "code": f"T-{unique_id[:4]}",
            "barcode": f"RES-{unique_id[:6]}",
        },
    )
    await tsd_pick_warehouse(page, unique_id)

    # --- Скан товара: карточка открылась ---
    await tsd_scan(page, f"BC-1-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Кофе зерновой {unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "Скан товара — карточка с остатками",
        page,
        screenshot_name="tsd-inquiry-product",
        label_en="Product scan — card with stock",
        details=(
            "Свободный осмотр: скан товара без всякого задания "
            "открывает его карточку — фото, штрихкод, остатки по "
            "ячейкам (грузятся с лоудерами) и действия «принять / "
            "переместить / посчитать»."
        ),
        details_en=(
            "Free inquiry: scanning a product with no active task "
            "opens its card — photo, barcode, per-bin stock "
            "(loading asynchronously) and «receive / move / count» "
            "actions."
        ),
    )

    # --- Рескан ДРУГОГО товара: та же карточка обновилась по месту ---
    await tsd_scan(page, f"BC-2-{unique_id[:6]}")
    # В стеке ровно один лист — карточек «поверх» не наслаивается.
    await expect(sheet).to_have_count(1, timeout=15_000)
    await expect(sheet).to_contain_text(f"Чай листовой {unique_id[:4]}", timeout=30_000)
    await expect(sheet).not_to_contain_text(f"Кофе зерновой {unique_id[:4]}")

    # --- Скан ячейки поверх открытой карточки: содержимое подменилось ---
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await expect(sheet).to_have_count(1, timeout=15_000)
    await expect(sheet).to_contain_text(f"Ячейка А{unique_id[:3]}", timeout=30_000)
    await expect(sheet).to_contain_text(f"Кофе зерновой {unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "Скан ячейки — карточка переключилась на её содержимое",
        page,
        screenshot_name="tsd-inquiry-bin",
        label_en="Bin scan — the card switched to its contents",
        details=(
            "Тот же лист по месту стал карточкой ячейки: учётное "
            "содержимое «Кофе 5 + Чай 8». Стек окон не растёт — "
            "оператор сканирует подряд, терминал следует за рукой."
        ),
        details_en=(
            "The same sheet in place became the bin card: book "
            "contents «Coffee 5 + Tea 8». No window stack growth — "
            "the operator scans in a row, the terminal follows."
        ),
    )

    # --- Скан баркода тележки: карточка ресурса → привязка ---
    await tsd_scan(page, f"RES-{unique_id[:6]}")
    # У ресурса одно действие «привязать» — ждём переключения карточки
    # (у ячейки три кнопки: переходный кадр ловить нельзя).
    await expect(sheet.locator(".action")).to_have_count(1, timeout=30_000)
    await sheet.locator(".action").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    # Привязка прошла на сервере — чип техники заполнен кодом.
    chip = page.locator("stock-tsd-home-page .context-chips .chip").nth(1)
    await expect(chip).to_contain_text(f"T-{unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "Скан техники — привязана к смене из карточки",
        page,
        screenshot_name="tsd-inquiry-resource",
        label_en="Equipment scan — bound to the shift from the card",
        details=(
            "**Демонстрация результата.** Штрихкод тележки открыл "
            "карточку ресурса, кнопка «привязать» закрепила её за "
            "оператором на сервере — чип техники теперь показывает "
            "код тележки. Никаких меню и ручного ввода.\n\n"
            "**Итог.** Любой скан с любого экрана — правильная "
            "карточка; рескан обновляет её по месту."
        ),
        details_en=(
            "**Result demonstration.** The cart barcode opened the "
            "resource card, «bind» claimed it for the operator on "
            "the server — the equipment chip now shows the cart "
            "code. No menus, no typing.\n\n"
            "**Summary.** Any scan from any screen — the right "
            "card; a rescan refreshes it in place."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="tsd-receive-multiline",
    doc_slug="stock-tsd-receive-multiline",
    title="Приёмка пачкой: три товара в один документ",
    title_en="Batch receiving: three products, one document",
    description=(
        "**Для чего:** машина с паллетой везёт несколько позиций — "
        "оператор набирает строки подряд и проводит одну приёмку, а "
        "не три отдельные.\n\n"
        "**Какие проблемы решает:** после ввода количества терминал "
        "снова ждёт товар — ячейка удерживается между строками; "
        "review показывает все набранные позиции перед проводкой.\n\n"
        "**Результат:** три товара проведены одним документом на "
        "одну ячейку, остатки легли по леджеру."
    ),
    description_en=(
        "**Purpose:** a pallet carries several items — the operator "
        "enters lines back to back and posts a single receipt "
        "instead of three.\n\n"
        "**Problems solved:** after quantity entry the terminal "
        "asks for the next product — the bin sticks between lines; "
        "review lists all entered positions before posting.\n\n"
        "**Result:** three products posted in one document to one "
        "bin, stock landed in the ledger."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_receive_multiline(
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
    product_1 = seed["product_1"]
    product_2 = seed["product_2"]
    uom_id = seed["uom_id"]
    product_3 = await stock_rest(
        page, "POST", "/products",
        {
            "name": f"Какао {unique_id[:4]}",
            "sku": f"CACAO-{unique_id[:6]}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "standard_price": "0",
            "tracking": "none",
            "is_storable": True,
            "barcodes": [f"BC-3-{unique_id[:6]}"],
        },
    )
    await tsd_seed_product_image(
        page, str(product_3["product_id"]), color="#5d4037", label="КАКАО"
    )
    await tsd_pick_warehouse(page, unique_id)

    # --- Приёмка: товар 1 → ячейка → количество → товар 2 → ... ---
    await tsd_scan(page, f"BC-1-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator(".action[data-action='receive']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await expect(run.locator(".qty-panel")).to_be_visible(timeout=15_000)
    await tsd_qty(page, "5")
    # Review: скан второго товара добавляет строку — направление
    # каждой строки подтверждается явным сканом ячейки (физика: куда
    # кладут ЭТИ короба).
    await tsd_wait_step(page, "review")
    await tsd_scan(page, f"BC-2-{unique_id[:6]}")
    await tsd_wait_step(page, "dest")
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await tsd_wait_step(page, "quantity")
    await tsd_qty(page, "7")
    await tsd_wait_step(page, "review")
    await tsd_scan(page, f"BC-3-{unique_id[:6]}")
    await tsd_wait_step(page, "dest")
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await tsd_wait_step(page, "quantity")
    await tsd_qty(page, "3")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await expect(run.locator(".line-row")).to_have_count(3, timeout=15_000)
    await scenario.step(
        "Три строки в review — одна проводка",
        page,
        screenshot_name="tsd-receive-multiline-review",
        label_en="Three lines in review — one posting",
        details=(
            "После «5» по кофе терминал ждал следующий товар. Скан "
            "чая → повторный скан ячейки (куда кладём ЭТОТ товар) → "
            "«7», скан какао → ячейка → «3»: три строки набраны "
            "подряд. Проводка пойдёт одним документом."
        ),
        details_en=(
            "After «5» for coffee the terminal waited for the next "
            "product. Tea scan → rescan the bin (where THIS product "
            "goes) → «7», cocoa scan → bin → «3»: three lines "
            "entered in a row. Posting goes as a single document."
        ),
    )
    await tsd_commit(page)

    # --- Один коммит положил все три товара ---
    for product, qty in ((product_1, "5"), (product_2, "7"), (product_3, "3")):
        actual = await stock_quant_qty(
            page, warehouse_id, product["product_id"], bin_a["location_id"]
        )
        assert actual == Decimal(qty), f"{product['name']}: {actual} != {qty}"

    await scenario.step(
        "Остатки: три позиции на одной ячейке",
        page,
        screenshot_name="tsd-receive-multiline-done",
        label_en="Stock: three items on one bin",
        details=(
            "**Демонстрация результата.** Леджер подтверждает: кофе "
            "5 + чай 7 + какао 3 лежат на ячейке А — все пришли "
            "единственной проводкой.\n\n"
            "**Итог.** Приёмка пачкой: товар → ячейка → количество → "
            "следующий товар → … → один commit."
        ),
        details_en=(
            "**Result demonstration.** The ledger confirms: coffee "
            "5 + tea 7 + cocoa 3 sit on bin A — all posted by a "
            "single commit.\n\n"
            "**Summary.** Batch receiving: product → bin → qty → "
            "next product → … → one commit."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="tsd-count-zero",
    doc_slug="stock-tsd-count-zero",
    title="Пересчёт до нуля: «в ячейке пусто» — тоже факт",
    title_en="Counting down to zero: «bin is empty» is a fact too",
    description=(
        "**Для чего:** оператор дошёл до ячейки и физически видит "
        "пустоту — система обязана принять нулевой факт, а не "
        "заставлять вводить ложное количество.\n\n"
        "**Какие проблемы решает:** ноль — легальное количество "
        "только в пересчёте: записывается как факт инвентаризации и "
        "даёт расхождение на утверждение, вместо отказа «количество "
        "должно быть больше нуля».\n\n"
        "**Результат:** факт 0 записан на остаток ячейки, расхождение "
        "−5 видно системе."
    ),
    description_en=(
        "**Purpose:** the operator reached the bin and physically "
        "sees emptiness — the system must accept a zero fact instead "
        "of forcing a fake quantity.\n\n"
        "**Problems solved:** zero is a legal quantity only in "
        "counting: recorded as the count fact and produces a "
        "variance for approval, instead of «quantity must be "
        "greater than zero» rejection.\n\n"
        "**Result:** fact 0 written onto the bin stock, variance "
        "−5 visible to the system."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_count_zero(
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
    product_1 = seed["product_1"]
    await tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "5"},
        ],
    )
    await tsd_pick_warehouse(page, unique_id)

    # --- Скан ячейки → «Посчитать» → скан товара → факт 0 ---
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator(".action[data-action='count']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)
    await tsd_scan(page, f"BC-1-{unique_id[:6]}")
    await expect(run.locator(".qty-panel")).to_be_visible(timeout=15_000)
    await tsd_qty(page, "0")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await scenario.step(
        "Факт 0 принят — review показывает расхождение",
        page,
        screenshot_name="tsd-count-zero-review",
        label_en="Fact 0 accepted — review shows the variance",
        details=(
            "Учётно на ячейке 5, физически пусто: «0» — честный "
            "факт пересчёта, не ошибка ввода. Строка готова к "
            "проводке — система запишет факт и отметит минус 5 "
            "для сверки."
        ),
        details_en=(
            "The book says 5, physically empty: «0» is an honest "
            "count fact, not an input error. The line is ready to "
            "post — the system records the fact and flags −5 for "
            "reconciliation."
        ),
    )
    await tsd_commit(page)

    # --- Факт 0 записан: inventory_quantity = 0 ---
    row = await stock_quant_row(
        page, warehouse_id, product_1["product_id"], bin_a["location_id"]
    )
    assert Decimal(str(row["inventory_quantity"])) == Decimal("0")
    await scenario.step(
        "Факт нуля лёг на остаток — расхождение видно",
        page,
        screenshot_name="tsd-count-zero-done",
        label_en="Zero fact on the stock — variance visible",
        details=(
            "**Демонстрация результата.** На остатке ячейки "
            "записан факт инвентаризации 0 — разница с учётными 5 "
            "уйдёт на утверждение корректировки.\n\n"
            "**Итог.** «Пустая ячейка» вводится как 0 — терминал "
            "не требует выдумывать количество."
        ),
        details_en=(
            "**Result demonstration.** The bin stock now carries "
            "the count fact 0 — the difference against book 5 "
            "goes for adjustment approval.\n\n"
            "**Summary.** «Empty bin» is entered as 0 — the "
            "terminal does not force inventing a quantity."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="tsd-hid-scan",
    doc_slug="stock-tsd-hid-scan",
    title="HID-сканер: быстрый клавиатурный ввод = скан",
    title_en="HID scanner: fast keyboard burst = scan",
    description=(
        "**Для чего:** аппаратный сканер работает как клавиатура — "
        "выстреливает символы пачкой и заканчивает Enter. Терминал "
        "отличает такой ввод от набора руками и в поле поиска его "
        "не ждёт.\n\n"
        "**Какие проблемы решает:** ручной ввод того же кода "
        "ничего не откроет (это обычный текст), а burst быстрее "
        "порога с Enter-суффиксом распознаётся как скан и идёт в "
        "ту же машину, что DataWedge-канал.\n\n"
        "**Результат:** код, «набранный» со скоростью сканера, "
        "открыл карточку товара — без полей и кнопок."
    ),
    description_en=(
        "**Purpose:** a hardware scanner acts as a keyboard — it "
        "fires characters in a burst ending with Enter. The "
        "terminal tells that apart from hand typing and does not "
        "wait for it in a search field.\n\n"
        "**Problems solved:** hand-typing the same code opens "
        "nothing (plain text), while a burst faster than the "
        "threshold with an Enter suffix is recognised as a scan "
        "and enters the same machine as the DataWedge channel.\n\n"
        "**Result:** the code «typed» at scanner speed opened the "
        "product card — no fields, no buttons."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_hid_scan(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(TSD_VIEWPORT)
    await tsd_open(page, stock_ui)
    await tsd_seed_warehouse(page, unique_id)
    await tsd_pick_warehouse(page, unique_id)

    # --- HID-burst: keydown-пачка быстрее 40 мс + Enter-суффикс ---
    # page.keyboard.type эмитирует trusted-события с задержкой —
    # 15 мс на символ укладывается в окно burst-эвристики сканера.
    await page.keyboard.type(f"BC-1-{unique_id[:6]}", delay=15)
    await page.keyboard.press("Enter")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Кофе зерновой {unique_id[:4]}", timeout=15_000)
    await scenario.step(
        "HID-ввод распознан как скан — карточка открылась",
        page,
        screenshot_name="tsd-hid-scan-card",
        label_en="HID input recognised as a scan — card opened",
        details=(
            "**Демонстрация результата.** Символы пришли пачкой по "
            "15 мс и закрылись Enter — эвристика сканера сработала, "
            "текстовое поле не понадобилось. Тот же код руками "
            "(медленнее порога) остался бы обычным набором.\n\n"
            "**Итог.** Аппаратный сканер «из коробки» — без "
            "DataWedge и без полей ввода."
        ),
        details_en=(
            "**Result demonstration.** Characters arrived in a "
            "15 ms burst closed by Enter — the scanner heuristic "
            "fired, no text field needed. The same code typed by "
            "hand (slower than the threshold) would stay plain "
            "typing.\n\n"
            "**Summary.** A hardware scanner works out of the box "
            "— no DataWedge, no input fields."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="tsd-offline-outbox",
    doc_slug="stock-tsd-offline-outbox",
    title="Мёртвая зона Wi-Fi: проводка уедет из outbox при связи",
    title_en="Wi-Fi dead zone: the posting ships from the outbox",
    description=(
        "**Для чего:** металлические стеллажи глушат связь — "
        "оператор не должен останавливаться или повторять работу: "
        "коммит встаёт в outbox и уезжает сам при возврате сети.\n\n"
        "**Какие проблемы решает:** ключ идемпотентности пишется "
        "ДО первой попытки — потерянный ответ не даст двойной "
        "проводки; очередь FIFO, доменный отказ останавливает "
        "дрейн, а не молча пропускает.\n\n"
        "**Результат:** приёмка набрана офлайн, уехала при "
        "восстановлении связи, остатки легли один раз."
    ),
    description_en=(
        "**Purpose:** metal racks kill connectivity — the operator "
        "must not stop or redo work: the commit lands in the "
        "outbox and ships itself when the network returns.\n\n"
        "**Problems solved:** the idempotency key is written "
        "BEFORE the first attempt — a lost response cannot double "
        "post; the queue is FIFO, a domain rejection stops "
        "draining instead of silently skipping.\n\n"
        "**Result:** a receipt entered offline shipped on "
        "reconnect, stock posted exactly once."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_offline_outbox(
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
    product_1 = seed["product_1"]
    await tsd_pick_warehouse(page, unique_id)

    # --- Сессия набрана ОНЛАЙН: товар → ячейка → количество ---
    await tsd_scan(page, f"BC-1-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator(".action[data-action='receive']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)
    await tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await expect(run.locator(".qty-panel")).to_be_visible(timeout=15_000)
    await tsd_qty(page, "9")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)

    # --- Офлайн: коммит уходит в outbox, сессия закрывается честно ---
    # Эмулируем потерю связи на уровне терминала: navigator.onLine
    # (его читает tsdOffline) + bus-событие connectivity/offline —
    # ровно то, что слушает сеть терминала. Настоящий 'offline'
    # event ронял бы Centrifugo-транспорт вместе с CDP-прогоном.
    await page.evaluate(
        """() => {
            Object.defineProperty(navigator, 'onLine',
                { configurable: true, get: () => false });
            window.__PLATFORM_BUS__.dispatch({
                type: 'network/connectivity/offline', payload: null,
            });
        }"""
    )
    await tsd_commit_click(page)
    await expect(run).to_have_count(0, timeout=15_000)
    banner = page.locator("stock-tsd-home-page .outbox-banner")
    await expect(banner).to_be_visible(timeout=15_000)
    await scenario.step(
        "Без связи коммит встал в outbox",
        page,
        screenshot_name="tsd-offline-enqueued",
        label_en="Offline commit queued in the outbox",
        details=(
            "Связь пропала между набором и проводкой — терминал не "
            "завис и не потерял работу: документ в outbox'е с "
            "готовым ключом идемпотентности, баннер показывает "
            "«ожидает отправки: 1»."
        ),
        details_en=(
            "Connectivity dropped between entry and posting — the "
            "terminal neither hung nor lost work: the document sits "
            "in the outbox with a ready idempotency key, the banner "
            "shows «pending: 1»."
        ),
    )

    # --- Связь вернулась: дрейн доставил документ ровно один раз ---
    await page.evaluate(
        """() => {
            Object.defineProperty(navigator, 'onLine',
                { configurable: true, get: () => true });
            window.__PLATFORM_BUS__.dispatch({
                type: 'network/connectivity/online', payload: null,
            });
        }"""
    )
    # WS настоящий (жил всё время) — дрейн сработает по событию online.
    await page.wait_for_function(
        """() => {
            const bus = window.__PLATFORM_BUS__;
            const s = bus.getState();
            return s.network?.ws?.status === 'open'
                && (s.stockTsdOutbox?.items ?? []).length === 0;
        }""",
        timeout=60_000,
    )
    qty = await stock_quant_qty(
        page, warehouse_id, product_1["product_id"], bin_a["location_id"]
    )
    assert qty == Decimal("9")
    await scenario.step(
        "Связь вернулась — документ доехал один раз",
        page,
        screenshot_name="tsd-offline-drained",
        label_en="Back online — the document shipped exactly once",
        details=(
            "**Демонстрация результата.** Outbox пуст, на ячейке "
            "ровно 9 — повторной доставки не было: ключ, записанный "
            "до первой попытки, защитил от дубля.\n\n"
            "**Итог.** Офлайн — не стоп-кран: набирай и сканируй, "
            "терминал дошлёт сам."
        ),
        details_en=(
            "**Result demonstration.** The outbox is empty, the "
            "bin holds exactly 9 — no re-delivery: the key written "
            "before the first attempt prevented a duplicate.\n\n"
            "**Summary.** Offline is not a stop sign: keep "
            "scanning, the terminal ships it itself."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="tsd-document-container-move",
    doc_slug="stock-tsd-document-container-move",
    title="Задание на паллету: документ ведёт перевоз тары",
    title_en="Pallet task: the document drives container hauling",
    description=(
        "**Для чего:** отгрузка целой паллеты — диспетчер отпустил "
        "накладную со стратегией «минимум тары», система "
        "зарезервировала паллету целиком и выдала задание «увезти "
        "тару», а не «набрать штуки».\n\n"
        "**Какие проблемы решает:** backend сам выбирает поток по "
        "kind строки документа — терминал просит скан тары, затем "
        "приёмник; товар разбирать не нужно.\n\n"
        "**Результат:** паллета со всем содержимым переехала в "
        "зону отгрузки одним коммитом."
    ),
    description_en=(
        "**Purpose:** shipping a whole pallet — the dispatcher "
        "released an order with the «least containers» strategy, "
        "the system reserved a full pallet and issued a «haul the "
        "container» task instead of «pick pieces».\n\n"
        "**Problems solved:** the backend picks the flow from the "
        "document line kind — the terminal asks for the container "
        "scan, then the destination; nothing needs unpacking.\n\n"
        "**Result:** the pallet with all contents moved to the "
        "shipping zone in one commit."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_tsd_document_container_move(
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
    uom_id = seed["uom_id"]

    # --- Паллета в ячейке А с однородным товаром, покрывающим заказ ---
    ctype = await stock_rest(
        page, "POST", "/container-types",
        {"warehouse_id": warehouse_id, "name": f"Паллета {unique_id[:4]}", "kind": "pallet"},
    )
    pallet = await stock_rest(
        page, "POST", "/containers",
        {
            "warehouse_id": warehouse_id,
            "parent_location_id": bin_a["location_id"],
            "container_type_id": ctype["container_type_id"],
            "name": f"Паллета {unique_id[:4]}",
            "barcode": f"PAL-{unique_id[:6]}",
        },
    )
    await tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": pallet["location_id"], "product_id": product_1["product_id"], "quantity": "5"},
        ],
    )
    # «Минимум тары» на товаре — резерв возьмёт паллету целиком.
    await stock_rest(
        page, "PATCH", f"/products/{product_1['product_id']}",
        {"product_id": product_1["product_id"], "removal_strategy": "least_containers"},
    )

    # --- Накладная на отгрузку 5 шт → assign → container-строка ---
    op_types = await stock_rest(
        page, "GET", f"/operation-types?warehouse_id={warehouse_id}"
    )
    outgoing_id = next(
        ot["operation_type_id"] for ot in op_types["items"] if ot["code"] == "outgoing"
    )
    transfer = await stock_rest(
        page, "POST", "/transfers",
        {
            "warehouse_id": warehouse_id,
            "operation_type_id": outgoing_id,
            "barcode": f"DOC-{unique_id[:6]}",
            "moves": [
                {
                    "product_id": product_1["product_id"],
                    "product_qty": "5",
                    "uom_id": uom_id,
                    "location_id": bin_a["location_id"],
                    "location_dest_id": bin_b["location_id"],
                },
            ],
        },
    )
    await stock_rest(page, "POST", f"/transfers/{transfer['transfer_id']}/confirm")
    await stock_rest(page, "POST", f"/transfers/{transfer['transfer_id']}/assign")

    await tsd_pick_warehouse(page, unique_id)

    # --- Скан накладной → вход в исполнение → поток «перевоз тары» ---
    await tsd_scan(page, f"DOC-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(transfer["name"], timeout=15_000)
    await scenario.step(
        "Накладная резервировала паллету целиком",
        page,
        screenshot_name="tsd-doc-container-card",
        label_en="The order reserved the whole pallet",
        details=(
            "Стратегия «минимум тары» нашла однородную паллету, "
            "покрывающую заказ: строка задания — «увезти тару», а "
            "не «набрать 5 штук». Карточка документа предлагает "
            "начать исполнение."
        ),
        details_en=(
            "The «least containers» strategy found a homogeneous "
            "pallet covering the order: the task line says «haul "
            "the container», not «pick 5 pieces». The document "
            "card offers to start execution."
        ),
    )
    await sheet.locator(".action").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)
    # Сессия открывается на шаге 'start' — машина уже ждёт скан тары
    # (expected = строка kind=container). 'container' — это переход
    # ПОСЛЕ скана, ждать его до скана бессмысленно.
    await tsd_scan(page, f"PAL-{unique_id[:6]}")
    await tsd_wait_step(page, "dest")
    await tsd_scan(page, f"BIN-B-{unique_id[:6]}")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await scenario.step(
        "Поток просил тару, затем приёмник",
        page,
        screenshot_name="tsd-doc-container-review",
        label_en="The flow asked for the container, then destination",
        details=(
            "Backend выбрал поток по kind строки: сначала скан "
            "паллеты, потом ячейки-приёмника. Разбирать тару и "
            "пересканировать содержимое не нужно."
        ),
        details_en=(
            "The backend picked the flow from the line kind: "
            "first the pallet scan, then the destination bin. No "
            "unpacking or re-scanning the contents."
        ),
    )
    await tsd_commit(page)

    # --- Тара переехала под приёмник со всем содержимым ---
    locations = await stock_rest(page, "GET", "/locations")
    moved = next(
        loc for loc in locations["items"]
        if loc["location_id"] == pallet["location_id"]
    )
    assert moved["parent_id"] == bin_b["location_id"], f"паллета не переехала: {moved}"
    qty = await stock_quant_qty(
        page, warehouse_id, product_1["product_id"], pallet["location_id"]
    )
    assert qty == Decimal("5")
    await scenario.step(
        "Паллета под новой ячейкой — товар ехал внутри",
        page,
        screenshot_name="tsd-doc-container-done",
        label_en="Pallet under the new bin — goods rode inside",
        details=(
            "**Демонстрация результата.** Контейнер переподвешен "
            "под ячейку Б, все 5 кофе остались внутри — физически "
            "и в системе это была одна операция «перевезти тару».\n\n"
            "**Итог.** Документ сам выбрал поток перевозки: скан "
            "накладной → паллета → приёмник → проводка."
        ),
        details_en=(
            "**Result demonstration.** The container re-hung under "
            "bin B, all 5 coffee units still inside — physically "
            "and in the system it was a single «haul the "
            "container» operation.\n\n"
            "**Summary.** The document picked the hauling flow "
            "itself: order scan → pallet → destination → commit."
        ),
    )
