"""Документационный сценарий Shop: входящие заказы на доске.

Маршрут продавца: открыть доску заказов, увидеть новый заказ от
покупателя и принять его в работу.
"""

from __future__ import annotations

import httpx2
import pytest
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.e2e.test_shop_orders_board_e2e import _create_order
from tests.ui.e2e.test_shop_storefront_desktop import Storefront, _create_storefront
from tests.ui.e2e_worker import ui_e2e_scope_headers
from tests.ui.harness import AppUI
from tests.ui.scenario_doc import ScenarioRecorder

_DESKTOP = ViewportSize(width=1440, height=900)


@pytest.mark.scenario(
    service="shop",
    tag="orders",
    doc_slug="incoming-orders-board",
    title="Входящие заказы: доска и принятие в работу",
    title_en="Incoming orders: the board and taking an order",
    description=(
        "**Для чего:** не потерять ни один заказ — все они летят на одну "
        "доску со статусами, без телефонных звонков и чатов.\n\n"
        "**Какие проблемы решает:** заказ из витрины легко пропустить. "
        "Доска показывает каждый заказ карточкой: состав, адрес, контакт "
        "— и кнопку «принять в работу».\n\n"
        "**Результат:** новый заказ принят и переехал в колонку «В "
        "работе» — покупатель видит статус у себя в кабинете."
    ),
    description_en=(
        "**Purpose:** never lose an order — they all land on one board "
        "with statuses, no phone calls or chats needed.\n\n"
        "**Problems solved:** a storefront order is easy to miss. The "
        "board shows every order as a card: items, address, contact — "
        "and a take-to-work button.\n\n"
        "**Result:** the new order is accepted and moved to the In "
        "progress column — the customer sees the status in their "
        "account."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_incoming_orders_board(
    shop_client_http: httpx2.AsyncClient,
    shop_public_client: httpx2.AsyncClient,
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
        f"board{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=2,
        shop_patch={"pickup_enabled": True},
    )

    order = await _create_order(
        shop_public_client,
        storefront.slug,
        [storefront.plain_product_id],
        customer_name="Мария",
    )
    code = str(order["public_code"])

    await shop_ui.open(page)
    await page.set_viewport_size(_DESKTOP)
    await page.goto(
        f"{shop_ui.spa_url()}{storefront.shop_id}/orders", wait_until="load"
    )
    new_col = page.locator(".col:has(button.col-title.new)")
    await expect(new_col.locator(".card").first).to_be_visible(timeout=30_000)
    await scenario.step(
        "Новый заказ на доске",
        page,
        screenshot_name="board-new",
        label_en="New order on the board",
        details=(
            "Заказ покупателя упал в колонку «Новые» сам — обновлять "
            "страницу не нужно. Карточка показывает номер, состав и "
            "данные покупателя."
        ),
        details_en=(
            "The customer's order landed in the New column by itself — "
            "no refresh needed. The card shows the number, items and "
            "customer details."
        ),
    )

    card = page.locator(".card", has_text=code)
    await expect(card).to_be_visible(timeout=15_000)
    accept_btn = card.locator(".card-actions platform-button").first
    await expect(accept_btn).to_be_visible()
    await accept_btn.click()
    accepted_col = page.locator(".col:has(button.col-title.accepted)")
    await expect(
        accepted_col.locator(".card", has_text=code)
    ).to_be_visible(timeout=15_000)
    await scenario.step(
        "Заказ принят в работу",
        page,
        screenshot_name="order-accepted",
        label_en="Order taken to work",
        details=(
            "Кнопка на карточке переводит заказ дальше по цепочке: "
            "«Новые» → «Принят» → «Готовится» → «Доставляется» → "
            "«Готов». Покупатель видит каждый шаг у себя."
        ),
        details_en=(
            "The card button moves the order along the chain: New → "
            "Accepted → Preparing → Delivering → Done. The customer "
            "sees every step."
        ),
    )


@pytest.mark.scenario(
    service="shop",
    tag="orders",
    doc_slug="order-status-flow",
    title="Статусы заказа: от принятия до выдачи",
    title_en="Order statuses: from acceptance to handout",
    description=(
        "**Для чего:** вся кухня и курьер видят одну и ту же ленту "
        "статусов — заказ нельзя «потерять» между этапами.\n\n"
        "**Какие проблемы решает:** без статусов покупатель звонит "
        "«а где мой заказ?», а кухня не знает, что готовить первым. "
        "Карточка сама ведёт заказ по цепочке.\n\n"
        "**Результат:** заказ прошёл «Принят» → «Готовится» → "
        "«Доставляется» → «Готов» — покупатель видел каждый шаг."
    ),
    description_en=(
        "**Purpose:** kitchen and courier see the same status feed — "
        "an order can't be lost between stages.\n\n"
        "**Problems solved:** without statuses the customer calls "
        "\"where is my order?\" and the kitchen doesn't know what to "
        "cook first. The card walks the order along the chain.\n\n"
        "**Result:** the order went Accepted → Preparing → Delivering "
        "→ Done — the customer saw every step."
    ),
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120, func_only=True)
async def test_order_status_flow(
    shop_client_http: httpx2.AsyncClient,
    shop_public_client: httpx2.AsyncClient,
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
        f"flow{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=2,
        shop_patch={"delivery_enabled": True, "pickup_enabled": True},
    )
    order = await _create_order(
        shop_public_client,
        storefront.slug,
        [storefront.plain_product_id],
        customer_name="Мария",
        delivery_type="delivery",
        address="Москва, Тверская 1",
    )
    code = str(order["public_code"])

    await shop_ui.open(page)
    await page.set_viewport_size(_DESKTOP)
    await page.goto(
        f"{shop_ui.spa_url()}{storefront.shop_id}/orders", wait_until="load"
    )
    card = page.locator(".card", has_text=code)
    await expect(card).to_be_visible(timeout=30_000)

    for status in ("accepted", "preparing", "delivering"):
        await card.locator(".card-actions platform-button").first.click()
        col = page.locator(f".col:has(button.col-title.{status})")
        await expect(col.locator(".card", has_text=code)).to_be_visible(
            timeout=15_000
        )
        card = col.locator(".card", has_text=code)

    await scenario.step(
        "Заказ в доставке",
        page,
        screenshot_name="order-delivering",
        label_en="Order out for delivery",
        details=(
            "Каждое нажатие кнопки на карточке двигает заказ на шаг "
            "дальше: «Принят» → «Готовится» → «Доставляется». Колонки "
            "показывают, сколько заказов на каждом этапе."
        ),
        details_en=(
            "Each card button press moves the order one step further: "
            "Accepted → Preparing → Delivering. Columns show how many "
            "orders sit at each stage."
        ),
    )

    await card.locator(".card-actions platform-button").first.click()
    done_col = page.locator(".col:has(button.col-title.done)")
    await page.locator("button.col-title.done").click()
    await expect(done_col.locator(".card", has_text=code)).to_be_visible(
        timeout=15_000
    )
    await scenario.step(
        "Заказ выдан",
        page,
        screenshot_name="order-done",
        label_en="Order handed out",
        details=(
            "Финальный шаг — «Готов»: заказ уехал в завершённую колонку. "
            "Она свёрнута справа, чтобы не отнимать место у активных "
            "заказов."
        ),
        details_en=(
            "The final step — Done: the order moved to the finished "
            "column. It stays collapsed on the right so active orders "
            "keep the space."
        ),
    )
