"""Документационные сценарии Stock: новые админ-страницы.

Рабочее место диспетчера склада: волны сборки, партии и сроки
годности (FEFO), полный редактор типов операций и рефлекс-решения
о размещении — всё, что раньше требовало прямого доступа к API.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.stock_e2e_helpers import (
    stock_e2e_nav,
    stock_e2e_open,
    stock_e2e_pick_warehouse,
    stock_rest,
    tsd_seed_document,
    tsd_seed_stock,
    tsd_seed_warehouse,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder


def _expiry(days: int) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).date().isoformat()


@pytest.mark.scenario(
    service="stock",
    tag="transfers",
    doc_slug="stock-admin-waves",
    title="Волны сборки: объединить строки заказов в одну волну",
    title_en="Pick waves: group order lines into one wave",
    description=(
        "**Для чего:** утром у диспетчера десятки накладных на "
        "отгрузку — оператору удобнее забрать позиции нескольких "
        "заказов одним обходом стеллажей, чем бегать по каждому "
        "документу.\n\n"
        "**Какие проблемы решает:** страница «Волны» показывает все "
        "свободные строки отбора склада — диспетчер отмечает нужные, "
        "называет волну и выпускает её в работу одной кнопкой.\n\n"
        "**Результат:** строки двух позиций объединены в волну "
        "«Утренняя», волна выпущена — её строки видны операторам "
        "терминалов как задания."
    ),
    description_en=(
        "**Purpose:** in the morning a dispatcher faces dozens of "
        "outbound orders — an operator prefers picking lines of "
        "several orders in one rack pass instead of visiting every "
        "document.\n\n"
        "**Problems solved:** the «Waves» page lists every free "
        "pick line of the warehouse — the dispatcher ticks the "
        "ones needed, names the wave and releases it to work "
        "with one button.\n\n"
        "**Result:** two lines merged into the «Morning» wave, "
        "the wave released — its lines appear to handheld "
        "operators as tasks."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_admin_waves(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await stock_e2e_open(page, stock_ui)

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
            {"location_dest_id": bin_a["location_id"], "product_id": product_1["product_id"], "quantity": "9"},
            {"location_dest_id": bin_a["location_id"], "product_id": product_2["product_id"], "quantity": "7"},
        ],
    )
    transfer = await tsd_seed_document(
        page,
        warehouse_id,
        unique_id,
        [
            {
                "product_id": product_1["product_id"],
                "product_qty": "3",
                "uom_id": uom_id,
                "location_id": bin_a["location_id"],
            },
            {
                "product_id": product_2["product_id"],
                "product_qty": "4",
                "uom_id": uom_id,
                "location_id": bin_a["location_id"],
            },
        ],
    )
    assert transfer["transfer_id"] != ""

    await stock_e2e_nav(page, "stock_waves", page_selector="stock-waves-page")
    waves_page = page.locator("stock-waves-page")
    await stock_e2e_pick_warehouse(waves_page, f"Склад {unique_id[:4]}")

    open_rows = waves_page.locator("input[data-line]")
    await expect(open_rows).to_have_count(2, timeout=20_000)
    await scenario.step(
        "Откройте «Волны» и выберите склад",
        page,
        screenshot_name="waves-open-lines",
        label_en="Open «Waves» and pick the warehouse",
        details=(
            "Раздел «Накладные → Волны» показывает свободные "
            "строки отбора склада: товар, ячейка-источник, "
            "направление и количество. Это физически исполнимая "
            "работа, ещё не закреплённая ни за кем."
        ),
        details_en=(
            "«Orders → Waves» lists the warehouse's free pick "
            "lines: product, source bin, direction and quantity. "
            "This is physically executable work not yet claimed "
            "by anyone."
        ),
    )
    await open_rows.nth(0).check()
    await open_rows.nth(1).check()
    await waves_page.locator(".wave-create-bar platform-field").evaluate(
        """(el) => {
            el.value = "Утренняя";
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value: 'Утренняя' }, bubbles: true, composed: true,
            }));
        }"""
    )
    create_btn = waves_page.locator("[data-create-wave]")
    await expect(create_btn).to_be_enabled(timeout=10_000)
    await create_btn.click()

    wave_row = waves_page.locator("tr", has_text="Утренняя").first
    await expect(wave_row).to_be_visible(timeout=20_000)
    await expect(wave_row.locator(".wave-state")).to_contain_text(
        "Черновик", timeout=10_000
    )
    await scenario.step(
        "Соберите волну из отмеченных строк",
        page,
        screenshot_name="wave-created",
        label_en="Build a wave from the ticked lines",
        details=(
            "Отметьте строки, которые оператор заберёт одним "
            "обходом, впишите имя волны и нажмите «Создать». "
            "Волна появляется черновиком — её ещё можно "
            "переосмыслить до выпуска."
        ),
        details_en=(
            "Tick the lines an operator will grab in one pass, "
            "type the wave name and press «Create». The wave "
            "appears as a draft — it can still be rethought "
            "before release."
        ),
    )
    await wave_row.locator("[data-release]").click()
    await expect(wave_row.locator(".wave-state")).to_contain_text(
        "Выпущена", timeout=20_000
    )
    waves = await stock_rest(
        page, "POST", "/waves/list", {"warehouse_id": warehouse_id}
    )
    assert any(w["name"] == "Утренняя" and w["state"] == "released" for w in waves["items"])
    await scenario.step(
        "Выпустите волну в работу",
        page,
        screenshot_name="wave-released",
        label_en="Release the wave to work",
        details=(
            "**Демонстрация результата.** Кнопка «Выпустить» у "
            "черновика переводит волну в работу: статус строки "
            "меняется на «Выпущена», а её позиции уходят "
            "операторам терминалов как задания с пометкой "
            "волны.\n\n"
            "**Итог.** Волны объединяют отбор нескольких заказов "
            "в один обход: свободные строки → отметить → имя → "
            "«Создать» → «Выпустить»."
        ),
        details_en=(
            "**Result demonstration.** The «Release» button on a "
            "draft sends the wave to work: the row state changes "
            "to «Released» and its lines reach handheld "
            "operators as wave-tagged tasks.\n\n"
            "**Summary.** Waves merge picking of several orders "
            "into one pass: free lines → tick → name → "
            "«Create» → «Release»."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="locations",
    doc_slug="stock-admin-lots",
    title="Партии и сроки годности: FEFO-карта склада",
    title_en="Lots and expiry: the warehouse FEFO board",
    description=(
        "**Для чего:** диспетчер должен видеть, какие партии "
        "скоро испортятся, чтобы ускорить их отгрузку или "
        "списание — до того как срок выйдет.\n\n"
        "**Какие проблемы решает:** страница «Партии» собирает "
        "все партии склада в таблицу со сроками «годен до», "
        "«лучше до», «отобрать до» и цветным статусом FEFO — "
        "просроченные подсвечены, фильтр по товару сужает "
        "обзор.\n\n"
        "**Результат:** две партии видны со сроками и статусами, "
        "новая партия заведена через форму без терминала."
    ),
    description_en=(
        "**Purpose:** a dispatcher must see which lots expire "
        "soon to speed up their shipment or write-off — before "
        "the date passes.\n\n"
        "**Problems solved:** the «Lots» page gathers every "
        "warehouse lot into a table with «best before», "
        "«use by», «remove by» dates and a colour FEFO badge — "
        "expired ones are highlighted, a product filter narrows "
        "the view.\n\n"
        "**Result:** two lots visible with dates and badges, "
        "a new lot registered through the form without a "
        "handheld."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_admin_lots(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await stock_e2e_open(page, stock_ui)

    seed = await tsd_seed_warehouse(page, unique_id)
    uom_id = seed["uom_id"]
    product = await stock_rest(
        page, "POST", "/products",
        {
            "name": f"Сметана {unique_id[:4]}",
            "sku": f"SOUR-{unique_id[:6]}",
            "uom_id": uom_id,
            "valuation_method": "fifo",
            "standard_price": "0",
            "tracking": "lot",
            "is_storable": True,
            "barcodes": [f"BC-S-{unique_id[:6]}"],
        },
    )
    await stock_rest(
        page, "POST", "/lots",
        {
            "product_id": product["product_id"],
            "name": f"LOT-OLD-{unique_id[:6]}",
            "expiration_at": _expiry(5),
        },
    )
    await stock_rest(
        page, "POST", "/lots",
        {
            "product_id": product["product_id"],
            "name": f"LOT-NEW-{unique_id[:6]}",
            "expiration_at": _expiry(90),
        },
    )

    await stock_e2e_nav(page, "stock_lots", page_selector="stock-lots-page")
    lots_page = page.locator("stock-lots-page")
    old_row = lots_page.locator("tr", has_text=f"LOT-OLD-{unique_id[:6]}")
    new_row = lots_page.locator("tr", has_text=f"LOT-NEW-{unique_id[:6]}")
    await expect(old_row).to_be_visible(timeout=20_000)
    await expect(new_row).to_be_visible(timeout=10_000)
    await expect(old_row.locator(".lot-badge")).to_contain_text(
        "Скоро истекает", timeout=10_000
    )
    await expect(new_row.locator(".lot-badge")).to_contain_text(
        "В норме", timeout=10_000
    )
    await scenario.step(
        "Откройте «Партии» — сроки и статусы FEFO",
        page,
        screenshot_name="lots-fefo-table",
        label_en="Open «Lots» — dates and FEFO badges",
        details=(
            "Раздел «Локации → Партии»: каждая партия показывает "
            "«годен до», производные даты и цветной статус — "
            "«скоро истекает» жёлтым, «просрочена» красным. "
            "Фильтр сверху сужает список до одного товара."
        ),
        details_en=(
            "«Locations → Lots»: each lot shows «best before», "
            "derived dates and a colour badge — «expiring soon» "
            "in amber, «expired» in red. The filter above "
            "narrows the list to one product."
        ),
    )
    await lots_page.locator("platform-button", has_text="Создать").click()
    modal = page.locator("stock-entity-form-modal")
    await expect(modal).to_be_visible(timeout=10_000)
    await modal.locator("platform-field").nth(0).evaluate(
        """(el, pid) => {
            el.value = pid;
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value: pid }, bubbles: true, composed: true,
            }));
        }""",
        product["product_id"],
    )
    await modal.locator("platform-field").nth(1).evaluate(
        """(el, name) => {
            el.value = name;
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value: name }, bubbles: true, composed: true,
            }));
        }""",
        f"LOT-NEW2-{unique_id[:6]}",
    )
    await modal.locator("platform-field").nth(2).evaluate(
        """(el, d) => {
            el.value = d;
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value: d }, bubbles: true, composed: true,
            }));
        }""",
        _expiry(30),
    )
    await modal.locator("platform-button", has_text="Сохранить").click()
    new2_row = lots_page.locator("tr", has_text=f"LOT-NEW2-{unique_id[:6]}")
    await expect(new2_row).to_be_visible(timeout=20_000)
    lots = await stock_rest(page, "GET", f"/lots?product_id={product['product_id']}")
    assert f"LOT-NEW2-{unique_id[:6]}" in {l["name"] for l in lots["items"]}
    await scenario.step(
        "Заведите партию через форму",
        page,
        screenshot_name="lot-created",
        label_en="Register a lot through the form",
        details=(
            "**Демонстрация результата.** Кнопка «Создать» "
            "открывает форму партии: товар, номер и «годен до». "
            "Новая строка появляется в таблице со статусом — "
            "партия доступна приёмке и отбору.\n\n"
            "**Итог.** «Партии» — карта сроков склада: фильтр "
            "по товару, статусы FEFO и заведение партий без "
            "терминала."
        ),
        details_en=(
            "**Result demonstration.** «Create» opens the lot "
            "form: product, number and «best before». The new "
            "row appears in the table with a badge — the lot is "
            "available to receiving and picking.\n\n"
            "**Summary.** «Lots» is the warehouse expiry board: "
            "product filter, FEFO badges and lot registration "
            "without a handheld."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="settings",
    doc_slug="stock-admin-operation-types",
    title="Типы операций: политики резервов и партий",
    title_en="Operation types: reservation and lot policies",
    description=(
        "**Для чего:** разные потоки склада ведут себя по-разному: "
        "приёмке можно заводить партии, отгрузке — только брать "
        "существующие, у срочных заказов — резерв сразу при "
        "подтверждении.\n\n"
        "**Какие проблемы решает:** полный редактор типа операции "
        "меняет поведение терминалов без программистов: политику "
        "резерва и недостачи, размещение, автопроводку, поток "
        "сканера и правила партий.\n\n"
        "**Результат:** у типа «Приёмка» выключено заведение "
        "партий и задан префикс номеров — настройки сохранены "
        "и видны в таблице."
    ),
    description_en=(
        "**Purpose:** different warehouse flows behave "
        "differently: receiving may create lots, shipping only "
        "takes existing ones, urgent orders reserve at "
        "confirmation.\n\n"
        "**Problems solved:** the full operation-type editor "
        "changes handheld behaviour without developers: "
        "reservation and backorder policies, putaway, "
        "auto-validation, scanner flow and lot rules.\n\n"
        "**Result:** «Receipt» type has lot creation disabled "
        "and a number prefix set — settings saved and visible "
        "in the table."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_admin_operation_types(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await stock_e2e_open(page, stock_ui)

    seed = await tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]

    await stock_e2e_nav(page, "stock_op_types", page_selector="stock-op-types-page")
    op_page = page.locator("stock-op-types-page")
    await stock_e2e_pick_warehouse(op_page, f"Склад {unique_id[:4]}")

    row = op_page.locator("tr", has_text="Приёмка").first
    await expect(row).to_be_visible(timeout=20_000)
    await scenario.step(
        "Откройте типы операций склада",
        page,
        screenshot_name="op-types-table",
        label_en="Open the warehouse operation types",
        details=(
            "Раздел «Настройки → Типы операций»: каждый тип — "
            "это поведение терминала по своему документу. "
            "Таблица показывает политики резерва, недостачи и "
            "размещения; строка открывает полный редактор."
        ),
        details_en=(
            "«Settings → Operation types»: each type is the "
            "handheld behaviour for its document. The table "
            "shows reservation, backorder and putaway "
            "policies; a row opens the full editor."
        ),
    )
    await row.click()
    modal = page.locator("stock-entity-form-modal")
    await expect(modal).to_be_visible(timeout=10_000)
    await modal.locator("platform-field").nth(1).evaluate(
        """(el, v) => {
            el.value = v;
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value: v }, bubbles: true, composed: true,
            }));
        }""",
        "IN-",
    )
    # create_lots (8-е поле по порядку) — boolean toggle off.
    fields = modal.locator("platform-field")
    await fields.nth(7).evaluate(
        """(el) => {
            el.value = false;
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value: false }, bubbles: true, composed: true,
            }));
        }"""
    )
    await modal.locator("platform-button", has_text="Сохранить").click()
    await expect(modal).to_have_count(0, timeout=15_000)

    op_types = await stock_rest(
        page, "GET", f"/operation-types?warehouse_id={warehouse_id}"
    )
    incoming = next(ot for ot in op_types["items"] if ot["code"] == "incoming")
    assert incoming["name_prefix"] == "IN-"
    assert incoming["create_lots"] is False
    await scenario.step(
        "Измените политики типа «Приёмка»",
        page,
        screenshot_name="op-type-saved",
        label_en="Change the «Receipt» type policies",
        details=(
            "**Демонстрация результата.** В редакторе задан "
            "префикс номеров «IN-» и выключено заведение "
            "партий: приёмка под этим типом теперь примет "
            "только уже зарегистрированную партию и откажет "
            "новой — строгий режим для сертифицированных "
            "поставок.\n\n"
            "**Итог.** Тип операции — пульт управления "
            "терминалом: все политики документа меняются "
            "в одной форме и действуют сразу."
        ),
        details_en=(
            "**Result demonstration.** The editor sets the "
            "number prefix «IN-» and disables lot creation: "
            "receiving under this type now accepts only an "
            "already registered lot and refuses a new one — "
            "strict mode for certified supplies.\n\n"
            "**Summary.** The operation type is the handheld "
            "control panel: every document policy changes in "
            "one form and applies at once."
        ),
    )


@pytest.mark.scenario(
    service="stock",
    tag="settings",
    doc_slug="stock-admin-decisions",
    title="Рефлекс-решения: аудит выбора ячеек размещения",
    title_en="Reflex decisions: putaway choice audit",
    description=(
        "**Для чего:** когда система или диспетчер выбирает "
        "ячейку для товара, выбор записывается как решение — "
        "кем, когда и из каких кандидатов.\n\n"
        "**Какие проблемы решает:** страница «Решения» — "
        "журнал аудита размещений: точка рефлекса, режим, "
        "кандидаты и итоговый выбор; фильтр по статусу "
        "отделяет применённые от предложенных и отклонённых.\n\n"
        "**Результат:** решение о размещении приёмки видно "
        "в журнале со статусом «применено» и выбранной "
        "ячейкой."
    ),
    description_en=(
        "**Purpose:** whenever the system or a dispatcher "
        "chooses a product's bin, the choice is recorded as "
        "a decision — by whom, when and from which "
        "candidates.\n\n"
        "**Problems solved:** the «Decisions» page is the "
        "putaway audit log: reflex point, mode, candidates "
        "and the final choice; the status filter separates "
        "applied from suggested and rejected.\n\n"
        "**Result:** the receipt's putaway decision is "
        "visible in the log as «applied» with the chosen "
        "bin."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(300)
async def test_stock_admin_decisions(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await stock_e2e_open(page, stock_ui)

    seed = await tsd_seed_warehouse(page, unique_id)
    warehouse_id = seed["warehouse"]["warehouse_id"]
    bin_a = seed["bin_a"]
    product_1 = seed["product_1"]
    uom_id = seed["uom_id"]

    # Черновик приёмки → move без выбранной ячейки → apply_decision.
    op_types = await stock_rest(
        page, "GET", f"/operation-types?warehouse_id={warehouse_id}"
    )
    incoming = next(ot for ot in op_types["items"] if ot["code"] == "incoming")
    transfer = await stock_rest(
        page, "POST", "/transfers",
        {
            "warehouse_id": warehouse_id,
            "operation_type_id": incoming["operation_type_id"],
            "moves": [
                {
                    "product_id": product_1["product_id"],
                    "product_qty": "5",
                    "uom_id": uom_id,
                    "location_dest_id": bin_a["location_id"],
                },
            ],
        },
    )
    detail = await stock_rest(
        page, "GET", f"/transfers/{transfer['transfer_id']}"
    )
    move_id = detail["moves"][0]["move_id"]
    await stock_rest(
        page, "POST", "/moves/apply-decision",
        {"move_id": move_id, "location_id": bin_a["location_id"]},
    )

    await stock_e2e_nav(page, "stock_decisions", page_selector="stock-decisions-page")
    dec_page = page.locator("stock-decisions-page")
    await stock_e2e_pick_warehouse(dec_page, f"Склад {unique_id[:4]}")

    row = dec_page.locator("tr", has_text=f"Ячейка А{unique_id[:3]}").first
    await expect(row).to_be_visible(timeout=20_000)
    await expect(row.locator(".decision-status")).to_contain_text(
        "Применено", timeout=10_000
    )
    await scenario.step(
        "Откройте журнал рефлекс-решений",
        page,
        screenshot_name="decisions-applied",
        label_en="Open the reflex decision log",
        details=(
            "Раздел «Настройки → Решения»: каждое решение — "
            "точка автоматики (размещение), режим (правило, "
            "inline, тень), список ячеек-кандидатов и итоговый "
            "выбор. Статус «применено» — выбор уже исполнен "
            "на остатках."
        ),
        details_en=(
            "«Settings → Decisions»: each decision is an "
            "automation point (putaway), a mode (rule, "
            "inline, shadow), candidate bins and the final "
            "choice. «Applied» status means the choice is "
            "already executed on stock."
        ),
    )
    # Фильтр по статусу: «применённые» оставляют строку видимой.
    await dec_page.locator(".toolbar platform-searchable-combobox").last.evaluate(
        """(el) => {
            el.value = 'applied';
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value: 'applied' }, bubbles: true, composed: true,
            }));
        }"""
    )
    await expect(row).to_be_visible(timeout=15_000)
    await scenario.step(
        "Отфильтруйте решения по статусу",
        page,
        screenshot_name="decisions-filtered",
        label_en="Filter decisions by status",
        details=(
            "**Демонстрация результата.** Фильтр статуса "
            "оставляет применённые решения — журнал честно "
            "показывает, что выбор ячейки А записан и "
            "исполнен.\n\n"
            "**Итог.** «Решения» — аудит размещений: кто и "
            "почему выбрал ячейку виден из журнала, а не из "
            "опроса персонала."
        ),
        details_en=(
            "**Result demonstration.** The status filter keeps "
            "applied decisions — the log honestly shows the "
            "bin-A choice recorded and executed.\n\n"
            "**Summary.** «Decisions» is the putaway audit: "
            "who chose which bin and why is read from the "
            "log, not from staff interviews."
        ),
    )
