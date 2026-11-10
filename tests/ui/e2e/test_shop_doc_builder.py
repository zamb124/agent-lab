"""Документационный сценарий Shop: конструктор витрины.

Маршрут владельца: раздел «Конструктор» → тумблер «Лояльность» →
программа наград → покупатель видит условие в корзине витрины.
"""

from __future__ import annotations

import re

import httpx2
import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.test_shop_builder_e2e import _wait_snapshot_loyalty
from tests.ui.e2e.test_shop_customer_auth_e2e import _page_url
from tests.ui.e2e.test_shop_storefront_desktop import _create_storefront
from tests.ui.e2e_worker import ui_e2e_scope_headers
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="shop",
    tag="menu",
    doc_slug="builder-sections",
    title="Конструктор витрины: программа лояльности",
    title_en="Storefront builder: the loyalty program",
    description=(
        "**Для чего:** конструктор собирает витрину — включённые "
        "функции сразу появляются у покупателя. Программа лояльности "
        "возвращает гостей подарком-скидкой за повторные заказы.\n\n"
        "**Какие проблемы решает:** постоянный покупатель получает "
        "награду сам — витрина считает заказы и показывает условие "
        "прямо в корзине, а владелец настраивает всё одним тумблером.\n\n"
        "**Результат:** программа сохранена; в корзине витрины "
        "покупатель видит «Каждый N-й заказ — скидка»."
    ),
    description_en=(
        "**Purpose:** the builder assembles the storefront — enabled "
        "features appear to customers at once. The loyalty program "
        "brings guests back with a discount reward for repeat "
        "orders.\n\n"
        "**Problems solved:** the regular gets the reward by "
        "themselves — the storefront counts orders and shows the "
        "condition right in the cart, while the owner configures it "
        "with one switch.\n\n"
        "**Result:** the program is saved; the storefront cart tells "
        "the customer \"Every Nth order — a discount\"."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180, func_only=True)
async def test_builder_sections(
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
        f"bld{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=1,
        shop_patch={"pickup_enabled": True},
    )

    await shop_ui.open(page)
    await page.set_viewport_size(_DESKTOP)
    await page.goto(
        f"{shop_ui.spa_url()}{storefront.shop_id}/builder",
        wait_until="load",
    )
    await expect(page.locator(".feature").first).to_be_visible(
        timeout=45_000
    )
    await scenario.step(
        "Конструктор витрины",
        page,
        screenshot_name="builder-features",
        label_en="Storefront builder",
        details=(
            "Конструктор — это список функций витрины с "
            "переключателями: КБЖУ, «Сообщить о поступлении», "
            "избранное, отзывы и лояльность. Включённое появляется "
            "у покупателя сразу после сохранения."
        ),
        details_en=(
            "The builder is a list of storefront features with "
            "switches: nutrition facts, back-in-stock, favorites, "
            "reviews and loyalty. Everything enabled appears to the "
            "customer right after saving."
        ),
    )

    loyalty_row = page.locator(".feature").filter(
        has_text=re.compile("Лояльность|Loyalty")
    )
    await loyalty_row.locator("platform-switch").click()
    await expect(page.locator(".loyprog")).to_be_visible(timeout=15_000)
    goal_field = page.locator(".loyprog platform-field").nth(0)
    await goal_field.locator("input").fill("2")
    await goal_field.locator("input").press("Tab")
    await page.locator(".lseg button", has_text="%").click()
    await scenario.step(
        "Программа лояльности",
        page,
        screenshot_name="loyalty-editor",
        label_en="Loyalty program editor",
        details=(
            "Включаем «Лояльность» — открывается редактор: каждый "
            "2-й заказ даёт награду. Награда — процент скидки или "
            "фиксированная сумма на выбор."
        ),
        details_en=(
            "Switching Loyalty on opens the editor: every 2nd order "
            "earns a reward. The reward is a percent discount or a "
            "fixed amount of your choice."
        ),
    )

    save = page.locator("platform-button[variant=primary]")
    await save.click()
    await expect(save).to_have_attribute("disabled", "", timeout=15_000)
    await _wait_snapshot_loyalty(
        shop_client_http, storefront.slug, goal=2
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
    hint = page.locator("#loyRow.loyhint")
    await expect(hint).to_be_visible(timeout=20_000)
    await expect(hint).to_contain_text("скидка")
    await scenario.step(
        "Условие награды в корзине",
        page,
        screenshot_name="storefront-loyalty-hint",
        label_en="Reward condition in the cart",
        details=(
            "Покупатель открывает корзину и видит условие программы: "
            "«Каждый 2-й заказ — скидка 10%». Когда награда накопится, "
            "витрина сама предложит применить её тумблером."
        ),
        details_en=(
            "The customer opens the cart and sees the program "
            "condition: \"Every 2nd order — a 10% discount\". Once "
            "the reward is earned, the storefront offers to apply it "
            "with a switch."
        ),
    )
