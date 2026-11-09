"""Документационный сценарий Shop: первый магазин от создания до витрины.

Пользовательский маршрут без API-подготовки: форма на главной Shop →
раздел меню → позиция → публикация → проверка витрины глазами покупателя.
"""

from __future__ import annotations

import asyncio

import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.shop_e2e_helpers import (
    SHOP_PUBLIC_API,
    shop_e2e_add_category,
    shop_e2e_add_product,
    shop_e2e_create_shop,
    shop_e2e_open_home,
    shop_e2e_open_storefront,
    shop_e2e_product_in_storefront,
    shop_e2e_publish,
    shop_e2e_set_point_on_map,
)
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)
_STOREFRONT_ORIGIN = "http://127.0.0.1:9027"


@pytest.mark.scenario(
    service="shop",
    tag="getting-started",
    doc_slug="shop-first-store",
    title="Создаём первый магазин и открываем витрину",
    title_en="Create your first store and open the storefront",
    description=(
        "**Для чего:** эта инструкция поможет завести первый магазин, "
        "добавить раздел меню с позицией и открыть витрину покупателям.\n\n"
        "**Какие проблемы решает:** вы узнаете, где создаётся магазин, как "
        "заполнить меню и как убедиться, что покупатели видят витрину.\n\n"
        "**Результат:** магазин опубликован, а позиция видна на витрине по "
        "публичной ссылке."
    ),
    description_en=(
        "**Purpose:** this guide helps you create your first store, add a "
        "menu section with an item, and open the storefront to customers.\n\n"
        "**Problems solved:** you will learn where stores are created, how to "
        "fill the menu, and how to verify customers see the storefront.\n\n"
        "**Result:** the store is published and the item is visible on the "
        "storefront via the public link."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_shop_first_store(
    scenario: ScenarioRecorder,
    shop_ui: AppUI,
    shop_client_http,
    ui_page_system: Page,
    unique_id: str,
) -> None:
    shop_name = f"Кофейня «Утро» {unique_id[:6]}"
    category_name = "Горячие напитки"
    product_name = "Капучино"
    product_price = "290"

    page = ui_page_system
    await page.set_viewport_size(_DESKTOP)

    await shop_e2e_open_home(page, shop_ui)
    await scenario.step(
        "Откройте сервис «Магазин»",
        page,
        screenshot_name="shop-home-opened",
        label_en="Open the Shop service",
        details=(
            "В списке сервисов компании выберите «Магазин». На главной странице "
            "показаны ваши магазины и блок «Новый магазин» в конце списка — "
            "с него начинается настройка."
        ),
        details_en=(
            "Choose «Shop» in the company services list. The home page shows "
            "your stores and the «New store» block at the end — setup starts there."
        ),
    )

    await shop_e2e_create_shop(page, shop_name)
    await scenario.step(
        "Введите название и создайте магазин",
        page,
        screenshot_name="shop-created-menu-opened",
        label_en="Enter a name and create the store",
        details=(
            "В поле «Название» впишите имя магазина — адрес витрины подставится "
            "автоматически. Нажмите кнопку создания: откроется раздел «Меню» "
            "нового магазина."
        ),
        details_en=(
            "Type the store name in the «Name» field — the storefront address "
            "fills in automatically. Click the create button: the new store's "
            "«Menu» section opens."
        ),
    )

    await shop_e2e_add_category(page, category_name)
    await scenario.step(
        "Добавьте раздел меню",
        page,
        screenshot_name="menu-category-added",
        label_en="Add a menu section",
        details=(
            "Слева находится дерево разделов. Нажмите строку добавления, "
            "впишите название раздела — например, «Горячие напитки» — и "
            "подтвердите клавишей Enter. Раздел появится в дереве."
        ),
        details_en=(
            "The section tree is on the left. Click the add row, type a section "
            "name — for example, «Hot drinks» — and press Enter. The section "
            "appears in the tree."
        ),
    )

    await shop_e2e_add_product(page, product_name, product_price)
    await scenario.step(
        "Добавьте первую позицию",
        page,
        screenshot_name="menu-product-added",
        label_en="Add the first item",
        details=(
            "Нажмите «+ Позиция» в шапке страницы. В окне заполните название "
            "и цену — остальное можно оставить пустым. Сохраните: карточка "
            "позиции появится в списке справа."
        ),
        details_en=(
            "Click «+ Item» in the page header. In the window fill in the name "
            "and price — the rest can stay empty. Save: the item card appears "
            "in the list on the right."
        ),
    )

    shop_id = page.url.split("/shop/")[-1].split("/")[0]
    await shop_e2e_set_point_on_map(page, shop_ui, shop_id)
    await scenario.step(
        "Отметьте точку магазина на карте",
        page,
        screenshot_name="settings-point-on-map",
        label_en="Mark the store point on the map",
        details=(
            "Откройте «Настройки» магазина. Кликните по карте в нужном месте — "
            "появится метка с адресом точки, затем сохраните. Без точки витрину "
            "опубликовать нельзя: покупатели не увидят магазин на карте."
        ),
        details_en=(
            "Open the store «Settings». Click the map where the store is — a "
            "pin with the point's coordinates appears, then save. Publishing "
            "requires the point: customers could not find the store otherwise."
        ),
    )

    link = await shop_e2e_publish(page, shop_ui)
    await scenario.step(
        "Опубликуйте витрину",
        page,
        screenshot_name="shop-published",
        label_en="Publish the storefront",
        details=(
            "Вернитесь на главную «Магазина». У готового магазина появляется "
            "кнопка публикации — нажмите её. После публикации у карточки "
            "появляется ссылка на витрину."
        ),
        details_en=(
            "Return to the Shop home page. A ready store shows a publish "
            "button — click it. After publishing, the card shows a storefront "
            "link."
        ),
    )

    href = await link.get_attribute("href")
    assert href is not None and SHOP_PUBLIC_API in href
    slug = href.rsplit("/", 1)[-1]
    # Снапшот витрины собирает фоновый воркер — ждём готовности по публичному API.
    for _ in range(90):
        resp = await shop_client_http.get(f"{SHOP_PUBLIC_API}/storefront/{slug}")
        if resp.status_code == 200:
            break
        await asyncio.sleep(0.5)
    else:
        raise AssertionError(f"витрина {slug} не опубликована за 45с")
    await shop_e2e_open_storefront(page, href, _STOREFRONT_ORIGIN)
    product = shop_e2e_product_in_storefront(page, product_name)
    await expect(product).to_be_visible(timeout=15_000)
    await scenario.step(
        "Откройте витрину и найдите позицию",
        page,
        screenshot_name="storefront-product-visible",
        label_en="Open the storefront and find the item",
        details=(
            "**Демонстрация результата.** Перейдите по ссылке витрины — так её "
            "видит покупатель. Найдите свою позицию в каталоге: она доступна "
            "для заказа.\n\n"
            "**Итог.** Теперь вы умеете создавать магазин, заполнять меню и "
            "публиковать витрину, проверяя её глазами покупателя."
        ),
        details_en=(
            "**Result demonstration.** Follow the storefront link — this is "
            "what a customer sees. Find your item in the catalog: it is "
            "available for ordering.\n\n"
            "**Summary.** Now you can create a store, fill the menu, and "
            "publish the storefront, checking it through a customer's eyes."
        ),
    )
