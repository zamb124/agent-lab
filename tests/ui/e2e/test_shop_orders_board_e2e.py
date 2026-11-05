"""Доска заказов Shop — живые обновления, тосты, бейдж и лейаут в браузере.

Продовый путь: Chromium, системный администратор в SPA :9027, заказы
создаются через реальный публичный REST витрины (customer-auth фикстуры) —
`shop/order/*` публикуется в настоящий Redis bus и доезжает до открытой
страницы через Centrifugo, как на проде.
"""

from __future__ import annotations

import re

import httpx2
import pytest_asyncio
from playwright.async_api import Page, expect

from tests.fixtures.shop import PUBLIC_PREFIX
from tests.ui.apps import SERVICE_UI_REGISTRY
from tests.ui.e2e.test_shop_storefront_desktop import (
    Storefront,
    _create_storefront,
)
from tests.ui.e2e_worker import ui_e2e_scope_headers
from tests.ui.harness import AppUI

_SHOP_UI = AppUI(SERVICE_UI_REGISTRY["shop"])
_PRODUCTS_PER_CATEGORY = 6


def _board_url(shop_id: str) -> str:
    return f"{_SHOP_UI.spa_url()}{shop_id}/orders"


def _menu_url(shop_id: str) -> str:
    return f"{_SHOP_UI.spa_url()}{shop_id}/menu"


def _order_body(product_ids: list[str], **overrides: object) -> dict[str, object]:
    return {
        "items": [{"product_id": pid, "qty": 1} for pid in product_ids],
        "customer_name": "Иван",
        "delivery_type": "pickup",
        **overrides,
    }


async def _create_order(public_client: httpx2.AsyncClient, slug: str, product_ids: list[str]) -> dict[str, object]:
    resp = await public_client.post(
        f"{PUBLIC_PREFIX}/storefront/{slug}/orders", json=_order_body(product_ids)
    )
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


