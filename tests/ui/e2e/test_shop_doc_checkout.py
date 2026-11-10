"""Документационный сценарий Shop: заказ на витрине глазами покупателя.

Маршрут покупателя: открыть витрину на телефоне, добавить позицию в
корзину, указать адрес доставки, войти по номеру телефона и получить
номер заказа.
"""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.e2e.test_shop_customer_auth_e2e import _page_url
from tests.ui.e2e.test_shop_delivery_e2e import (
    _cart_to_sheet,
    _emulator_auth,
    zoned_storefront,  # noqa: F401 — фикстура
)
from tests.ui.e2e.test_shop_feed_e2e import _PHONE
from tests.ui.e2e.test_shop_storefront_desktop import Storefront
from tests.ui.scenario_doc import ScenarioRecorder


@pytest.mark.scenario(
    service="shop",
    tag="storefront",
    doc_slug="storefront-checkout",
    title="Заказ на витрине глазами покупателя",
    title_en="Ordering on the storefront as a customer",
    description=(
        "**Для чего:** увидеть, что чувствует ваш покупатель — от "
        "открытия меню до номера заказа, без всяких установок.\n\n"
        "**Какие проблемы решает:** непонятно, удобно ли заказывать у "
        "вас. Здесь весь путь: корзина, адрес с подсказками, зона "
        "доставки, вход по телефону и готовый заказ.\n\n"
        "**Результат:** заказ оформлен и попал в личный кабинет "
        "покупателя — вкладка «Заказы» сигналит активной точкой."
    ),
    description_en=(
        "**Purpose:** see what your customer experiences — from opening "
        "the menu to the order number, no setup needed.\n\n"
        "**Problems solved:** it is unclear whether ordering from you is "
        "convenient. Here is the whole path: cart, address suggestions, "
        "delivery zone, phone sign-in and a ready order.\n\n"
        "**Result:** the order is placed and sits in the customer's "
        "account — the Orders tab signals with an active dot."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_storefront_checkout(
    page: Page,
    zoned_storefront: Storefront,
    unique_id: str,
    scenario: ScenarioRecorder,
) -> None:
    await page.set_viewport_size(_PHONE)

    _ = await page.goto(
        f"{_page_url(zoned_storefront.slug)}?tmode=light", wait_until="load"
    )
    await expect(page.locator(".item").first).to_be_visible(timeout=30_000)
    await scenario.step(
        "Витрина на телефоне покупателя",
        page,
        screenshot_name="storefront-menu",
        label_en="Storefront on the customer's phone",
        details=(
            "Покупатель открывает ссылку на витрину и видит меню с "
            "категориями и ценами. У каждой позиции — кнопка добавления "
            "в корзину."
        ),
        details_en=(
            "The customer opens the storefront link and sees the menu "
            "with categories and prices. Each item has an add-to-cart "
            "button."
        ),
    )

    await page.locator(
        f".item[data-pid='{zoned_storefront.plain_product_id}'] .add"
    ).click()
    await expect(page.locator("#cart.show")).to_be_visible()
    await page.locator("#cart").click()
    await expect(page.locator("#sheet.show")).to_be_visible()
    await scenario.step(
        "Корзина и оформление",
        page,
        screenshot_name="cart-sheet",
        label_en="Cart and checkout",
        details=(
            "Внизу появилась корзина с суммой. Она открывает лист "
            "оформления: способ получения, адрес и детали заказа."
        ),
        details_en=(
            "A cart with the total appeared at the bottom. It opens the "
            "checkout sheet: pickup method, address and order details."
        ),
    )

    await page.locator("#ca").fill("Тверская")
    sug = page.locator("#caSug")
    await expect(sug.locator(".sugrow").first).to_be_visible(timeout=15_000)
    await sug.locator(".sugrow").first.click()
    await expect(page.locator("#zoneStat")).to_have_class(
        "zstat ok", timeout=15_000
    )
    await page.locator("#dflat").fill("12")
    await page.locator("#dentrance").fill("3")
    await scenario.step(
        "Адрес с подсказками и зоной доставки",
        page,
        screenshot_name="address-zone",
        label_en="Address suggestions and delivery zone",
        details=(
            "Адрес подсказывается по мере ввода — покупателю не нужно "
            "помнить точное написание. Система сразу проверяет, входит ли "
            "точка в зону доставки: зелёный бейдж — привезём."
        ),
        details_en=(
            "The address is suggested while typing — no need to remember "
            "the exact spelling. The system instantly checks whether the "
            "point falls in the delivery zone: green badge — we deliver."
        ),
    )

    await page.locator("#payBtn").click()
    await _emulator_auth(page, f"+7999{int(unique_id[:8], 16) % 10**7:07d}")
    await expect(page.locator(".done .code")).to_be_visible(timeout=20_000)
    await scenario.step(
        "Заказ создан",
        page,
        screenshot_name="order-done",
        label_en="Order created",
        details=(
            "Покупатель подтверждает номер телефона — пароль и регистрация "
            "не нужны. Заказ получает номер и сразу уходит в вашу доску "
            "заказов."
        ),
        details_en=(
            "The customer confirms their phone number — no password or "
            "registration needed. The order gets a number and goes "
            "straight to your orders board."
        ),
    )

    _ = await page.goto(
        f"{_page_url(zoned_storefront.slug)}?tmode=light", wait_until="load"
    )
    orders_tab = page.locator('.acctnav [data-tab="orders"]')
    await expect(orders_tab).to_have_class("has-active", timeout=15_000)
    await scenario.step(
        "Заказ в личном кабинете",
        page,
        screenshot_name="orders-active",
        label_en="Order in the account",
        details=(
            "Вернувшись на витрину, покупатель видит пульсирующую точку "
            "на вкладке «Заказы» — там статус его заказа в реальном "
            "времени."
        ),
        details_en=(
            "Back on the storefront, the customer sees a pulsing dot on "
            "the Orders tab — that is where the order status lives in "
            "real time."
        ),
    )


@pytest.mark.scenario(
    service="shop",
    tag="storefront",
    doc_slug="storefront-mobile",
    title="Витрина на телефоне покупателя",
    title_en="The storefront on the customer's phone",
    description=(
        "**Для чего:** большинство заказов приходят с телефона — здесь "
        "видно, как ваша витрина выглядит и работает в руке.\n\n"
        "**Какие проблемы решает:** меню, корзина и оформление сделаны "
        "под палец: карточки крупные, корзина выезжает снизу, кабинет — "
        "вкладками. Ничего устанавливать не нужно.\n\n"
        "**Результат:** покупатель проходит весь путь одной рукой: "
        "меню → корзина → заказ → свой кабинет."
    ),
    description_en=(
        "**Purpose:** most orders come from phones — this shows how "
        "your storefront looks and works in a hand.\n\n"
        "**Problems solved:** menu, cart and checkout are made for a "
        "thumb: large cards, a bottom cart sheet, an account in tabs. "
        "Nothing to install.\n\n"
        "**Result:** the customer walks the whole path one-handed: "
        "menu → cart → order → account."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_storefront_mobile(
    page: Page,
    zoned_storefront: Storefront,
    scenario: ScenarioRecorder,
) -> None:
    await page.set_viewport_size(_PHONE)
    _ = await page.goto(
        f"{_page_url(zoned_storefront.slug)}?tmode=light", wait_until="load"
    )
    await expect(page.locator(".item").first).to_be_visible(timeout=30_000)
    await scenario.step(
        "Меню на телефоне",
        page,
        screenshot_name="mobile-menu",
        label_en="Menu on the phone",
        details=(
            "Витрина открывается прямо по ссылке — приложение не нужно. "
            "Карточки блюд крупные, цена и кнопка «+» под большим "
            "пальцем."
        ),
        details_en=(
            "The storefront opens straight from a link — no app needed. "
            "Dish cards are large, price and the + button sit under the "
            "thumb."
        ),
    )

    await page.locator(
        f".item[data-pid='{zoned_storefront.plain_product_id}'] .add"
    ).click()
    await expect(page.locator("#cart.show")).to_be_visible()
    await page.locator("#cart").click()
    await expect(page.locator("#sheet.show")).to_be_visible()
    await scenario.step(
        "Корзина выезжает снизу",
        page,
        screenshot_name="mobile-cart-sheet",
        label_en="Cart slides from the bottom",
        details=(
            "Корзина — выезжающий лист снизу экрана, как в привычных "
            "приложениях доставки. Сумма и кнопка оформления всегда "
            "на виду."
        ),
        details_en=(
            "The cart is a bottom sheet, like in familiar delivery "
            "apps. Total and the checkout button are always visible."
        ),
    )
