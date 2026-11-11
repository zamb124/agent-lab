"""Документационный сценарий Stock: структура склада в «Локациях».

Локации заводят операции (tools/интеграции) — интерфейс показывает
структуру дерева «склад → зоны → ячейки → тара» слева и карточку
выбранной локации справа: тип, блокировки, KPI и содержимое.
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
        "**Для чего:** «Карта склада» — это дерево склада: зоны, ячейки и "
        "тара, где реально лежит товар, плюс служебные локации "
        "приёмки и отгрузки.\n\n"
        "**Какие проблемы решает:** вы увидите, как склад разбит на "
        "адреса хранения, что означают типы локаций и что лежит в "
        "каждой ячейке.\n\n"
        "**Результат:** структура «склад → зона → ячейка» раскрывается "
        "в дереве, а карточка локации показывает её тип и остатки."
    ),
    description_en=(
        "**Purpose:** the warehouse map is a tree of zones, bins "
        "and containers where goods actually sit, plus the system's "
        "receiving and shipping locations.\n\n"
        "**Problems solved:** you will see how the warehouse is "
        "split into storage addresses, what the location types "
        "mean and what each bin holds.\n\n"
        "**Result:** the warehouse → zone → bin structure expands "
        "in the tree and the location card shows its type and stock."
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

    warehouse_code = f"0-{unique_id[:8].upper()}"
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
    bin_loc = await stock_e2e_op(
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

    await stock_e2e_nav(page, "stock_locations", page_selector="stock-locations-page")

    wh_node = page.locator(
        f"stock-locations-page platform-tree [data-node-id='wh:{warehouse_id}']"
    )
    await expect(wh_node).to_be_visible(timeout=30_000)
    await scenario.step(
        "Откройте «Карту склада»",
        page,
        screenshot_name="locations-tree",
        label_en="Open the warehouse map",
        details=(
            "В меню слева выберите «Локации → Карта склада» — слева "
            "дерево «склад → зоны → ячейки → тара», справа карточка "
            "выбранной локации. Склады раскрываются кликом по стрелке "
            "рядом с именем."
        ),
        details_en=(
            "Choose «Locations → Warehouse map» in the left menu — the "
            "left pane is the warehouse → zones → bins → containers "
            "tree, the right pane is the selected location card. "
            "Warehouses expand by clicking the arrow next to the name."
        ),
    )

    await page.locator(
        f"stock-locations-page platform-tree [data-twisty='wh:{warehouse_id}']"
    ).click()
    zone_parent = zone.get("parent_id")
    if zone_parent:
        await page.locator(
            f"stock-locations-page platform-tree [data-twisty='{zone_parent}']"
        ).click()
    zone_node = page.locator(
        f"stock-locations-page platform-tree [data-node-id='{zone['location_id']}']"
    )
    await expect(zone_node).to_be_visible(timeout=15_000)
    await expect(zone_node).to_contain_text(zone_name)
    await page.locator(
        f"stock-locations-page platform-tree [data-twisty='{zone['location_id']}']"
    ).click()
    bin_node = page.locator(
        f"stock-locations-page platform-tree [data-node-id='{bin_loc['location_id']}']"
    )
    await expect(bin_node).to_be_visible(timeout=15_000)
    await expect(bin_node).to_contain_text(bin_name)

    await bin_node.click()
    await expect(
        page.locator("stock-locations-page .loc-header")
    ).to_contain_text(bin_name, timeout=15_000)

    await scenario.step(
        "Выберите ячейку в дереве",
        page,
        screenshot_name="locations-detail",
        label_en="Pick a bin in the tree",
        details=(
            "**Демонстрация результата.** Клик по ячейке открывает её "
            "карточку справа: полный путь от склада, бейдж типа "
            "«ячейка», блокировки и KPI — позиции, количество, резерв "
            "и число SKU. Тип показывает роль локации: «зона» "
            "группирует ячейки (сама товар не хранит), «ячейка» — "
            "реальный адрес запаса с порядком обхода при сборке, "
            "«тара» — короб внутри паллеты. Служебные «поставщик», "
            "«покупатель» и «перераспределение» система создаёт сама "
            "и показывает отдельной веткой.\n\n"
            "**Итог.** Теперь вы видите, из каких адресов состоит "
            "склад, куда попадёт принятый товар и что лежит в каждой "
            "ячейке."
        ),
        details_en=(
            "**Result demonstration.** Clicking a bin opens its card "
            "on the right: the full path from the warehouse, the «bin» "
            "type badge, blocking flags and KPIs — positions, "
            "quantity, reserved and SKU count. The type shows the "
            "location's role: a view groups bins (it holds no stock "
            "itself), a bin is the real stock address with a picking "
            "order, a container is a box inside a pallet. The service "
            "supplier, customer and adjustment locations are created "
            "by the system and shown in their own branch.\n\n"
            "**Summary.** You can now see which addresses the "
            "warehouse consists of, where received goods land and "
            "what each bin holds."
        ),
    )