async def _product_ids(client: httpx2.AsyncClient, headers: dict[str, str], shop_id: str) -> list[str]:
    resp = await client.get(f"/shop/api/v1/shops/{shop_id}/products", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    return [str(p["shop_product_id"]) for p in items]


@pytest_asyncio.fixture
async def board_storefront(
    shop_client_http: httpx2.AsyncClient,
    shop_worker: None,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> dict[str, object]:
    """Опубликованная витрина с шестью товарами + список product_id."""
    _ = shop_worker
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    storefront: Storefront = await _create_storefront(
        shop_client_http,
        headers,
        f"board-{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=_PRODUCTS_PER_CATEGORY,
        shop_patch={"delivery_enabled": True, "pickup_enabled": True},
    )
    ids = await _product_ids(shop_client_http, headers, storefront.shop_id)
    return {"storefront": storefront, "product_ids": ids, "headers": headers}


def _col(page: Page, status: str):
    return page.locator(f".col:has(button.col-title.{status})")


def _card(page: Page, code: str):
    return page.locator(".card", has_text=code)


class TestOrdersBoardLayout:
    """Лейаут доски: свёрнутые завершённые колонки, кнопки в ряд, скролл позиций."""

    async def test_collapsed_columns_and_card_layout(
        self,
        ui_page_system: Page,
        board_storefront: dict[str, object],
        shop_public_client: httpx2.AsyncClient,
    ) -> None:
        storefront = board_storefront["storefront"]
        assert isinstance(storefront, Storefront)
        product_ids = board_storefront["product_ids"]
        assert isinstance(product_ids, list)
        created = await _create_order(shop_public_client, storefront.slug, product_ids[:6])

        await ui_page_system.goto(_board_url(storefront.shop_id), wait_until="load")
        await expect(_col(ui_page_system, "new").locator(".card").first).to_be_visible()

        # done/cancelled — свёрнутые рельсы ~48px, остальные колонки занимают ширину.
        for status in ("done", "cancelled"):
            col = _col(ui_page_system, status)
            await expect(col).to_have_class(re.compile(r"collapsed"))
            box = await col.bounding_box()
            assert box is not None and box["width"] <= 80, f"{status} width {box}"
        new_box = await _col(ui_page_system, "new").bounding_box()
        assert new_box is not None and new_box["width"] >= 200

        # Действия карточки — одна строка, две кнопки.
        card = _card(ui_page_system, str(created["public_code"]))
        buttons = card.locator(".card-actions platform-button")
        await expect(buttons).to_have_count(2)
        b0 = await buttons.nth(0).bounding_box()
        b1 = await buttons.nth(1).bounding_box()
        assert b0 is not None and b1 is not None
        assert abs(b0["y"] - b1["y"]) < 2, "кнопки не в одной строке"

        # Шесть позиций: .items ограничен по высоте и скроллится.
        items_box = card.locator(".items")
        dims = await items_box.evaluate(
            "(el) => ({client: el.clientHeight, scroll: el.scrollHeight})"
        )
        assert dims["client"] <= 110
        assert dims["scroll"] > dims["client"]

        # Клик по свёрнутой колонке разворачивает её.
        await _col(ui_page_system, "done").locator("button.col-title.done").click()
        await expect(_col(ui_page_system, "done")).not_to_have_class(re.compile(r"collapsed"))


class TestOrdersBoardLive:
    """Живые обновления: push создаёт карточку с тостом и подсветкой, статус — moved."""

    async def test_new_order_toast_and_moved_card(
        self,
        ui_page_system: Page,
        board_storefront: dict[str, object],
        shop_public_client: httpx2.AsyncClient,
    ) -> None:
        storefront = board_storefront["storefront"]
        assert isinstance(storefront, Storefront)
        product_ids = board_storefront["product_ids"]
        assert isinstance(product_ids, list)
        await _create_order(shop_public_client, storefront.slug, product_ids[:1])

        await ui_page_system.goto(_board_url(storefront.shop_id), wait_until="load")
        await expect(_col(ui_page_system, "new").locator(".card").first).to_be_visible()

        # Заказ создаётся пока страница открыта: push → тост + карточка с moved.
        created = await _create_order(shop_public_client, storefront.slug, product_ids[:2])
        code = str(created["public_code"])
        toast = ui_page_system.locator("glass-toast", has_text=code)
        await expect(toast).to_be_visible(timeout=15_000)
        card = _card(ui_page_system, f"#{code}")
        await expect(card).to_be_visible()
        await expect(card).to_have_class(re.compile(r"moved"))

    async def test_status_change_moves_card_with_animation(
        self,
        ui_page_system: Page,
        board_storefront: dict[str, object],
        shop_public_client: httpx2.AsyncClient,
    ) -> None:
        storefront = board_storefront["storefront"]
        assert isinstance(storefront, Storefront)
        product_ids = board_storefront["product_ids"]
        assert isinstance(product_ids, list)
        created = await _create_order(shop_public_client, storefront.slug, product_ids[:1])
        code = str(created["public_code"])

        await ui_page_system.goto(_board_url(storefront.shop_id), wait_until="load")
        card = _card(ui_page_system, f"#{code}")
        await expect(card).to_be_visible()

        await card.locator("platform-button").first.click()
        moved = _col(ui_page_system, "accepted").locator(".card.moved", has_text=f"#{code}")
        await expect(moved).to_be_visible(timeout=15_000)

    async def test_sidebar_badge_counts_active_orders(
        self,
        ui_page_system: Page,
        board_storefront: dict[str, object],
        shop_public_client: httpx2.AsyncClient,
    ) -> None:
        storefront = board_storefront["storefront"]
        assert isinstance(storefront, Storefront)
        product_ids = board_storefront["product_ids"]
        assert isinstance(product_ids, list)
        await _create_order(shop_public_client, storefront.slug, product_ids[:1])
        await _create_order(shop_public_client, storefront.slug, product_ids[1:2])

        # Бейдж виден и вне страницы заказов — счётчик живёт на push.
        await ui_page_system.goto(_menu_url(storefront.shop_id), wait_until="load")
        badge = ui_page_system.locator(".nav-item .nav-badge")
        await expect(badge).to_have_text("2", timeout=15_000)

        await ui_page_system.goto(_board_url(storefront.shop_id), wait_until="load")
        await expect(badge).to_have_text("2")
