"""UI-хелперы сервиса Shop (магазин компании и публичная витрина).

Каждая функция инкапсулирует один пользовательский жест: переход по разделу,
заполнение формы, ожидание результата. Тела сценариев читаются как
последовательность действий пользователя.
"""

from __future__ import annotations

import re

from playwright.async_api import Locator, Page, expect

from tests.ui.harness import AppUI, ui_set_platform_field

SHOP_PUBLIC_API = "/shop/api/v1/public"


async def shop_e2e_open_home(page: Page, shop_ui: AppUI) -> None:
    """Открывает главную Shop: список магазинов и форма создания."""
    await shop_ui.open(page, wait_until="domcontentloaded")
    await shop_ui.expect_shell(page)
    await expect(page.locator("shop-home-page .create")).to_be_visible(timeout=30_000)


async def shop_e2e_create_shop(page: Page, name: str) -> None:
    """Заполняет форму «Новый магазин» и отправляет → переход в раздел меню."""
    create = page.locator("shop-home-page .create")
    fields = create.locator("platform-field")
    await ui_set_platform_field(fields.nth(0), name)
    submit = create.locator("platform-button[variant='primary']")
    await expect(submit).to_be_enabled(timeout=5_000)
    await submit.click()
    await expect(page.locator("shop-menu-page")).to_be_visible(timeout=30_000)


async def shop_e2e_add_category(page: Page, name: str) -> Locator:
    """Создаёт раздел верхнего уровня через inline-строку дерева категорий."""
    tree = page.locator("shop-menu-page shop-category-tree")
    await expect(tree).to_be_visible(timeout=15_000)
    add_row = tree.locator(".add-row").last
    await expect(add_row).to_be_visible(timeout=10_000)
    await add_row.click()
    edit_input = tree.locator(".edit-input")
    await expect(edit_input).to_be_visible(timeout=10_000)
    await edit_input.fill(name)
    await edit_input.press("Enter")
    node = tree.locator(".treeitem", has_text=name).first
    await expect(node).to_be_visible(timeout=15_000)
    return node


async def shop_e2e_add_product(page: Page, name: str, price: str) -> Locator:
    """Открывает модалку товара, заполняет название и цену, сохраняет."""
    add_btn = page.locator(
        "shop-menu-page .head-actions platform-button[variant='primary']"
    ).first
    await expect(add_btn).to_be_visible(timeout=15_000)
    await add_btn.click()
    modal = page.locator("shop-product-modal").first
    await expect(modal).to_be_visible(timeout=15_000)
    name_field = modal.locator(".fields > platform-field[type='string']").first
    await ui_set_platform_field(name_field, name)
    price_field = modal.locator(".row2 platform-field[type='number']").first
    await ui_set_platform_field(price_field, price)
    save = modal.locator(".actions platform-button[variant='primary']")
    await expect(save).to_be_enabled(timeout=5_000)
    await save.click()
    await expect(modal).to_be_hidden(timeout=15_000)
    card = page.locator("shop-menu-page .card .pname", has_text=name).first
    await expect(card).to_be_visible(timeout=15_000)
    return card


async def shop_e2e_set_point_on_map(page: Page, shop_ui: AppUI, shop_id: str) -> None:
    """Ставит обязательную точку магазина кликом по карте в настройках."""
    await page.goto(
        f"{shop_ui.spa_url()}{shop_id}/settings?section=delivery",
        wait_until="domcontentloaded",
    )
    wrap = page.locator(".zone-map-wrap")
    await expect(wrap).to_be_visible(timeout=45_000)
    # pm-overlay перехватывает клики, пока карта не прогрузилась.
    await expect(wrap.locator(".maplibregl-canvas")).to_be_visible(timeout=45_000)
    await expect(wrap.locator(".pm-overlay")).to_have_count(0, timeout=45_000)
    map_el = wrap.locator("platform-map")
    await map_el.click(position={"x": 260, "y": 120})
    await expect(wrap.locator(".empty-badge.point")).to_have_count(0, timeout=15_000)
    await expect(wrap.locator(".maplibregl-marker")).to_have_count(1, timeout=15_000)
    save = page.locator(".savebar platform-button[variant='primary']")
    await expect(save).to_be_enabled(timeout=15_000)
    await save.click()
    await expect(page.locator(".savebar")).to_have_count(0, timeout=30_000)


async def shop_e2e_publish(page: Page, shop_ui: AppUI) -> Locator:
    """Публикует магазин с главной и ждёт появления ссылки на витрину."""
    await shop_e2e_open_home(page, shop_ui)
    publish = page.locator("shop-home-page .publish-cta platform-button").first
    await expect(publish).to_be_visible(timeout=15_000)
    await publish.click()
    link = page.locator("shop-home-page a.hint[href*='public/s/']").first
    await expect(link).to_be_visible(timeout=30_000)
    return link


async def shop_e2e_open_storefront(page: Page, href: str, base_url: str) -> None:
    """Открывает публичную витрину и ждёт появления каталога."""
    url = href if href.startswith("http") else f"{base_url}{href}"
    # tmode=light — штатный параметр витрины: док-скриншоты держим в светлой теме.
    sep = "&" if "?" in url else "?"
    await page.goto(f"{url}{sep}tmode=light", wait_until="load")
    await expect(page.locator(".item, .gcard").first).to_be_visible(timeout=60_000)


def shop_e2e_product_in_storefront(page: Page, name: str) -> Locator:
    """Локатор позиции на публичной витрине (карточка товара с названием)."""
    return page.locator(".item, .gcard", has_text=re.escape(name)).first
