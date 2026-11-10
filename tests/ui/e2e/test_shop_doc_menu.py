"""Документационный сценарий Shop: меню — позиции и модификаторы.

Маршрут владельца магазина: открыть «Меню», увидеть категории и
позиции, открыть карточку позиции и окно модификаторов.
"""

from __future__ import annotations

import httpx2
import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.test_shop_storefront_desktop import _create_storefront
from tests.ui.e2e_worker import ui_e2e_scope_headers
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="shop",
    tag="menu",
    doc_slug="menu-items-and-modifiers",
    title="Меню: позиции, цены и модификаторы",
    title_en="Menu: items, prices and modifiers",
    description=(
        "**Для чего:** меню — это всё, что видит покупатель на витрине: "
        "разделы, позиции, цены и допы (размер, добавки).\n\n"
        "**Какие проблемы решает:** карточка позиции собирает всё в "
        "одном месте — название, цену, порцию, фото и бейджи; "
        "модификаторы дают выбор «размер/добавка» без отдельных "
        "позиций-дублей.\n\n"
        "**Результат:** разделы слева, позиции справа; у каждой "
        "позиции — редактирование и кнопка «Модификаторы»."
    ),
    description_en=(
        "**Purpose:** the menu is everything the customer sees on the "
        "storefront: sections, items, prices and extras (size, "
        "add-ons).\n\n"
        "**Problems solved:** the item card keeps everything in one "
        "place — name, price, portion, photo and badges; modifiers "
        "give size/add-on choice without duplicate items.\n\n"
        "**Result:** sections on the left, items on the right; every "
        "item has edit and a Modifiers button."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_menu_items_and_modifiers(
    shop_client_http: httpx2.AsyncClient,
    shop_worker: None,
    auth_headers_system: dict[str, str],
    shop_ui: AppUI,
    ui_page_system: Page,
    unique_id: str,
    scenario: ScenarioRecorder,
) -> None:
    _ = shop_worker
    page = ui_page_system
    storefront = await _create_storefront(
        shop_client_http,
        {**auth_headers_system, **ui_e2e_scope_headers()},
        f"menu{unique_id[:8]}",
        categories=("Меню", "Напитки"),
        products_per_category=2,
        shop_patch={"pickup_enabled": True},
    )

    await shop_ui.open(page)
    await page.set_viewport_size(_DESKTOP)
    await page.goto(
        f"{shop_ui.spa_url()}{storefront.shop_id}/menu", wait_until="load"
    )
    await expect(
        page.locator("shop-category-tree").first
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Разделы и позиции меню",
        page,
        screenshot_name="menu-layout",
        label_en="Menu sections and items",
        details=(
            "Слева — дерево разделов (категорий), справа — позиции "
            "выбранного раздела с ценами. Всё, что тут есть, попадает "
            "на витрину."
        ),
        details_en=(
            "Sections tree on the left, items of the selected section "
            "with prices on the right. Everything here lands on the "
            "storefront."
        ),
    )

    await page.locator(
        "platform-button[title='Edit']"
    ).first.click()
    product_modal = page.locator("shop-product-modal")
    await expect(product_modal).to_be_visible(timeout=15_000)
    await scenario.step(
        "Карточка позиции",
        page,
        screenshot_name="product-edit",
        label_en="Item card",
        details=(
            "Название, цена, порция, описание, фото и бейджи — всё "
            "редактируется в одном окне. Кнопки с искрой заполняют "
            "описание и фото через AI."
        ),
        details_en=(
            "Name, price, portion, description, photo and badges — "
            "all editable in one window. Sparkle buttons fill "
            "description and photo with AI."
        ),
    )
    await page.keyboard.press("Escape")
    await expect(product_modal).to_have_count(0, timeout=10_000)

    await page.locator(
        "platform-button[title='Modifiers']"
    ).first.click()
    modifiers_modal = page.locator("shop-modifiers-modal")
    await expect(modifiers_modal).to_be_visible(timeout=15_000)
    await scenario.step(
        "Модификаторы позиции",
        page,
        screenshot_name="modifiers-modal",
        label_en="Item modifiers",
        details=(
            "Модификаторы — группы выбора на позиции: «размер», "
            "«добавки», «тесто». Покупатель выбирает их прямо в "
            "карточке на витрине, цена пересчитывается сама."
        ),
        details_en=(
            "Modifiers are option groups on an item: size, add-ons, "
            "dough. The customer picks them right in the storefront "
            "card, the price recalculates itself."
        ),
    )
