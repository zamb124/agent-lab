"""Сквозной сценарий Stock: от пустого склада до смены оператора на ТСД.

Акт 1 (десктоп): администратор заводит ВСЕ сущности через UI — склад
(топология строится пресетом), типы хранения и тары, технику, единицу
измерения, два товара с баркодами, упаковку, ячейки хранения и паллету,
правила размещения и пополнения, маршрут. Ни один справочник не сидится
в обход UI: то, что делает администратор, делает тест мышью.

Акт 2 (ТСД, 430×900): оператор проходит полный складской цикл на
созданных сущностях — вход по бейджу техники, карточка товара со скана,
приёмка двух товаров, перемещение, инвентаризация, сборка по накладной,
перемещение паллеты. Документ-накладная приходит снаружи (заказ
поставщику/отгрузка создаётся в ERP-потоке) — на ТСД его только сканируют.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.stock_e2e_helpers import (
    TSD_VIEWPORT,
    stock_e2e_nav,
    stock_e2e_open,
    stock_e2e_pick_warehouse,
    stock_quant_qty,
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
    tsd_wait_step,
)
from tests.ui.harness import AppUI, ui_set_platform_field
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


async def _save_entity_modal(page: Page) -> None:
    """Сабмит модалки `stock-entity-form-modal` по header-кнопке сохранения."""
    modal = page.locator("stock-entity-form-modal")
    await expect(modal.locator(".header-save-btn")).to_be_enabled(timeout=10_000)
    await modal.locator(".header-save-btn").click()
    await expect(modal).to_be_hidden(timeout=15_000)


async def _create_via_entity_modal(page: Page, create_button: Any, values: list[str]) -> Any:
    """Открыть create-модалку settings-страницы, заполнить поля по порядку, сохранить."""
    await create_button.locator("button").click()
    modal = page.locator("stock-entity-form-modal")
    await expect(modal.locator("platform-field").first).to_be_visible(timeout=15_000)
    fields = modal.locator("platform-field")
    for i, value in enumerate(values):
        await ui_set_platform_field(fields.nth(i), value)
    return modal


async def _tsd_product_create(
    page: Page, *, name: str, sku: str, barcode: str, uom_id: str
) -> None:
    """Товар через UI: picker каталога → «создать новый» → карточка товара."""
    products_page = page.locator("stock-products-page")
    await products_page.locator("page-header platform-button").locator("button").click()
    picker = page.locator("platform-catalog-product-picker")
    await expect(picker).to_be_visible(timeout=15_000)
    await ui_set_platform_field(picker.locator("platform-field").first, name)
    await picker.locator("[data-create-new]").click()
    modal = page.locator("stock-product-modal")
    await expect(modal.locator("platform-field").first).to_be_visible(timeout=15_000)
    fields = modal.locator("platform-field")
    await ui_set_platform_field(fields.nth(0), name)
    await ui_set_platform_field(fields.nth(1), sku)
    await ui_set_platform_field(fields.nth(2), uom_id)
    await fields.nth(3).evaluate(
        """(el, value) => {
            el.value = value;
            el.dispatchEvent(new CustomEvent('change', {
                detail: { value }, bubbles: true, composed: true,
            }));
        }""",
        [barcode],
    )
    save = modal.locator("platform-button").nth(1)
    await expect(save).to_be_enabled(timeout=10_000)
    await save.locator("button").click()
    await expect(modal).to_be_hidden(timeout=15_000)


@pytest.mark.scenario(
    service="stock",
    tag="full-lifecycle",
    doc_slug="stock-full-lifecycle",
    title="Полный цикл склада: настройка администратором → смена на ТСД",
    title_en="Full warehouse cycle: admin setup → operator shift on the handheld",
    description=(
        "**Для чего:** единая инструкция «с нуля до результата» — от "
        "регистрации склада до проведённых операций на терминале.\n\n"
        "**Какие проблемы решает:** показывает, что администратору не "
        "нужен программист — все справочники заводятся формами; "
        "оператору не нужен компьютер — вся работа идёт сканами.\n\n"
        "**Результат:** склад с топологией, справочниками и правилами; "
        "принятый, перемещённый, пересчитанный и отгруженный товар — "
        "всё проведено леджером."
    ),
    description_en=(
        "**Purpose:** a single zero-to-result instruction — from "
        "warehouse registration to posted handheld operations.\n\n"
        "**Problems solved:** shows the admin needs no programmer — "
        "every directory is filled through forms; the operator needs "
        "no desktop — all work is done by scans.\n\n"
        "**Result:** a warehouse with topology, directories and rules; "
        "product received, moved, counted and shipped — all posted "
        "to the ledger."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(360)
async def test_stock_full_lifecycle(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    page.set_default_timeout(30_000)
    page.context.set_default_timeout(30_000)
    tag = unique_id[:4]
    uid6 = unique_id[:6]
    wh_name = f"Склад {tag}"
    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)

    # ================================================================
    # АКТ 1 — Администратор: склад и все справочники через UI
    # ================================================================

    # --- 1. Склад: пресет «standard» сам строит топологию и типы операций ---
    await stock_e2e_nav(
        page, "stock_warehouses", page_selector="stock-warehouses-page"
    )
    wh_page = page.locator("stock-warehouses-page")
    await _create_via_entity_modal(
        page,
        wh_page.locator("page-header platform-button[data-create]"),
        [f"0-{unique_id[:8].upper()}", wh_name],
    )
    await scenario.step(
        "Заведите склад — топология соберётся сама",
        page,
        screenshot_name="admin-warehouse-create",
        label_en="Register the warehouse — topology builds itself",
        details=(
            "«Настройки → Склады → Создать»: код и название — всё, что "
            "нужно ввести. Схема «standard» заодно разворачивает зоны "
            "«Приёмка / Хранение / Упаковка / Отгрузка» и типы операций "
            "«приход, отгрузка, внутренние» — руками ничего не "
            "доклеивается."
        ),
        details_en=(
            "«Settings → Warehouses → Create»: code and name are all "
            "you type. The «standard» layout unfolds «Receiving / "
            "Stock / Packing / Shipping» zones and «incoming, "
            "outgoing, internal» operation types by itself."
        ),
    )
    await _save_entity_modal(page)
    wh_row = wh_page.locator("tbody tr").filter(has_text=wh_name)
    await expect(wh_row.first).to_be_visible(timeout=15_000)
    warehouses = await stock_rest(page, "GET", "/warehouses?limit=500")
    wh_row = next(
        w for w in warehouses["items"] if w["name"] == wh_name
    )
    wh_id = wh_row["warehouse_id"]
    view_loc_id = wh_row["view_location_id"]
    locations = await stock_rest(page, "GET", f"/locations?warehouse_id={wh_id}&limit=500")
    zone_stock = next(
        loc for loc in locations["items"] if loc["name"] == "Stock"
    )
    loc_receiving = next(
        loc for loc in locations["items"] if loc["name"] == "Receiving"
    )
    await stock_e2e_pick_warehouse(wh_page, wh_name)
    op_section = wh_page.locator("tbody tr").filter(has_text="incoming")
    await expect(op_section.first).to_be_visible(timeout=15_000)
    await scenario.step(
        "Типы операций склада — готовы из коробки",
        page,
        screenshot_name="admin-warehouse-operations",
        label_en="Warehouse operation types — ready out of the box",
        details=(
            "**Демонстрация результата.** Под таблицей складов — типы "
            "операций выбранного склада: приход, отгрузка, внутренние "
            "перемещения. Тумблер «auto-validate» и поток сканирования "
            "«default/pack/ship» правятся прямо в строке — они решают, "
            "какие экраны увидит оператор на ТСД."
        ),
        details_en=(
            "**Result demonstration.** Below the warehouse table are "
            "the operation types of the selected warehouse: incoming, "
            "outgoing, internal moves. The «auto-validate» toggle and "
            "the «default/pack/ship» scan flow are edited inline — "
            "they decide which screens the operator gets on the "
            "handheld."
        ),
    )

    # --- 2. Тип хранения: стеллаж для ячеек ---
    await stock_e2e_nav(
        page, "stock_storage_types", page_selector="stock-storage-types-page"
    )
    st_page = page.locator("stock-storage-types-page")
    await stock_e2e_pick_warehouse(st_page, wh_name)
    await _create_via_entity_modal(
        page,
        st_page.locator("page-header platform-button[data-create]"),
        [wh_id, f"Стеллаж {tag}"],
    )
    await scenario.step(
        "Создайте тип хранения",
        page,
        screenshot_name="admin-storage-type-form",
        label_en="Create a storage type",
        details=(
            "«Типы хранения» — это классы ячеек (стеллаж, пол, "
            "холодильник): у типа — лимиты по таре, весу и период "
            "инвентаризации. Ячейка потом просто ссылается на тип."
        ),
        details_en=(
            "«Storage types» are bin classes (rack, floor, cold "
            "room): a type carries container, weight and cycle-count "
            "limits. A bin then just references a type."
        ),
    )
    await _save_entity_modal(page)
    await expect(
        st_page.locator("tbody tr").filter(has_text=f"Стеллаж {tag}").first
    ).to_be_visible(timeout=15_000)
    storage_types = await stock_rest(page, "GET", f"/storage-types?warehouse_id={wh_id}")
    storage_type_id = next(
        st["storage_type_id"] for st in storage_types["items"] if st["name"] == f"Стеллаж {tag}"
    )

    # --- 3. Тип тары: европаллета ---
    await stock_e2e_nav(
        page, "stock_container_types", page_selector="stock-container-types-page"
    )
    ct_page = page.locator("stock-container-types-page")
    await stock_e2e_pick_warehouse(ct_page, wh_name)
    await _create_via_entity_modal(
        page,
        ct_page.locator("page-header platform-button[data-create]"),
        [wh_id, f"Паллета {tag}", "pallet", "500"],
    )
    await scenario.step(
        "Создайте тип тары «паллета»",
        page,
        screenshot_name="admin-container-type-form",
        label_en="Create a «pallet» container type",
        details=(
            "«Типы тары» — паллеты, короба, тележки. У типа — вид "
            "(pallet/box/tote/cart), лимит веса и объёма, признак "
            "многоразовости. Паллета позже станет локацией-контейнером "
            "и поедет по складу целиком."
        ),
        details_en=(
            "«Container types» are pallets, boxes, carts. A type has "
            "a kind (pallet/box/tote/cart), weight and volume limits "
            "and a reusable flag. The pallet later becomes a "
            "container location and travels the warehouse whole."
        ),
    )
    await _save_entity_modal(page)
    await expect(
        ct_page.locator("tbody tr").filter(has_text=f"Паллета {tag}").first
    ).to_be_visible(timeout=15_000)
    container_types = await stock_rest(page, "GET", f"/container-types?warehouse_id={wh_id}")
    container_type_id = next(
        ct["container_type_id"] for ct in container_types["items"] if ct["name"] == f"Паллета {tag}"
    )

    # --- 4. Техника: тип ресурса + погрузчик с бейджом ---
    await stock_e2e_nav(
        page, "stock_resources", page_selector="stock-resources-page"
    )
    res_page = page.locator("stock-resources-page")
    await stock_e2e_pick_warehouse(res_page, wh_name)
    type_button = res_page.locator(".section platform-button")
    await type_button.locator("button").click()
    rt_modal = page.locator("stock-entity-form-modal")
    await expect(rt_modal.locator("platform-field").first).to_be_visible(timeout=15_000)
    rt_fields = rt_modal.locator("platform-field")
    await ui_set_platform_field(rt_fields.nth(0), wh_id)
    await ui_set_platform_field(rt_fields.nth(1), f"Погрузчик {tag}")
    await _save_entity_modal(page)
    resource_types = await stock_rest(page, "GET", f"/resource-types?warehouse_id={wh_id}")
    resource_type_id = next(
        rt["resource_type_id"] for rt in resource_types["items"] if rt["name"] == f"Погрузчик {tag}"
    )
    await _create_via_entity_modal(
        page,
        res_page.locator("page-header platform-button[data-create]"),
        [wh_id, f"T-{tag}", resource_type_id, f"RES-{uid6}"],
    )
    await scenario.step(
        "Выдайте технике бейдж со штрихкодом",
        page,
        screenshot_name="admin-resource-form",
        label_en="Issue the equipment a barcode badge",
        details=(
            "«Ресурсы» — техника и люди-устройства: тележка, погрузчик, "
            "пикер. У ресурса есть штрихкод-бейдж: оператор сканирует "
            "его на ТСД и техника привязывается к смене — задания "
            "фильтруются под её возможности."
        ),
        details_en=(
            "«Resources» are equipment and device-people: carts, "
            "forklifts, pickers. A resource carries a barcode badge: "
            "the operator scans it on the handheld and the equipment "
            "binds to the shift — tasks filter to its capabilities."
        ),
    )
    await _save_entity_modal(page)
    await expect(
        res_page.locator("tbody tr").filter(has_text=f"T-{tag}").first
    ).to_be_visible(timeout=15_000)

    # --- 5. Единица измерения: упаковка из 12 штук ---
    await stock_e2e_nav(page, "stock_uoms", page_selector="stock-uoms-page")
    uoms_page = page.locator("stock-uoms-page")
    uom_create = uoms_page.locator(".section").first.locator("platform-button")
    await uom_create.locator("button").click()
    uom_modal = page.locator("stock-entity-form-modal")
    await expect(uom_modal.locator("platform-field").first).to_be_visible(timeout=15_000)
    uom_fields = uom_modal.locator("platform-field")
    await ui_set_platform_field(uom_fields.nth(0), f"Упаковка {tag}")
    await ui_set_platform_field(uom_fields.nth(1), "unit")
    await ui_set_platform_field(uom_fields.nth(2), "12")
    await scenario.step(
        "Добавьте свою единицу измерения",
        page,
        screenshot_name="admin-uom-form",
        label_en="Add a custom unit of measure",
        details=(
            "«ЕИ и упаковки»: своя единица — имя, категория и "
            "коэффициент к базовой. «Упаковка ×12» позволит принимать "
            "и отгружать коробами, не пересчитывая в штуки."
        ),
        details_en=(
            "«UoM & packaging»: a custom unit is a name, a category "
            "and a factor to the base. «Pack ×12» lets you receive "
            "and ship by the box without converting to pieces."
        ),
    )
    await _save_entity_modal(page)
    await expect(
        uoms_page.locator("tbody tr").filter(has_text=f"Упаковка {tag}").first
    ).to_be_visible(timeout=15_000)
    uoms = await stock_rest(page, "GET", "/uoms?limit=500")
    uom_id = next(u["uom_id"] for u in uoms["items"] if u["name"] == "Units")

    # --- 6. Товары через каталог-пикер (2 SKU с баркодами) ---
    await stock_e2e_nav(page, "stock_products", page_selector="stock-products-page")
    await _tsd_product_create(
        page, name=f"Кофе зерновой {tag}", sku=f"BEAN-{uid6}",
        barcode=f"BC-1-{uid6}", uom_id=uom_id,
    )
    await scenario.step(
        "Заведите первый товар",
        page,
        screenshot_name="admin-product-in-table",
        label_en="Register the first product",
        details=(
            "«Товары → Создать» открывает каталог-пикер: если товар "
            "уже есть в общем каталоге — подключите его одной строкой, "
            "если нет — «Создать новый». Артикул, базовая ЕИ и "
            "штрихкод — минимум для работы терминала."
        ),
        details_en=(
            "«Products → Create» opens the catalog picker: if the "
            "product is already in the shared catalog, attach it in "
            "one row; otherwise «Create new». SKU, base UoM and a "
            "barcode are the minimum the handheld needs."
        ),
    )
    await _tsd_product_create(
        page, name=f"Чай листовой {tag}", sku=f"TEA-{uid6}",
        barcode=f"BC-2-{uid6}", uom_id=uom_id,
    )
    products_page = page.locator("stock-products-page")
    await expect(
        products_page.locator("tbody tr").filter(has_text=f"Чай листовой {tag}").first
    ).to_be_visible(timeout=15_000)
    products = await stock_rest(page, "GET", "/products?limit=500")
    product_1 = next(
        p for p in products["items"] if p["sku"] == f"BEAN-{uid6}"
    )
    product_2 = next(
        p for p in products["items"] if p["sku"] == f"TEA-{uid6}"
    )
    await tsd_seed_product_image(
        page, str(product_1["product_id"]), color="#b4690e", label="КОФЕ"
    )
    await tsd_seed_product_image(
        page, str(product_2["product_id"]), color="#2e7d46", label="ЧАЙ"
    )

    # --- 7. Упаковка товара: короб из 12 штук со своим баркодом ---
    await stock_e2e_nav(page, "stock_uoms", page_selector="stock-uoms-page")
    uoms_page = page.locator("stock-uoms-page")
    pkg_section = uoms_page.locator(".section").last
    await pkg_section.locator("platform-button").locator("button").click()
    pkg_modal = page.locator("stock-entity-form-modal")
    await expect(pkg_modal.locator("platform-field").first).to_be_visible(timeout=15_000)
    pkg_fields = pkg_modal.locator("platform-field")
    await ui_set_platform_field(pkg_fields.nth(0), product_1["product_id"])
    await ui_set_platform_field(pkg_fields.nth(1), f"Короб {tag}")
    await ui_set_platform_field(pkg_fields.nth(2), "12")
    await ui_set_platform_field(pkg_fields.nth(3), f"PACK-{uid6}")
    await scenario.step(
        "Привяжите упаковку к товару",
        page,
        screenshot_name="admin-packaging-form",
        label_en="Bind a package to the product",
        details=(
            "Упаковка — это «короб по 12 шт» со своим штрихкодом: "
            "скан упаковки на ТСД сам подставит товар и количество. "
            "Отдельный баркод — отдельная этикетка на коробе."
        ),
        details_en=(
            "A package is a «box of 12» with its own barcode: "
            "scanning it on the handheld fills product and quantity "
            "itself. A dedicated barcode — a dedicated box label."
        ),
    )
    await _save_entity_modal(page)
    await expect(
        uoms_page.locator("tbody tr").filter(has_text=f"Короб {tag}").first
    ).to_be_visible(timeout=15_000)

    # --- 8. Ячейки хранения и паллета — дети зоны «Stock» ---
    await page.reload(wait_until="domcontentloaded")
    await stock_e2e_nav(
        page, "stock_locations", page_selector="stock-locations-page"
    )
    loc_page = page.locator("stock-locations-page")
    tree = loc_page.locator("platform-tree")
    twisty = tree.locator(f"[data-twisty='wh:{wh_id}']")
    await expect(twisty).to_be_visible(timeout=15_000)
    await twisty.click()
    view_twisty = tree.locator(f"[data-twisty='{view_loc_id}']")
    await expect(view_twisty).to_be_visible(timeout=15_000)
    await view_twisty.click()
    stock_node = tree.locator(f"[data-node-id='{zone_stock['location_id']}']")
    await expect(stock_node).to_be_visible(timeout=15_000)
    await scenario.step(
        "Разверните склад на карте локаций",
        page,
        screenshot_name="admin-locations-tree",
        label_en="Expand the warehouse on the location map",
        details=(
            "«Локации» — карта склада деревом: пресет «standard» уже "
            "создал «Receiving / Stock→Pick / Packing / Shipping». "
            "Дальше добавляем рабочие ячейки внутрь зоны «Stock»."
        ),
        details_en=(
            "«Locations» is the warehouse map as a tree: the "
            "«standard» preset already made «Receiving / Stock→Pick / "
            "Packing / Shipping». Now we add working bins inside the "
            "«Stock» zone."
        ),
    )
    await stock_node.click()
    create_child = loc_page.locator("page-header platform-button").nth(1)
    await create_child.locator("button").click()
    loc_modal = page.locator("stock-location-modal")
    await expect(loc_modal.locator("[data-location-name]")).to_be_visible(timeout=15_000)
    await ui_set_platform_field(
        loc_modal.locator("[data-location-name]"), f"A-01 {tag}"
    )
    await ui_set_platform_field(
        loc_modal.locator("[data-location-barcode]"), f"BIN-A-{uid6}"
    )
    await ui_set_platform_field(
        loc_modal.locator("[data-location-storage-type]"), storage_type_id
    )
    await scenario.step(
        "Добавьте ячейку хранения",
        page,
        screenshot_name="admin-location-bin-form",
        label_en="Add a storage bin",
        details=(
            "«Создать дочернюю» внутри зоны «Stock»: имя ячейки, её "
            "штрихкод (наклейка на стеллаже) и тип хранения — стеллаж, "
            "заведённый шагом раньше. Штрихкод — то, что оператор "
            "будет сканировать на месте."
        ),
        details_en=(
            "«Create child» inside the «Stock» zone: the bin name, "
            "its barcode (the shelf sticker) and the storage type — "
            "the rack registered a step ago. The barcode is what the "
            "operator scans on the floor."
        ),
    )
    await loc_modal.locator(".header-save-btn").click()
    await expect(loc_modal).to_be_hidden(timeout=15_000)

    # Вторая ячейка — приёмник перемещений
    await create_child.locator("button").click()
    await expect(loc_modal.locator("[data-location-name]")).to_be_visible(timeout=15_000)
    await ui_set_platform_field(
        loc_modal.locator("[data-location-name]"), f"A-02 {tag}"
    )
    await ui_set_platform_field(
        loc_modal.locator("[data-location-barcode]"), f"BIN-B-{uid6}"
    )
    await ui_set_platform_field(
        loc_modal.locator("[data-location-storage-type]"), storage_type_id
    )
    await loc_modal.locator(".header-save-btn").click()
    await expect(loc_modal).to_be_hidden(timeout=15_000)

    # Паллета — контейнерная локация внутри той же зоны
    await create_child.locator("button").click()
    await expect(loc_modal.locator("[data-location-name]")).to_be_visible(timeout=15_000)
    await ui_set_platform_field(
        loc_modal.locator("[data-location-name]"), f"Паллета-01 {tag}"
    )
    await ui_set_platform_field(
        loc_modal.locator("[data-location-barcode]"), f"PLT-{uid6}"
    )
    usage_segments = loc_modal.locator("[data-location-usage] .segment")
    await usage_segments.nth(2).click()
    await ui_set_platform_field(
        loc_modal.locator("[data-location-container-type]"), container_type_id
    )
    await scenario.step(
        "Заведите паллету как контейнер-локацию",
        page,
        screenshot_name="admin-location-pallet-form",
        label_en="Register a pallet as a container location",
        details=(
            "Та же «дочерняя» локация, но вид «контейнер»: паллета — "
            "движимая ячейка, её содержимое едет вместе с ней. Тип — "
            "паллета из справочника тары, баркод — бирка на борту."
        ),
        details_en=(
            "The same «child» location but «container» usage: a "
            "pallet is a movable bin — its contents travel with it. "
            "Type — the pallet from the container directory, barcode "
            "— the tag on its side."
        ),
    )
    await loc_modal.locator(".header-save-btn").click()
    await expect(loc_modal).to_be_hidden(timeout=15_000)
    locations = await stock_rest(page, "GET", f"/locations?warehouse_id={wh_id}&limit=500")
    bin_a = next(
        loc for loc in locations["items"] if loc["name"] == f"A-01 {tag}"
    )
    bin_b = next(
        loc for loc in locations["items"] if loc["name"] == f"A-02 {tag}"
    )
    pallet = next(
        loc for loc in locations["items"] if loc["name"] == f"Паллета-01 {tag}"
    )
    await tree.locator(f"[data-twisty='{zone_stock['location_id']}']").click()
    await expect(
        tree.locator(f"[data-node-id='{pallet['location_id']}']")
    ).to_be_visible(timeout=15_000)
    await scenario.step(
        "Карта готова: зона, ячейки и паллета",
        page,
        screenshot_name="admin-locations-ready",
        label_en="The map is ready: zone, bins and a pallet",
        details=(
            "**Демонстрация результата.** В дереве под «Stock» — две "
            "ячейки стеллажа и паллета. Каждая имеет штрихкод — можно "
            "переходить к правилам размещения."
        ),
        details_en=(
            "**Result demonstration.** Under «Stock» in the tree — "
            "two rack bins and a pallet. Each has a barcode — time "
            "for putaway rules."
        ),
    )

    # --- 9. Правило размещения: приёмка → ячейка A-01 ---
    await stock_e2e_nav(
        page, "stock_putaway_rules", page_selector="stock-putaway-rules-page"
    )
    put_page = page.locator("stock-putaway-rules-page")
    await stock_e2e_pick_warehouse(put_page, wh_name)
    await _create_via_entity_modal(
        page,
        put_page.locator("page-header platform-button[data-create]"),
        [wh_id, loc_receiving["location_id"], bin_a["location_id"], product_1["product_id"], "10"],
    )
    await scenario.step(
        "Назначьте правило размещения",
        page,
        screenshot_name="admin-putaway-rule-form",
        label_en="Assign a putaway rule",
        details=(
            "«Правила размещения» отвечают «куда убрать приехавший "
            "товар»: из зоны приёмки — в конкретную ячейку. На ТСД "
            "это правило превратится в подсказку «положите в A-01»."
        ),
        details_en=(
            "«Putaway rules» answer «where does incoming stock go»: "
            "from the receiving zone into a concrete bin. On the "
            "handheld this rule becomes the «put into A-01» hint."
        ),
    )
    await _save_entity_modal(page)
    await expect(
        put_page.locator("tbody tr").filter(has_text=f"A-01 {tag}").first
    ).to_be_visible(timeout=15_000)

    # --- 10. Правило пополнения: минимум/максимум ячейки ---
    op_types = await stock_rest(page, "GET", f"/operation-types?warehouse_id={wh_id}")
    op_incoming = next(ot for ot in op_types["items"] if ot["code"] == "incoming")
    await stock_e2e_nav(
        page, "stock_reorder_rules", page_selector="stock-reorder-rules-page"
    )
    reorder_page = page.locator("stock-reorder-rules-page")
    await stock_e2e_pick_warehouse(reorder_page, wh_name)
    await _create_via_entity_modal(
        page,
        reorder_page.locator("page-header platform-button[data-create]"),
        [wh_id, product_1["product_id"], bin_a["location_id"], "5", "20", op_incoming["operation_type_id"]],
    )
    await scenario.step(
        "Задайте минимум и максимум запаса ячейки",
        page,
        screenshot_name="admin-reorder-rule-form",
        label_en="Set the bin's min and max stock",
        details=(
            "«Правила пополнения» стерегут ячейку: остаток упал ниже "
            "минимума — система предложит пополнить до максимума "
            "указанным видом документа."
        ),
        details_en=(
            "«Reorder rules» guard the bin: stock below the minimum "
            "— the system suggests a replenishment up to the maximum "
            "with the given document kind."
        ),
    )
    await _save_entity_modal(page)
    await expect(
        reorder_page.locator("tbody tr").filter(has_text=f"Кофе зерновой {tag}").first
    ).to_be_visible(timeout=15_000)

    # --- 11. Маршрут ---
    await stock_e2e_nav(page, "stock_routes", page_selector="stock-routes-page")
    routes_page = page.locator("stock-routes-page")
    await _create_via_entity_modal(
        page,
        routes_page.locator("page-header platform-button[data-create]"),
        [f"Сборка {tag}", f"RT-{tag}"],
    )
    await _save_entity_modal(page)
    await expect(
        routes_page.locator("tbody tr").filter(has_text=f"Сборка {tag}").first
    ).to_be_visible(timeout=15_000)
    await scenario.step(
        "Настройка закончена — склад готов к смене",
        page,
        screenshot_name="admin-setup-done",
        label_en="Setup complete — the warehouse is shift-ready",
        details=(
            "**Демонстрация результата.** Справочники заполнены только "
            "UI-формами: склад с топологией, типы хранения и тары, "
            "техника с бейджем, единицы и упаковки, товары с "
            "штрихкодами, ячейки и паллета, правила размещения и "
            "пополнения, маршрут.\n\n"
            "**Дальше** — передаём терминал оператору."
        ),
        details_en=(
            "**Result demonstration.** Every directory was filled "
            "with UI forms only: a warehouse with topology, storage "
            "and container types, badged equipment, units and "
            "packaging, barcoded products, bins and a pallet, "
            "putaway and reorder rules, a route.\n\n"
            "**Next** — hand the terminal to the operator."
        ),
    )

    # ================================================================
    # АКТ 2 — Оператор: полный цикл на ТСД
    # ================================================================
    await page.set_viewport_size(TSD_VIEWPORT)
    await tsd_open(page, stock_ui)
    await tsd_pick_warehouse(page, unique_id)
    await scenario.step(
        "Возьмите терминал и выберите склад",
        page,
        screenshot_name="tsd-warehouse-picked",
        label_en="Take the handheld and pick the warehouse",
        details=(
            "ТСД открывается списком складов — оператор выбирает свой "
            "раз в смену. Видно только то, что администратор завёл "
            "через формы."
        ),
        details_en=(
            "The handheld opens with the warehouse list — the "
            "operator picks theirs once per shift. It shows only "
            "what the admin registered through forms."
        ),
    )

    # --- Вход по бейджу техники ---
    await tsd_scan(page, f"RES-{uid6}")
    sheet = page.locator("stock-tsd-entity-sheet")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet.locator(".action")).to_have_count(1, timeout=15_000)
    await sheet.locator(".action").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    chip = page.locator("stock-tsd-home-page .context-chips .chip").nth(1)
    await expect(chip).to_contain_text(f"T-{tag}", timeout=15_000)
    await scenario.step(
        "Скан бейджа техники — смена привязана",
        page,
        screenshot_name="tsd-resource-bound",
        label_en="Badge scan — shift bound to the equipment",
        details=(
            "Штрихкод погрузчика открыл карточку ресурса, кнопка "
            "«привязать» закрепила его за сменой на сервере — чип "
            "техники показывает код. Пароль не нужен: бейдж и есть "
            "удостоверение."
        ),
        details_en=(
            "The forklift barcode opened the resource card, the "
            "«bind» button claimed it for the shift on the server — "
            "the equipment chip shows the code. No password needed: "
            "the badge IS the credential."
        ),
    )

    # --- Карточка товара со скана: фото, остатки, действия ---
    await tsd_scan(page, f"BC-1-{uid6}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Кофе зерновой {tag}", timeout=15_000)
    await scenario.step(
        "Скан товара — карточка с фото и действиями",
        page,
        screenshot_name="tsd-product-card",
        label_en="Product scan — card with photo and actions",
        details=(
            "Скан любого товара с любого экрана — карточка: фото, "
            "остатки по ячейкам и действия «переместить / принять / "
            "разместить / пересчитать». Оператору не надо помнить, "
            "где что лежит."
        ),
        details_en=(
            "Scanning any product from any screen opens its card: "
            "photo, per-bin stock and «move / receive / putaway / "
            "count» actions. The operator doesn't need to remember "
            "where anything is."
        ),
    )

    # --- Приёмка товара 1: приёмник A-01 ---
    await sheet.locator(".action[data-action='receive']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    run = page.locator("stock-tsd-run")
    await expect(run).to_be_visible(timeout=15_000)
    await tsd_scan(page, f"BIN-A-{uid6}")
    await tsd_wait_step(page, "quantity")
    await tsd_qty(page, "8")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await scenario.step(
        "Приёмка: товар → ячейка → количество → свайп",
        page,
        screenshot_name="tsd-receive-review",
        label_en="Receiving: product → bin → qty → slide",
        details=(
            "Машина приёмки ведёт по сканам: штрихкод товара, "
            "штрихкод ячейки-приёмника, количество на крупной "
            "клавиатуре — и проводка свайпом «слева направо». Свайп "
            "не срабатывает от случайного касания в перчатке."
        ),
        details_en=(
            "The receiving machine walks scan by scan: product "
            "barcode, destination bin barcode, quantity on the big "
            "keypad — then a left-to-right slide commits. The slide "
            "can't fire from an accidental glove touch."
        ),
    )
    await tsd_commit(page)
    assert await stock_quant_qty(page, wh_id, product_1["product_id"], bin_a["location_id"]) == Decimal("8")

    # --- Приёмка товара 2: приёмник A-02 ---
    await tsd_scan(page, f"BC-2-{uid6}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator(".action[data-action='receive']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    await tsd_scan(page, f"BIN-B-{uid6}")
    await tsd_wait_step(page, "quantity")
    await tsd_qty(page, "5")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await tsd_commit(page)
    assert await stock_quant_qty(page, wh_id, product_2["product_id"], bin_b["location_id"]) == Decimal("5")

    # --- Скан ячейки: содержимое подтверждает приёмку ---
    await tsd_scan(page, f"BIN-A-{uid6}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Кофе зерновой {tag}", timeout=15_000)
    await scenario.step(
        "Скан ячейки — остаток на месте",
        page,
        screenshot_name="tsd-bin-contents",
        label_en="Bin scan — the stock is there",
        details=(
            "**Демонстрация результата.** Штрихкод ячейки A-01 "
            "показывает принятый кофе ×8 — приёмка записана леджером. "
            "Отсюда же доступны действия по ячейке."
        ),
        details_en=(
            "**Result demonstration.** The A-01 bin barcode shows "
            "the received coffee ×8 — the receipt is in the ledger. "
            "Bin actions are available right here too."
        ),
    )
    await sheet.locator(".action[data-action='count']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    await expect(run).to_be_visible(timeout=15_000)
    await tsd_wait_step(page, "product")

    # --- Инвентаризация по месту: сверили кофе в A-01 ---
    await tsd_scan(page, f"BC-1-{uid6}")
    await tsd_wait_step(page, "quantity")
    await tsd_qty(page, "8")
    await tsd_wait_step(page, "review")
    await scenario.step(
        "Пересчёт прямо на месте",
        page,
        screenshot_name="tsd-count-review",
        label_en="Count right on the spot",
        details=(
            "Действие «пересчитать» из карточки ячейки: скан товара → "
            "фактическое количество → проводка. Расхождение система "
            "зафиксировала бы сама — здесь учёт сошёлся с фактом."
        ),
        details_en=(
            "The «count» action from the bin card: product scan → "
            "actual quantity → commit. A discrepancy would be "
            "recorded by the system itself — here books match "
            "reality."
        ),
    )
    await tsd_commit(page)

    # --- Перемещение: кофе 3 шт из A-01 в A-02 ---
    await tsd_scan(page, f"BC-1-{uid6}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await sheet.locator(".action[data-action='move']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    await expect(run).to_be_visible(timeout=15_000)
    await tsd_scan(page, f"BIN-A-{uid6}")
    await tsd_wait_step(page, "dest")
    await tsd_scan(page, f"BIN-B-{uid6}")
    await tsd_wait_step(page, "quantity")
    await tsd_qty(page, "3")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await scenario.step(
        "Перемещение: откуда → куда → сколько",
        page,
        screenshot_name="tsd-move-review",
        label_en="Move: from → where → how many",
        details=(
            "Поток перемещения повторяет физику: подтвердил ячейку "
            "отбора сканом, пришёл к целевой ячейке — сканом её, "
            "ввёл количество. Перепутать направление невозможно — "
            "источник и приёмник разные сканы."
        ),
        details_en=(
            "The move flow mirrors the physics: confirm the pick "
            "bin by scan, arrive at the target bin — scan it too, "
            "enter the quantity. Direction can't flip — source and "
            "destination are separate scans."
        ),
    )
    await tsd_commit(page)
    assert await stock_quant_qty(page, wh_id, product_1["product_id"], bin_a["location_id"]) == Decimal("5")
    assert await stock_quant_qty(page, wh_id, product_1["product_id"], bin_b["location_id"]) == Decimal("3")

    # --- Сборка по накладной: документ приходит сканом ---
    transfer = await tsd_seed_document(
        page, wh_id, unique_id,
        moves=[
            {
                "product_id": product_1["product_id"],
                "product_qty": "2",
                "uom_id": uom_id,
                "location_id": bin_b["location_id"],
            },
            {
                "product_id": product_2["product_id"],
                "product_qty": "4",
                "uom_id": uom_id,
                "location_id": bin_b["location_id"],
            },
        ],
    )
    await tsd_scan(page, f"DOC-{uid6}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(transfer["name"], timeout=15_000)
    await scenario.step(
        "Скан накладной — документ в работу",
        page,
        screenshot_name="tsd-document-card",
        label_en="Order scan — the document goes to work",
        details=(
            "Накладная от ERP резолвится в карточку документа: "
            "номер и число позиций. «Начать исполнение» открывает "
            "сессию — поток «сборка» backend выбрал сам по типу "
            "операции."
        ),
        details_en=(
            "The ERP order resolves into a document card: number "
            "and line count. «Start execution» opens a session — "
            "the backend picked the «pick» flow itself from the "
            "operation type."
        ),
    )
    await sheet.locator("button.action").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    await expect(run).to_be_visible(timeout=15_000)
    expected = run.locator(".expected")
    await expect(expected).to_contain_text(f"Кофе зерновой {tag}", timeout=15_000)
    await scenario.step(
        "Терминал подсказывает, что собирать",
        page,
        screenshot_name="tsd-document-expected",
        label_en="The terminal suggests what to pick",
        details=(
            "Жёлтая полоса — подсказка backend'а из открытой строки "
            "накладной: ячейка → товар × количество. Оператор идёт к "
            "указанной ячейке — искать заказ руками не нужно."
        ),
        details_en=(
            "The amber strip is the backend hint from the open "
            "order line: bin → product × qty. The operator walks to "
            "that bin — no need to hunt for the order."
        ),
    )

    # Позиция кофе: ячейка → товар → количество → проводка
    await tsd_scan(page, f"BIN-B-{uid6}")
    await tsd_wait_step(page, "product")
    await tsd_scan(page, f"BC-1-{uid6}")
    await tsd_wait_step(page, "quantity")
    await tsd_qty(page, "2")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await tsd_commit_click(page)

    # Backend продолжает документ: следующая строка — чай
    await expect(expected).to_contain_text(f"Чай листовой {tag}", timeout=15_000)
    await tsd_scan(page, f"BIN-B-{uid6}")
    await tsd_wait_step(page, "product")
    await tsd_scan(page, f"BC-2-{uid6}")
    await tsd_wait_step(page, "quantity")
    await tsd_qty(page, "4")
    await expect(run.locator(".commit-btn")).to_be_visible(timeout=15_000)
    await scenario.step(
        "Вторая позиция — документ ведёт сам",
        page,
        screenshot_name="tsd-document-line2",
        label_en="Second line — the document leads itself",
        details=(
            "После проводки первой позиции сессия не закрылась — "
            "backend подсказал следующую строку накладной. Оператор "
            "не возвращается в очередь между ходками."
        ),
        details_en=(
            "After the first line posted, the session did not "
            "close — the backend suggested the next order line. No "
            "queue round-trip between trips."
        ),
    )
    await tsd_commit(page)
    assert await stock_quant_qty(page, wh_id, product_2["product_id"], bin_b["location_id"]) == Decimal("1")

    # --- Паллета с товаром: положили кофе на паллету и везём целиком ---
    await tsd_seed_stock(
        page, wh_id,
        [{"location_dest_id": pallet["location_id"], "product_id": product_1["product_id"], "quantity": "6"}],
    )
    await tsd_scan(page, f"PLT-{uid6}")
    await expect(sheet).to_be_visible(timeout=15_000)
    await expect(sheet).to_contain_text(f"Паллета-01 {tag}", timeout=15_000)
    await sheet.locator(".action[data-action='container_move']").click()
    await expect(sheet).to_have_count(0, timeout=15_000)
    await expect(run).to_be_visible(timeout=15_000)
    await tsd_wait_step(page, "dest")
    await tsd_scan(page, f"BIN-A-{uid6}")
    await tsd_wait_step(page, "review")
    await scenario.step(
        "Паллета едет целиком — один скан вместо переноски",
        page,
        screenshot_name="tsd-pallet-move",
        label_en="The pallet travels whole — one scan instead of carrying",
        details=(
            "Скан бирки паллеты → «переместить» → скан ячейки-цели: "
            "всё содержимое (кофе ×6) переезжает вместе с тарой одной "
            "проводкой. Реальная физика склада — контейнер как единица."
        ),
        details_en=(
            "Scan the pallet tag → «move» → scan the target bin: "
            "all contents (coffee ×6) travel with the container in "
            "one posting. Real warehouse physics — the container is "
            "the unit."
        ),
    )
    await tsd_commit(page)
    locations = await stock_rest(page, "GET", f"/locations?warehouse_id={wh_id}&limit=500")
    pallet_after = next(
        loc for loc in locations["items"] if loc["location_id"] == pallet["location_id"]
    )
    assert pallet_after["parent_id"] == bin_a["location_id"]

    # --- Финал: рабочий стол, смена закрыта полным циклом ---
    await scenario.step(
        "Смена прошла полный цикл",
        page,
        screenshot_name="tsd-shift-done",
        label_en="The shift ran the full cycle",
        details=(
            "**Демонстрация результата.** Принято два товара, "
            "проведён пересчёт, перемещение между ячейками, сборка "
            "двух позиций накладной и переезд паллеты — всё одними "
            "сканами и свайпами, на сущностях, которые администратор "
            "создал формами.\n\n"
            "**Итог.** «Настроил склад → отдал терминал → склад "
            "работает» — от регистрации до леджера без единой "
            "строчки кода и без бумажной накладной."
        ),
        details_en=(
            "**Result demonstration.** Two products received, a "
            "count posted, a bin-to-bin move, a two-line order "
            "pick and a pallet move — all with scans and slides, "
            "on entities the admin created through forms.\n\n"
            "**Summary.** «Set up the warehouse → hand over the "
            "terminal → the warehouse runs» — registration to "
            "ledger with no code and no paper."
        ),
    )
