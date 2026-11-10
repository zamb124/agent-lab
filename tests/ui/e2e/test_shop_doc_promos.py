"""Документационный сценарий Shop: акции (промо).

Маршрут владельца: раздел «Акции» → новая акция → скидка видна
покупателю в корзине витрины.
"""

from __future__ import annotations

import httpx2
import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.test_shop_customer_auth_e2e import _page_url
from tests.ui.e2e.test_shop_storefront_desktop import _create_storefront
from tests.ui.e2e_worker import ui_e2e_scope_headers
from tests.ui.harness import AppUI, ui_set_platform_field
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="shop",
    tag="promos",
    doc_slug="promo-create",
    title="Акция со скидкой: создаём и проверяем на витрине",
    title_en="A discount promo: create it and check the storefront",
    description=(
        "**Для чего:** акции приводят покупателей и поднимают средний "
        "чек — скидка создаётся за минуту без программиста.\n\n"
        "**Какие проблемы решает:** не нужно вручную менять цены — "
        "акция сама считает скидку в корзине и показывает её "
        "покупателю отдельной строкой «Выгода».\n\n"
        "**Результат:** акция в списке и активна; в корзине витрины "
        "видна скидка с её названием."
    ),
    description_en=(
        "**Purpose:** promos bring customers and raise the average "
        "ticket — a discount takes a minute, no developer needed.\n\n"
        "**Problems solved:** no manual price edits — the promo "
        "computes the discount in the cart itself and shows it to the "
        "customer as a separate Savings line.\n\n"
        "**Result:** the promo is listed and active; the storefront "
        "cart shows the discount with its name."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_promo_create(
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
        f"promo{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=2,
        shop_patch={"pickup_enabled": True},
    )

    await shop_ui.open(page)
    await page.set_viewport_size(_DESKTOP)
    await page.goto(
        f"{shop_ui.spa_url()}{storefront.shop_id}/promos", wait_until="load"
    )
    await expect(
        page.locator("shop-promos-page .wrap").first
    ).to_be_visible(timeout=30_000)
    new_btn = page.locator(
        "shop-promos-page platform-button[variant='primary']"
    ).first
    await expect(new_btn).to_be_visible(timeout=15_000)
    await scenario.step(
        "Раздел «Акции» магазина",
        page,
        screenshot_name="promos-empty",
        label_en="Shop Promotions section",
        details=(
            "В разделе «Акции» собраны все скидки магазина. Кнопка "
            "«Новая акция» открывает редактор: шаблон скидки, условия, "
            "расписание."
        ),
        details_en=(
            "The Promotions section lists all shop discounts. The New "
            "promo button opens the editor: discount template, "
            "conditions, schedule."
        ),
    )

    await new_btn.click()
    editor = page.locator("shop-promos-page .card").first
    await expect(editor).to_be_visible(timeout=15_000)
    await ui_set_platform_field(
        editor.locator("platform-field[type='string']").first,
        "Скидка 15% на заказ",
    )
    await ui_set_platform_field(
        editor.locator("platform-field[type='number']").first, "15"
    )
    save_btn = editor.locator(".actions platform-button[variant='primary']")
    await expect(save_btn).to_be_enabled(timeout=10_000)
    await scenario.step(
        "Редактор акции",
        page,
        screenshot_name="promo-editor",
        label_en="Promo editor",
        details=(
            "Заполняем название и размер скидки — шаблон «Процент на "
            "заказ» выбран по умолчанию. Условия и расписание "
            "необязательны: без них акция работает всегда."
        ),
        details_en=(
            "Fill in the name and discount size — the order percent "
            "template is selected by default. Conditions and schedule "
            "are optional: without them the promo always applies."
        ),
    )

    await save_btn.click()
    promo_card = page.locator("shop-promos-page .card.promo").first
    await expect(promo_card).to_be_visible(timeout=15_000)
    await expect(
        promo_card.locator(".name")
    ).to_have_text("Скидка 15% на заказ", timeout=10_000)
    await scenario.step(
        "Акция создана и активна",
        page,
        screenshot_name="promo-created",
        label_en="Promo created and active",
        details=(
            "Акция появилась в списке с описанием скидки. Переключатель "
            "справа позволяет временно выключить её без удаления."
        ),
        details_en=(
            "The promo appeared in the list with its discount "
            "description. The switch on the right pauses it without "
            "deleting."
        ),
    )

    _ = await page.goto(
        f"{_page_url(storefront.slug)}?tmode=light", wait_until="load"
    )
    await expect(page.locator(".item").first).to_be_visible(timeout=30_000)
    await page.locator(
        f".item[data-pid='{storefront.plain_product_id}'] .add"
    ).click()
    await expect(page.locator("#cart.show")).to_be_visible()
    await page.locator("#cart").click()
    await expect(page.locator("#sheet.show")).to_be_visible()
    savings = page.locator("#savings .save")
    await expect(savings).to_be_visible(timeout=20_000)
    await expect(savings).to_contain_text("Скидка 15% на заказ")
    await scenario.step(
        "Скидка видна покупателю",
        page,
        screenshot_name="storefront-savings",
        label_en="Discount visible to the customer",
        details=(
            "Покупатель добавляет позицию — в корзине строкой "
            "«Выгода» видна скидка с названием акции и новая сумма. "
            "Ничего настраивать на витрине не нужно."
        ),
        details_en=(
            "The customer adds an item — the cart shows a Savings "
            "line with the promo name and the new total. Nothing to "
            "configure on the storefront."
        ),
    )
