"""Документационный сценарий Shop: настройки магазина.

Маршрут владельца: «Настройки» → адрес опубликованной витрины →
часы работы пресетом «Каждый день» → витрина показывает бейдж
«Открыто/Откроемся» рядом с названием.
"""

from __future__ import annotations

import httpx2
import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.test_shop_customer_auth_e2e import _page_url
from tests.ui.e2e.test_shop_storefront_desktop import _create_storefront
from tests.ui.e2e_worker import ui_e2e_scope_headers
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="shop",
    tag="settings",
    doc_slug="shop-settings",
    title="Настройки магазина: адрес витрины и часы работы",
    title_en="Shop settings: storefront link and working hours",
    description=(
        "**Для чего:** в настройках собраны адрес витрины, профиль, "
        "часы работы и способы выдачи заказов — всё, что видит "
        "покупатель на витрине.\n\n"
        "**Какие проблемы решает:** ссылка на витрину копируется "
        "одной кнопкой, а часы работы задаются готовым пресетом — "
        "витрина сама показывает «Открыто» или «Откроемся» и не даёт "
        "оформить заказ вне времени работы.\n\n"
        "**Результат:** ссылка на витрину скопирована; витрина "
        "показывает часы работы рядом с названием."
    ),
    description_en=(
        "**Purpose:** shop settings hold the storefront link, "
        "profile, working hours and order handover — everything the "
        "customer sees on the storefront.\n\n"
        "**Problems solved:** the storefront link is copied with one "
        "button, and working hours are set with a ready preset — the "
        "storefront itself shows Open or Opens later and blocks "
        "ordering outside working time.\n\n"
        "**Result:** the storefront link is copied; the storefront "
        "shows working hours next to the name."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180, func_only=True)
async def test_shop_settings(
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
        f"set{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=1,
        shop_patch={"pickup_enabled": True},
    )

    await shop_ui.open(page)
    await page.set_viewport_size(_DESKTOP)
    await page.goto(
        f"{shop_ui.spa_url()}{storefront.shop_id}/settings",
        wait_until="load",
    )
    hero = page.locator("shop-settings-page .hero.published")
    await expect(hero).to_be_visible(timeout=45_000)
    await expect(hero.locator(".link-chip .url")).to_contain_text(
        storefront.slug
    )
    await scenario.step(
        "Адрес витрины",
        page,
        screenshot_name="settings-storefront-link",
        label_en="Storefront link",
        details=(
            "Раздел «Витрина» показывает статус «Опубликована» и "
            "готовую ссылку — её копируют в соцсети и рекламу кнопкой "
            "рядом. «Открыть витрину» показывает страницу глазами "
            "покупателя, «Приостановить» временно скрывает её."
        ),
        details_en=(
            "The Storefront section shows Published status and the "
            "ready link — copied to socials and ads with the button "
            "next to it. Open storefront shows the page as the "
            "customer sees it, Suspend temporarily hides it."
        ),
    )

    await page.goto(
        f"{shop_ui.spa_url()}{storefront.shop_id}/settings?section=hours",
        wait_until="load",
    )
    editor = page.locator("shop-settings-page shop-hours-editor")
    await expect(editor).to_be_visible(timeout=30_000)
    await editor.locator(".preset").first.click()
    await expect(editor.locator(".day").first).not_to_have_class(
        "day off", timeout=10_000
    )
    await scenario.step(
        "Часы работы пресетом",
        page,
        screenshot_name="settings-hours-editor",
        label_en="Working hours preset",
        details=(
            "Раздел «Часы работы» задаёт расписание недели. Пресет "
            "«Каждый день» ставит 9:00–22:00 на всю неделю сразу; "
            "отдельный день меняют полями времени или выключают "
            "тумблером."
        ),
        details_en=(
            "The Working hours section schedules the week. The Every "
            "day preset sets 9:00–22:00 for the whole week at once; a "
            "single day is changed with the time fields or switched "
            "off with its toggle."
        ),
    )

    save = page.locator(
        "shop-settings-page .savebar platform-button[variant='primary']"
    )
    await save.click()
    await expect(
        page.locator("shop-settings-page .savebar")
    ).to_have_count(0, timeout=30_000)

    _ = await page.goto(
        f"{_page_url(storefront.slug)}?tmode=light", wait_until="load"
    )
    await expect(page.locator(".item").first).to_be_visible(timeout=30_000)
    badge = page.locator(".meta .ob-open, .meta .ob-closed")
    await expect(badge).to_be_visible(timeout=20_000)
    await scenario.step(
        "Часы работы на витрине",
        page,
        screenshot_name="storefront-hours-badge",
        label_en="Working hours on the storefront",
        details=(
            "Витрина показывает часы рядом с названием: «Открыто» "
            "когда магазин работает, «Откроемся» с ближайшим "
            "временем — когда нет. Покупатель сразу понимает, "
            "примут ли заказ."
        ),
        details_en=(
            "The storefront shows hours next to the name: Open while "
            "the shop works, Opens later with the nearest time "
            "otherwise. The customer knows at once whether an order "
            "will be accepted."
        ),
    )
