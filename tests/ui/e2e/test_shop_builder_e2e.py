"""Конструктор витрины в браузере: тумблеры функций и редактор лояльности.

Продовый путь: реальный SPA конструктора → platform-switch/platform-field →
те же op_* и REST, что у директора магазина. Проверка персиста — API
``GET /shops/{id}/loyalty`` и блок ``loyalty`` в публичном снапшоте.
"""

from __future__ import annotations

import re

import httpx2
import pytest
import pytest_asyncio
from playwright.async_api import Page, ViewportSize, expect

from tests.ui.apps import SERVICE_UI_REGISTRY
from tests.ui.e2e.test_shop_feed_e2e import _shot
from tests.ui.e2e.test_shop_storefront_desktop import (
    _SHOP_API,
    _SHOP_PUBLIC,
    Storefront,
    _create_storefront,
)
from tests.ui.e2e_worker import ui_e2e_scope_headers
from tests.ui.harness import AppUI

_SHOP_UI = AppUI(SERVICE_UI_REGISTRY["shop"])
_DESKTOP = ViewportSize(width=1440, height=900)


@pytest_asyncio.fixture
async def builder_storefront(
    shop_client_http: httpx2.AsyncClient,
    shop_worker: None,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> Storefront:
    """Минимальная витрина для конструктора: каталог есть, функции дефолтные."""
    return await _create_storefront(
        shop_client_http,
        {**auth_headers_system, **ui_e2e_scope_headers()},
        f"bld{unique_id[:8]}",
        categories=("Меню",),
        products_per_category=1,
    )


async def _wait_snapshot_loyalty(
    client: httpx2.AsyncClient, slug: str, goal: int
) -> None:
    """Снапшот догоняет фичу и программу: ребилд — через shop_worker."""
    import asyncio

    deadline = asyncio.get_running_loop().time() + 30
    while True:
        resp = await client.get(f"{_SHOP_PUBLIC}/storefront/{slug}")
        if resp.status_code == 200:
            body = resp.json()
            feat = body.get("features") or {}
            loy = body.get("loyalty") or {}
            if feat.get("loyalty") is True and loy.get("orders_goal") == goal:
                return
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"снапшот {slug} без loyalty: {resp.status_code} {body!r}")
        await asyncio.sleep(0.5)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_builder_features_and_loyalty_program(
    ui_page_system: Page,
    builder_storefront: Storefront,
    shop_client_http: httpx2.AsyncClient,
    auth_headers_system: dict[str, str],
) -> None:
    """Тумблер «Лояльность» открывает редактор программы; save → API и снапшот."""
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    await ui_page_system.set_viewport_size(_DESKTOP)
    await ui_page_system.goto(
        f"{_SHOP_UI.spa_url()}{builder_storefront.shop_id}/builder",
        wait_until="load",
    )
    await expect(ui_page_system.locator(".feature").first).to_be_visible(
        timeout=45_000
    )

    loyalty_row = ui_page_system.locator(".feature").filter(
        has_text=re.compile("Лояльность|Loyalty")
    )
    await expect(loyalty_row).to_be_visible(timeout=15_000)
    await loyalty_row.locator("platform-switch").click()
    await expect(ui_page_system.locator(".loyprog")).to_be_visible(timeout=15_000)

    goal_field = ui_page_system.locator(".loyprog platform-field").nth(0)
    await goal_field.locator("input").fill("2")
    await goal_field.locator("input").press("Tab")
    await ui_page_system.locator(".lseg button", has_text="%").click()
    await _shot(ui_page_system, "builder-loyalty", builder_storefront.slug)

    save = ui_page_system.locator("platform-button[variant=primary]")
    await save.click()
    await expect(save).to_have_attribute("disabled", "", timeout=15_000)

    resp = await shop_client_http.get(
        f"{_SHOP_API}/shops/{builder_storefront.shop_id}/loyalty", headers=headers
    )
    assert resp.status_code == 200, resp.text
    program = resp.json()
    assert program["orders_goal"] == 2
    assert program["reward_kind"] == "discount_percent"
    assert program["reward_value"] == 10

    await _wait_snapshot_loyalty(
        shop_client_http, builder_storefront.slug, goal=2
    )

    # Перезагрузка: редактор гидрируется тем же состоянием (персист обеих осей).
    await ui_page_system.reload(wait_until="load")
    await expect(ui_page_system.locator(".loyprog")).to_be_visible(timeout=45_000)
    goal_input = ui_page_system.locator(".loyprog platform-field").nth(0).locator("input")
    await expect(goal_input).to_have_value("2", timeout=15_000)
    await _shot(ui_page_system, "builder-loyalty-reload", builder_storefront.slug)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(180)
async def test_builder_reviews_toggle_persists(
    ui_page_system: Page,
    builder_storefront: Storefront,
    shop_client_http: httpx2.AsyncClient,
    auth_headers_system: dict[str, str],
) -> None:
    """Тумблер «Отзывы» пишет в features.reviews, а не в соседнюю ось
    (регрессия бага, когда _setFeature падал в _favorites)."""
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    await ui_page_system.set_viewport_size(_DESKTOP)
    await ui_page_system.goto(
        f"{_SHOP_UI.spa_url()}{builder_storefront.shop_id}/builder",
        wait_until="load",
    )
    await expect(ui_page_system.locator(".feature").first).to_be_visible(
        timeout=45_000
    )
    reviews_row = ui_page_system.locator(".feature").filter(
        has_text=re.compile("Отзывы|Reviews")
    )
    await reviews_row.locator("platform-switch").click()
    save = ui_page_system.locator("platform-button[variant=primary]")
    await save.click()
    await expect(save).to_have_attribute("disabled", "", timeout=15_000)

    resp = await shop_client_http.get(
        f"{_SHOP_API}/shops/{builder_storefront.shop_id}", headers=headers
    )
    assert resp.status_code == 200, resp.text
    features = resp.json()["features"]
    assert features["reviews"] is False, features
    assert features["favorites"] is not False, features
