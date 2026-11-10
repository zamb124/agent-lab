"""Документационный сценарий Shop: публикация витрины.

Маршрут владельца: магазин готов → «Опубликовать» → публичная
ссылка → витрина живая для покупателей.
"""

from __future__ import annotations

import httpx2
import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.shop_e2e_helpers import shop_e2e_publish
from tests.ui.e2e.test_shop_customer_auth_e2e import _page_url
from tests.ui.e2e.test_shop_storefront_desktop import _create_storefront
from tests.ui.e2e_worker import ui_e2e_scope_headers
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="shop",
    tag="storefront",
    doc_slug="publish-storefront",
    title="Публикация витрины и публичная ссылка",
    title_en="Publishing the storefront and the public link",
    description=(
        "**Для чего:** пока витрина не опубликована, её видите только "
        "вы. Одна кнопка делает её живой по постоянной ссылке.\n\n"
        "**Какие проблемы решает:** не нужен сайт и программист — "
        "ссылку на витрину можно сразу отправить покупателям, поставить "
        "в соцсети или в QR-код на столе.\n\n"
        "**Результат:** карточка магазина помечена «Опубликован», "
        "ссылка открывает меню для покупателей."
    ),
    description_en=(
        "**Purpose:** while unpublished, only you see the storefront. "
        "One button makes it live at a permanent link.\n\n"
        "**Problems solved:** no website or developer needed — send "
        "the link to customers, post it on socials, print it as a QR "
        "code on tables.\n\n"
        "**Result:** the shop card is marked Published and the link "
        "opens the menu for customers."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_publish_storefront(
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
        f"pub{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=2,
        shop_patch={"pickup_enabled": True},
    )

    await shop_ui.open(page)
    await page.set_viewport_size(_DESKTOP)
    await page.goto(shop_ui.spa_url(), wait_until="load")
    await expect(
        page.locator(".publish-cta platform-button").first
    ).to_be_visible(timeout=30_000)
    await scenario.step(
        "Магазин готов к публикации",
        page,
        screenshot_name="ready-to-publish",
        label_en="Ready to publish",
        details=(
            "Когда меню и оформление собраны, карточка магазина "
            "показывает кнопку публикации. До нажатия витрину видите "
            "только вы."
        ),
        details_en=(
            "Once the menu and design are set, the shop card shows "
            "the publish button. Before you press it, only you can "
            "see the storefront."
        ),
    )

    link = await shop_e2e_publish(page, shop_ui)
    href = (await link.get_attribute("href")) or ""
    await scenario.step(
        "Витрина опубликована",
        page,
        screenshot_name="published-link",
        label_en="Storefront published",
        details=(
            "«Опубликован» — появилась постоянная публичная ссылка. "
            "Её можно отправлять покупателям или печатать QR-кодом."
        ),
        details_en=(
            "Published — the permanent public link appeared. Send it "
            "to customers or print it as a QR code."
        ),
    )

    _ = href
    await page.goto(
        f"{_page_url(storefront.slug)}?tmode=light", wait_until="load"
    )
    await expect(page.locator(".item").first).to_be_visible(timeout=30_000)
    await scenario.step(
        "Витрина открыта покупателям",
        page,
        screenshot_name="storefront-live",
        label_en="Storefront is live",
        details=(
            "По ссылке открывается живая витрина: меню, корзина, "
            "оформление заказа — всё, что видит покупатель."
        ),
        details_en=(
            "The link opens a live storefront: menu, cart, checkout — "
            "everything the customer sees."
        ),
    )
