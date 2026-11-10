"""Документационный сценарий Stock: структура склада в «Локациях».

Локации заводят операции (tools/интеграции) — интерфейс показывает
дерево плоской таблицей: зоны (view), ячейки (bin), тара (container)
и служебные виртуальные локации компании.
"""

from __future__ import annotations

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.stock_e2e_helpers import (
    stock_e2e_nav,
    stock_e2e_op,
    stock_e2e_open,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="stock",
    tag="locations",
    doc_slug="locations-tree",
    title="Структура склада: зоны и ячейки",
    title_en="Warehouse structure: zones and bins",
    description=(
        "**Для чего:** «Локации» — это карта склада: зоны, ячейки и "
        "тара, где реально лежит товар, плюс служебные локации "
        "приёмки и отгрузки.\n\n"
        "**Какие проблемы решает:** вы увидите, как склад разбит на "
        "адреса хранения и что означают типы локаций — куда кладёт "
        "товар приёмка и откуда собирает отгрузка.\n\n"
        "**Результат:** структура «зона → ячейка» видна в списке "
        "локаций рядом со служебными локациями склада."
    ),
    description_en=(
        "**Purpose:** Locations are the warehouse map: zones, bins "
        "and containers where goods actually sit, plus the system's "
        "receiving and shipping locations.\n\n"
        "**Problems solved:** you will see how the warehouse is "
        "split into storage addresses and what the location types "
        "mean — where put-away places goods and where picking takes "
        "them from.\n\n"
        "**Result:** the zone → bin structure is listed among the "
        "warehouse's service locations."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_locations_tree(
    scenario: ScenarioRecorder,
    stock_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)
    await stock_e2e_open(page, stock_ui)

    warehouses = await stock_e2e_op(
        page, "stock/warehouses", "stock/warehouses/list_requested"
    )
    existing_codes = [w["code"] for w in warehouses["items"]]
    warehouse_code = ("0" + min(existing_codes)) if existing_codes else "MAIN"
    warehouse = await stock_e2e_op(
        page,
        "stock/warehouse_create",
        "stock/warehouse_create/requested",
        {"code": warehouse_code, "name": f"Склад {unique_id[:4]}"},
    )
    warehouse_id = warehouse["warehouse_id"]

    zone_name = f"Зона хранения {unique_id[:4]}"
    zone = await stock_e2e_op(
        page,
        "stock/location_create",
        "stock/location_create/requested",
        {
            "warehouse_id": warehouse_id,
            "name": zone_name,
            "usage": "view",
        },
    )
    bin_name = f"A-01-{unique_id[:2].upper()}"
    await stock_e2e_op(
        page,
        "stock/location_create",
        "stock/location_create/requested",
        {
            "warehouse_id": warehouse_id,
            "parent_id": zone["location_id"],
            "name": bin_name,
            "usage": "bin",
            "pick_sequence": 10,
        },
    )

    await stock_e2e_nav(page, 3, page_selector="stock-locations-page")
    zone_row = page.locator(
        "stock-locations-page table tbody tr", has_text=zone_name
    )
    await expect(zone_row).to_be_visible(timeout=30_000)
    bin_row = page.locator(
        "stock-locations-page table tbody tr", has_text=bin_name
    )
    await expect(bin_row).to_be_visible(timeout=15_000)
    await scenario.step(
        "Откройте «Локации»",
        page,
        screenshot_name="locations-list",
        label_en="Open Locations",
        details=(
            "В меню слева выберите «Локации» — здесь вся структура "
            "склада. Зона «Зона хранения» и ячейка внутри неё видны "
            "рядом: у ячейки в колонке «Родитель» — код зоны."
        ),
        details_en=(
            "Choose «Locations» in the left menu — the whole "
            "warehouse structure lives here. The Storage zone and "
            "the bin inside it are listed together: the bin's Parent "
            "column points at the zone."
        ),
    )

    await scenario.step(
        "Что означают типы локаций",
        page,
        screenshot_name="locations-usage-types",
        label_en="What the location types mean",
        details=(
            "**Демонстрация результата.** Тип показывает роль "
            "локации: «зона» группирует ячейки (сама товар не "
            "хранит), «ячейка» — реальный адрес запаса с порядком "
            "обхода при сборке, «тара» — короб внутри паллеты. "
            "Служебные «поставщик», «покупатель» и «перераспределение» "
            "система создаёт сама — через них проходят приход, "
            "отгрузка и корректировки.\n\n"
            "**Итог.** Теперь вы видите, из каких адресов состоит "
            "склад и куда попадёт принятый товар."
        ),
        details_en=(
            "**Result demonstration.** The type shows the location's "
            "role: a view groups bins (it holds no stock itself), a "
            "bin is the real stock address with a picking order, a "
            "container is a box inside a pallet. The service "
            "supplier, customer and adjustment locations are created "
            "by the system — receipts, deliveries and corrections "
            "flow through them.\n\n"
            "**Summary.** You can now see which addresses the "
            "warehouse consists of and where received goods land."
        ),
    )
