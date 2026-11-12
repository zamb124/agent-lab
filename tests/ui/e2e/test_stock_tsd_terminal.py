"""Документационный сценарий Stock TSD: терминал оператора `/stock/tsd`.

Физический маршрут приёмки: выбор склада → скан товара → карточка с
остатками → «Принять» → скан ячейки → количество → проводка. Сканы
идут по нативному каналу `stock/tsd:native_scan` — тому же контракту,
что аппаратный сканер и DataWedge-мост Capacitor-оболочки.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.stock_e2e_helpers import stock_e2e_op
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

# ТСД — портретный экран терминала: сценарий снимается в формате
# реального устройства оператора.
_TSD = ViewportSize(width=430, height=900)


async def _tsd_scan(page: Page, code: str) -> None:
    """Скан через нативный канал: тот же вход, что DataWedge/intent
    Capacitor-оболочки и hardware-кейборд-сканер после эвристики."""
    await page.evaluate(
        "(code) => window.dispatchEvent("
        "new CustomEvent('stock/tsd:native_scan', { detail: { code } }))",
        code,
    )


async def _tsd_wait_step(page: Page, step: str) -> None:
    """Ожидание шага скан-машины: оператор физически ждёт подсказку
    экрана перед следующим сканом — следующий шаг возможен только
    после ответа scan_step на предыдущий."""
    await page.wait_for_function(
        """(step) => {
            const s = window.__PLATFORM_BUS__.getState();
            return s.stockTsdSession?.context?.step === step;
        }""",
        arg=step,
        timeout=15_000,
    )


async def _tsd_open(page: Page, stock_ui: AppUI) -> None:
    await page.goto(
        f"{stock_ui.origin}/stock/tsd", wait_until="domcontentloaded"
    )
    await expect(page.locator("stock-tsd-app")).to_be_visible(timeout=30_000)
    await expect(page.locator("stock-tsd-home-page")).to_be_visible(
        timeout=30_000
    )
    await page.wait_for_function(
        """() => {
            const bus = window.__PLATFORM_BUS__;
            if (!bus || typeof bus.getState !== 'function') return false;
            return bus.getState()?.network?.ws?.status === 'open';
        }""",
        timeout=30_000,
    )


async def _tsd_qty(page: Page, digits: str) -> None:
    """Набор количества на экранной клавиатуре + подтверждение."""
    for ch in digits:
        key = page.locator("stock-tsd-run .numpad button", has_text=ch).first
        await expect(key).to_be_visible(timeout=10_000)
        await key.click()
    ok = page.locator("stock-tsd-run .numpad button.ok")
    await expect(ok).to_be_enabled(timeout=10_000)
    await ok.click()


async def _tsd_commit(page: Page) -> None:
    btn = page.locator("stock-tsd-run .commit-btn")
    await expect(btn).to_be_enabled(timeout=10_000)
    await btn.click()
    # Успешный коммит закрывает сессию — run-экран уходит, возвращается рабочий стол.
    await expect(page.locator("stock-tsd-run")).to_have_count(0, timeout=30_000)


async def _stock_rest(
    page: Page, method: str, path: str, payload: dict[str, Any] | None = None
) -> Any:
    """REST-зеркало stock op'ов для подготовки данных: у ТСД нет
    фабрик справочников, контракт тот же — `POST /stock/api/v1/...`."""
    parts = urlsplit(page.url)
    resp = await page.request.fetch(
        f"{parts.scheme}://{parts.netloc}/stock/api/v1{path}",
        method=method,
        data=payload,
    )
    assert resp.ok, f"{method} {path} → {resp.status}: {await resp.text()}"
    return await resp.json()


async def _quant_row(
    page: Page, warehouse_id: str, product_id: str, location_id: str
) -> dict[str, Any]:
    quants: dict[str, Any] = await stock_e2e_op(
        page,
        "stock/quants",
        "stock/quants/list_requested",
        {"warehouse_id": warehouse_id, "product_id": product_id},
    )
    rows = [q for q in quants["items"] if q["location_id"] == location_id]
    assert len(rows) == 1, f"ожидался quant {product_id}@{location_id}: {quants}"
    return rows[0]


async def _quant_qty(
    page: Page, warehouse_id: str, product_id: str, location_id: str
) -> Decimal:
    return Decimal(
        str((await _quant_row(page, warehouse_id, product_id, location_id))["quantity"])
    )


async def _tsd_seed_warehouse(
    page: Page, unique_id: str
) -> dict[str, Any]:
    """Типовая топология ТСД-сценария: склад, зона-view, две ячейки
    с баркодами и два товара с баркодами. Данные создаются через
    REST-зеркала op'ов — тот же контракт, что и у SPA."""
    warehouse = await _stock_rest(
        page, "POST", "/warehouses",
        {"code": f"0-{unique_id[:8].upper()}", "name": f"Склад {unique_id[:4]}"},
    )
    zone = await _stock_rest(
        page, "POST", "/locations",
        {
            "warehouse_id": warehouse["warehouse_id"],
            "name": f"Зона {unique_id[:4]}",
            "usage": "view",
        },
    )
    bin_a = await _stock_rest(
        page, "POST", "/locations",
        {
            "warehouse_id": warehouse["warehouse_id"],
            "parent_id": zone["location_id"],
            "name": f"Ячейка А{unique_id[:3]}",
            "usage": "bin",
            "barcode": f"BIN-A-{unique_id[:6]}",
        },
    )
    bin_b = await _stock_rest(
        page, "POST", "/locations",
        {
            "warehouse_id": warehouse["warehouse_id"],
            "parent_id": zone["location_id"],
            "name": f"Ячейка Б{unique_id[:3]}",
            "usage": "bin",
            "barcode": f"BIN-B-{unique_id[:6]}",
        },
    )
    uoms = await _stock_rest(page, "GET", "/uoms")
    uom_id = next(u["uom_id"] for u in uoms["items"] if u["name"] == "Units")
    product_1 = await _stock_rest(
        page, "POST", "/products",
        {
            "name": f"Кофе зерновой {unique_id[:4]}",
            "sku": f"BEAN-{unique_id[:6]}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "standard_price": "0",
            "tracking": "none",
            "is_storable": True,
            "barcodes": [f"BC-1-{unique_id[:6]}"],
        },
    )
    product_2 = await _stock_rest(
        page, "POST", "/products",
        {
            "name": f"Чай листовой {unique_id[:4]}",
            "sku": f"TEA-{unique_id[:6]}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "standard_price": "0",
            "tracking": "none",
            "is_storable": True,
            "barcodes": [f"BC-2-{unique_id[:6]}"],
        },
    )
    return {
        "warehouse": warehouse,
        "zone": zone,
        "bin_a": bin_a,
        "bin_b": bin_b,
        "product_1": product_1,
        "product_2": product_2,
        "uom_id": uom_id,
    }


async def _tsd_seed_stock(
    page: Page,
    warehouse_id: str,
    lines: list[dict[str, Any]],
) -> None:
    """Положить товар на локацию тем же adhoc-commit, что ходит с ТСД:
    многострочный receive-контекст → один входящий документ."""
    await _stock_rest(
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
                        "location_dest_id": line["location_dest_id"],
                        "product_id": line["product_id"],
                        "quantity": str(line["quantity"]),
                    }
                    for line in lines
                ],
            },
        },
    )


async def _tsd_pick_warehouse(page: Page, unique_id: str) -> None:
    """Выбор склада текущего прогона: компания воркера общая, склады
    копятся между прогонами — кликаем карточку по имени, а не первую.
    Список складов грузится один раз при монтировании — перезагружаем
    страницу после сидирования, иначе свежий склад гонится с autoload."""
    await page.reload(wait_until="domcontentloaded")
    await expect(page.locator("stock-tsd-home-page")).to_be_visible(
        timeout=30_000
    )
    card = page.locator(
        "stock-tsd-home-page .warehouse-card",
        has_text=f"Склад {unique_id[:4]}",
    )
    await expect(card).to_be_visible(timeout=30_000)
    await card.click()


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
    await page.set_viewport_size(_TSD)
    await _tsd_open(page, stock_ui)

    # --- Набор данных через REST-зеркала op'ов (у ТСД нет фабрик справочников) ---
    seed = await _tsd_seed_warehouse(page, unique_id)
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
    await _tsd_scan(page, f"BC-1-{unique_id[:6]}")
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
    await _tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await expect(run.locator(".qty-panel")).to_be_visible(timeout=15_000)
    await _tsd_qty(page, "5")
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
    await _tsd_commit(page)

    # --- Приёмка товара 2 в другую ячейку тем же маршрутом ---
    await _tsd_scan(page, f"BC-2-{unique_id[:6]}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator(".action[data-action='receive']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    await expect(run).to_be_visible(timeout=15_000)
    await _tsd_scan(page, f"BIN-B-{unique_id[:6]}")
    await expect(run.locator(".qty-panel")).to_be_visible(timeout=15_000)
    await _tsd_qty(page, "12")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await _tsd_commit(page)

    # --- Проводки проверяем леджером, не глазами ---
    qty_1 = await _quant_qty(page, warehouse_id, product_1["product_id"], bin_a["location_id"])
    qty_2 = await _quant_qty(page, warehouse_id, product_2["product_id"], bin_b["location_id"])
    assert qty_1 == Decimal("5")
    assert qty_2 == Decimal("12")

    # --- Скан ячейки: содержимое с остатками обоих приёмок ---
    await _tsd_scan(page, f"BIN-A-{unique_id[:6]}")
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
    await page.set_viewport_size(_TSD)
    await _tsd_open(page, stock_ui)

    # --- Топология и остаток на ячейке А ---
    seed = await _tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    bin_b = seed["bin_b"]
    product_1 = seed["product_1"]
    product_2 = seed["product_2"]
    await _tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "5"},
            {"location_dest_id": bin_a["location_id"], "product_id": product_2["product_id"], "quantity": "8"},
        ],
    )

    await _tsd_pick_warehouse(page, unique_id)

    # --- Скан товара: карточка показывает, где он лежит ---
    await _tsd_scan(page, f"BC-1-{unique_id[:6]}")
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
    await _tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await _tsd_wait_step(page, "dest")
    await _tsd_scan(page, f"BIN-B-{unique_id[:6]}")
    await expect(run.locator(".qty-panel")).to_be_visible(timeout=15_000)
    await _tsd_qty(page, "2")
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
    await _tsd_commit(page)

    # --- Перенос 2 тем же маршрутом ---
    await _tsd_scan(page, f"BC-2-{unique_id[:6]}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator(".action[data-action='move']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    await expect(run).to_be_visible(timeout=15_000)
    await _tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await _tsd_wait_step(page, "dest")
    await _tsd_scan(page, f"BIN-B-{unique_id[:6]}")
    await expect(run.locator(".qty-panel")).to_be_visible(timeout=15_000)
    await _tsd_qty(page, "3")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await _tsd_commit(page)

    # --- Остатки после двух переносов ---
    assert await _quant_qty(page, warehouse_id, product_1["product_id"], bin_a["location_id"]) == Decimal("3")
    assert await _quant_qty(page, warehouse_id, product_2["product_id"], bin_a["location_id"]) == Decimal("5")
    assert await _quant_qty(page, warehouse_id, product_1["product_id"], bin_b["location_id"]) == Decimal("2")
    assert await _quant_qty(page, warehouse_id, product_2["product_id"], bin_b["location_id"]) == Decimal("3")

    # --- Скан ячейки Б: оба перенесённых товара на месте ---
    await _tsd_scan(page, f"BIN-B-{unique_id[:6]}")
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
    await page.set_viewport_size(_TSD)
    await _tsd_open(page, stock_ui)

    # --- Топология и остаток на ячейке А ---
    seed = await _tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    product_1 = seed["product_1"]
    product_2 = seed["product_2"]
    await _tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "5"},
            {"location_dest_id": bin_a["location_id"], "product_id": product_2["product_id"], "quantity": "8"},
        ],
    )

    await _tsd_pick_warehouse(page, unique_id)

    # --- Скан ячейки: карточка с содержимым и действием «Посчитать» ---
    await _tsd_scan(page, f"BIN-A-{unique_id[:6]}")
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
    await _tsd_scan(page, f"BC-1-{unique_id[:6]}")
    await expect(run.locator(".qty-panel")).to_be_visible(timeout=15_000)
    await _tsd_qty(page, "4")
    # После первой строки машина снова ждёт товар — ячейка удержана.
    await _tsd_wait_step(page, "review")
    await _tsd_scan(page, f"BC-2-{unique_id[:6]}")
    await _tsd_wait_step(page, "quantity")
    await _tsd_qty(page, "7")
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
    await _tsd_commit(page)

    # --- Факт пересчёта записан на остатки (дельта уходит на утверждение) ---
    row_1 = await _quant_row(page, warehouse_id, product_1["product_id"], bin_a["location_id"])
    row_2 = await _quant_row(page, warehouse_id, product_2["product_id"], bin_a["location_id"])
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
    await page.set_viewport_size(_TSD)
    await _tsd_open(page, stock_ui)

    # --- Топология + паллета с остатком внутри ---
    seed = await _tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    bin_b = seed["bin_b"]
    product_1 = seed["product_1"]
    # Паллета стоит в ячейке А: дети допустимы только под view/container/bin.
    pallet_type = await _stock_rest(
        page, "POST", "/container-types",
        {
            "warehouse_id": warehouse_id,
            "name": f"Европаллета {unique_id[:4]}",
            "kind": "pallet",
        },
    )
    pallet = await _stock_rest(
        page, "POST", "/containers",
        {
            "warehouse_id": warehouse_id,
            "parent_location_id": bin_a["location_id"],
            "container_type_id": pallet_type["container_type_id"],
            "name": f"Паллета {unique_id[:4]}",
            "barcode": f"PLT-{unique_id[:6]}",
        },
    )
    await _tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": pallet["location_id"], "product_id": product_1["product_id"], "quantity": "10"},
        ],
    )

    await _tsd_pick_warehouse(page, unique_id)

    # --- Скан паллеты: карточка тары с содержимым ---
    await _tsd_scan(page, f"PLT-{unique_id[:6]}")
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
    await _tsd_scan(page, f"BIN-B-{unique_id[:6]}")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await _tsd_commit(page)

    # --- Паллета переподвешена под ячейку Б, остаток поехал с ней ---
    locations = await _stock_rest(page, "GET", "/locations", )
    moved = next(
        loc for loc in locations["items"]
        if loc["location_id"] == pallet["location_id"]
    )
    assert moved["parent_id"] == bin_b["location_id"]
    assert await _quant_qty(page, warehouse_id, product_1["product_id"], pallet["location_id"]) == Decimal("10")
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
    await page.set_viewport_size(_TSD)
    await _tsd_open(page, stock_ui)

    # --- Топология, остаток и накладная на отгрузку с баркодом ---
    seed = await _tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    product_1 = seed["product_1"]
    product_2 = seed["product_2"]
    uom_id = seed["uom_id"]
    await _tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "5"},
            {"location_dest_id": bin_a["location_id"], "product_id": product_2["product_id"], "quantity": "8"},
        ],
    )
    op_types = await _stock_rest(
        page, "GET", f"/operation-types?warehouse_id={warehouse_id}"
    )
    outgoing_id = next(
        ot["operation_type_id"] for ot in op_types["items"] if ot["code"] == "outgoing"
    )
    transfer = await _stock_rest(
        page, "POST", "/transfers",
        {
            "warehouse_id": warehouse_id,
            "operation_type_id": outgoing_id,
            "barcode": f"DOC-{unique_id[:6]}",
            "moves": [
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
        },
    )
    await _stock_rest(page, "POST", f"/transfers/{transfer['transfer_id']}/confirm")
    await _stock_rest(page, "POST", f"/transfers/{transfer['transfer_id']}/assign")

    await _tsd_pick_warehouse(page, unique_id)

    # --- Скан накладной: карточка документа и вход в исполнение ---
    await _tsd_scan(page, f"DOC-{unique_id[:6]}")
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
    await expect(sheet).to_have_count(0, timeout=15_000)
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
    await _tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await _tsd_wait_step(page, "product")
    await _tsd_scan(page, f"BC-1-{unique_id[:6]}")
    await _tsd_wait_step(page, "quantity")
    await _tsd_qty(page, "4")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await _tsd_commit(page)

    # --- Позиция 2: повторный скан накладной открывает следующий move ---
    await _tsd_scan(page, f"DOC-{unique_id[:6]}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator("button.action").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    await expect(run).to_be_visible(timeout=15_000)
    expected_2 = run.locator(".expected")
    await expect(expected_2).to_contain_text(f"Чай листовой {unique_id[:4]}", timeout=15_000)
    await _tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await _tsd_wait_step(page, "product")
    await _tsd_scan(page, f"BC-2-{unique_id[:6]}")
    await _tsd_wait_step(page, "quantity")
    await _tsd_qty(page, "6")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await _tsd_commit(page)

    # --- Обе позиции проведены: остаток ячейки уменьшен по леджеру ---
    assert await _quant_qty(page, warehouse_id, product_1["product_id"], bin_a["location_id"]) == Decimal("1")
    assert await _quant_qty(page, warehouse_id, product_2["product_id"], bin_a["location_id"]) == Decimal("2")
    moves = await _stock_rest(
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
            "проведены леджером: кофе 5 → 1, чай 8 → 2 — ровно по "
            "спецификациям документа.\n\n"
            "**Итог.** Работа по документу: скан накладной → "
            "«Начать» → подсказка позиции → ячейка → товар → "
            "количество → проводка."
        ),
        details_en=(
            "**Result demonstration.** Both order lines were posted "
            "to the ledger: coffee 5 → 1, tea 8 → 2 — exactly per "
            "the document specs.\n\n"
            "**Summary.** Document work: scan the order → «Start» → "
            "line hint → bin → product → qty → commit."
        ),
    )


async def _tsd_seed_document(
    page: Page,
    warehouse_id: str,
    unique_id: str,
    moves: list[dict[str, Any]],
    *,
    code: str = "outgoing",
    scan_flow: str | None = None,
) -> dict[str, Any]:
    """Накладная с баркодом под ТСД-исполнение: тип операции по коду,
    при необходимости — явный поток плеча (pack/ship)."""
    op_types = await _stock_rest(
        page, "GET", f"/operation-types?warehouse_id={warehouse_id}"
    )
    op_type = next(ot for ot in op_types["items"] if ot["code"] == code)
    if scan_flow is not None:
        op_type = await _stock_rest(
            page, "PATCH", f"/operation-types/{op_type['operation_type_id']}",
            {"operation_type_id": op_type["operation_type_id"], "scan_flow": scan_flow},
        )
    transfer = await _stock_rest(
        page, "POST", "/transfers",
        {
            "warehouse_id": warehouse_id,
            "operation_type_id": op_type["operation_type_id"],
            "barcode": f"DOC-{unique_id[:6]}",
            "moves": moves,
        },
    )
    await _stock_rest(page, "POST", f"/transfers/{transfer['transfer_id']}/confirm")
    await _stock_rest(page, "POST", f"/transfers/{transfer['transfer_id']}/assign")
    return transfer


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
    await page.set_viewport_size(_TSD)
    await _tsd_open(page, stock_ui)

    # --- Топология, остаток, пустой короб и накладная «pack» ---
    seed = await _tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    bin_b = seed["bin_b"]
    product_1 = seed["product_1"]
    uom_id = seed["uom_id"]
    await _tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "5"},
        ],
    )
    box_type = await _stock_rest(
        page, "POST", "/container-types",
        {
            "warehouse_id": warehouse_id,
            "name": f"Короб {unique_id[:4]}",
            "kind": "box",
        },
    )
    box = await _stock_rest(
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
    _ = await _tsd_seed_document(
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

    await _tsd_pick_warehouse(page, unique_id)

    # --- Скан накладной → исполнение: backend выбрал поток «упаковка» ---
    await _tsd_scan(page, f"DOC-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator("button.action").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)

    # --- Товар → тара → количество ---
    await _tsd_scan(page, f"BC-1-{unique_id[:6]}")
    await _tsd_wait_step(page, "container")
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
    await _tsd_scan(page, f"BOX-{unique_id[:6]}")
    await _tsd_wait_step(page, "quantity")
    await _tsd_qty(page, "3")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await _tsd_commit(page)

    # --- Остаток переехал с ячейки в короб ---
    assert await _quant_qty(page, warehouse_id, product_1["product_id"], bin_a["location_id"]) == Decimal("2")
    assert await _quant_qty(page, warehouse_id, product_1["product_id"], box["location_id"]) == Decimal("3")

    # --- Скан короба: карточка тары показывает уложенный товар ---
    await _tsd_scan(page, f"BOX-{unique_id[:6]}")
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
    await page.set_viewport_size(_TSD)
    await _tsd_open(page, stock_ui)

    # --- Топология, остаток и накладная «ship» на два товара ---
    seed = await _tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    product_1 = seed["product_1"]
    product_2 = seed["product_2"]
    uom_id = seed["uom_id"]
    await _tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "5"},
            {"location_dest_id": bin_a["location_id"], "product_id": product_2["product_id"], "quantity": "8"},
        ],
    )
    transfer = await _tsd_seed_document(
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

    await _tsd_pick_warehouse(page, unique_id)

    # --- Скан накладной → скан ворот → проводка всего плеча ---
    await _tsd_scan(page, f"DOC-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator("button.action").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)
    # ship-поток: единственный скан — отгрузочная ячейка, позиции
    # набирать не нужно — документ уже знает свой состав.
    await _tsd_scan(page, f"BIN-B-{unique_id[:6]}")
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
    await _tsd_commit(page)

    # --- Плечо второго товара: повторный скан накладной ---
    await _tsd_scan(page, f"DOC-{unique_id[:6]}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator("button.action").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    await expect(run).to_be_visible(timeout=15_000)
    await _tsd_scan(page, f"BIN-B-{unique_id[:6]}")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await _tsd_commit(page)

    # --- Все строки проведены: ячейка пуста по обоим позициям накладной ---
    assert await _quant_qty(page, warehouse_id, product_1["product_id"], bin_a["location_id"]) == Decimal("1")
    assert await _quant_qty(page, warehouse_id, product_2["product_id"], bin_a["location_id"]) == Decimal("2")
    detail = await _stock_rest(page, "GET", f"/transfers/{transfer['transfer_id']}")
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
    await page.set_viewport_size(_TSD)
    await _tsd_open(page, stock_ui)

    # --- Топология и сток на стейдже ---
    seed = await _tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    bin_b = seed["bin_b"]
    product_1 = seed["product_1"]
    await _tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "5"},
        ],
    )

    await _tsd_pick_warehouse(page, unique_id)

    # --- Скан товара на стейдже → действие «Разместить» ---
    await _tsd_scan(page, f"BC-1-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator("[data-action='putaway']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)

    # --- Подтверждение стейджа → целевая ячейка → количество ---
    await _tsd_wait_step(page, "location")
    await _tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await _tsd_wait_step(page, "dest")
    await _tsd_scan(page, f"BIN-B-{unique_id[:6]}")
    await _tsd_wait_step(page, "quantity")
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
    await _tsd_qty(page, "3")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await _tsd_commit(page)

    # --- Остаток переехал со стейджа в хранение ---
    assert await _quant_qty(page, warehouse_id, product_1["product_id"], bin_a["location_id"]) == Decimal("2")
    assert await _quant_qty(page, warehouse_id, product_1["product_id"], bin_b["location_id"]) == Decimal("3")

    # --- Скан ячейки приёмника: содержимое показывает размещённый товар ---
    await _tsd_scan(page, f"BIN-B-{unique_id[:6]}")
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
    await page.set_viewport_size(_TSD)
    await _tsd_open(page, stock_ui)

    # --- Топология, сток и накладная «pick» на 4 шт ---
    seed = await _tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    product_1 = seed["product_1"]
    uom_id = seed["uom_id"]
    await _tsd_seed_stock(
        page,
        warehouse_id,
        [
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "4"},
        ],
    )
    transfer = await _tsd_seed_document(
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

    await _tsd_pick_warehouse(page, unique_id)

    # --- Скан накладной → исполнение отбора ---
    await _tsd_scan(page, f"DOC-{unique_id[:6]}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator("button.action").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
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
    detail = await _stock_rest(page, "GET", f"/transfers/{transfer['transfer_id']}")
    assert Decimal(str(detail["lines"][0]["quantity"])) == Decimal("2"), detail["lines"]
    quant = await _quant_row(page, warehouse_id, product_1["product_id"], bin_a["location_id"])
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
    await expect(run).to_be_visible(timeout=15_000)
    # Пересчёт физически: дошёл до ячейки → скан ячейки → скан товара → факт.
    await _tsd_scan(page, f"BIN-A-{unique_id[:6]}")
    await _tsd_wait_step(page, "product")
    await _tsd_scan(page, f"BC-1-{unique_id[:6]}")
    await expect(run.locator(".qty-panel")).to_be_visible(timeout=15_000)
    await _tsd_qty(page, "8")
    await _tsd_wait_step(page, "review")
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
    await _tsd_commit(page)
    await expect(run).to_have_count(0, timeout=15_000)

    # --- Задание пересчёта закрыто фактом — не висит в очереди вечно ---
    detail = await _stock_rest(page, "GET", f"/transfers/{transfer['transfer_id']}")
    count_lines = [ln for ln in detail["lines"] if ln.get("kind") == "count"]
    assert len(count_lines) == 1, detail["lines"]
    assert count_lines[0]["state"] == "done", count_lines[0]
