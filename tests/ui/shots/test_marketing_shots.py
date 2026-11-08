"""Маркетинговые кадры продуктов на реальном стеке и демо-данных.

Запуск (после `make test-up`):
    UI_E2E_USE_LVH_ME=1 uv run pytest tests/ui/shots -v

PNG пишутся в ``tests/ui/shots/out/``. Каждый кадр вручную проверяется
как маркетинговая картинка перед переносом в ``land/``.
"""

from __future__ import annotations

import pytest
from playwright.async_api import Page, expect

from tests.ui.apps import SERVICE_UI_REGISTRY
from tests.ui.harness import AppUI
from tests.ui.shots.conftest import (
    click_geo_map_at,
    dismiss_cookie_banner,
    settle_page,
    wait_geo_map_ready,
)
from tests.ui.shots.seed_content import SHOP_HOST_ORIGIN, SHOP_PUBLIC_API, api_origin

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(300)]


def _ui(service_key: str) -> AppUI:
    return AppUI(SERVICE_UI_REGISTRY[service_key])


def _shops(seeded: dict[str, object]) -> dict[str, dict[str, str]]:
    shops = seeded["shops"]
    assert isinstance(shops, dict)
    return shops


async def _goto(page: Page, url: str, *, settle_ms: int = 1500) -> None:
    await page.goto(url, wait_until="domcontentloaded")
    await settle_page(page, settle_ms)
    await page.evaluate("window.scrollTo(0, 0)")


# === Shop: публичная витрина (светлая тема, без auth) ===

CAFE_LIGHT = "?tmode=light&thero=cover"


async def _open_storefront(page: Page, slug: str, query: str = "") -> None:
    await _goto(
        page,
        f"{SHOP_HOST_ORIGIN}{SHOP_PUBLIC_API}/s/{slug}{query}",
        settle_ms=2500,
    )
    await expect(page.locator(".item").first).to_be_visible(timeout=30_000)


async def test_shot_shop_cafe_storefront(
    shot_anonymous_page: Page, marketing_seeded, save_shot
) -> None:
    slug = _shops(marketing_seeded)["cafe"]["slug"]
    await _open_storefront(shot_anonymous_page, slug, CAFE_LIGHT)
    await save_shot(shot_anonymous_page, "shop-cafe-storefront")


async def test_shot_shop_cafe_storefront_grid(
    shot_anonymous_page: Page, marketing_seeded, save_shot
) -> None:
    slug = _shops(marketing_seeded)["cafe"]["slug"]
    await _open_storefront(shot_anonymous_page, slug, CAFE_LIGHT)
    await shot_anonymous_page.evaluate("window.scrollBy(0, 600)")
    await shot_anonymous_page.wait_for_timeout(800)
    await save_shot(shot_anonymous_page, "shop-cafe-grid")


async def test_shot_shop_cafe_product_modal(
    shot_anonymous_page: Page, marketing_seeded, save_shot
) -> None:
    slug = _shops(marketing_seeded)["cafe"]["slug"]
    await _open_storefront(shot_anonymous_page, slug, CAFE_LIGHT)
    first = shot_anonymous_page.locator(".item").first
    await first.click()
    await shot_anonymous_page.wait_for_timeout(1200)
    await save_shot(shot_anonymous_page, "shop-cafe-product")


async def test_shot_shop_cafe_cart(
    shot_anonymous_page: Page, marketing_seeded, save_shot
) -> None:
    slug = _shops(marketing_seeded)["cafe"]["slug"]
    await _open_storefront(shot_anonymous_page, slug, CAFE_LIGHT)
    add = shot_anonymous_page.locator(".item .add").first
    await add.click()
    await shot_anonymous_page.wait_for_timeout(1000)
    await shot_anonymous_page.locator(".item .add").nth(1).click()
    await shot_anonymous_page.wait_for_timeout(1500)
    await save_shot(shot_anonymous_page, "shop-cafe-cart")


async def test_shot_shop_pizza_storefront(
    shot_anonymous_page: Page, marketing_seeded, save_shot
) -> None:
    slug = _shops(marketing_seeded)["pizza"]["slug"]
    await _open_storefront(shot_anonymous_page, slug)
    await save_shot(shot_anonymous_page, "shop-pizza-storefront")


async def test_shot_shop_market_storefront(
    shot_anonymous_page: Page, marketing_seeded, save_shot
) -> None:
    slug = _shops(marketing_seeded)["market"]["slug"]
    await _open_storefront(shot_anonymous_page, slug)
    await save_shot(shot_anonymous_page, "shop-market-storefront")


async def test_shot_shop_cafe_mobile(
    shot_anonymous_mobile: Page, marketing_seeded, save_shot
) -> None:
    slug = _shops(marketing_seeded)["cafe"]["slug"]
    await _open_storefront(shot_anonymous_mobile, slug, CAFE_LIGHT)
    await save_shot(shot_anonymous_mobile, "shop-cafe-mobile")


# === Shop: админка (dark, auth) ===


async def test_shot_shop_admin_home(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    await _goto(shot_desktop_page, f"{api_origin('shop')}/shop/", settle_ms=2500)
    await expect(
        shot_desktop_page.locator("shop-app, shop-home-page").first
    ).to_be_visible(timeout=30_000)
    await save_shot(shot_desktop_page, "shop-admin-home")


async def test_shot_shop_admin_menu(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    shop_id = _shops(marketing_seeded)["cafe"]["id"]
    await _goto(
        shot_desktop_page,
        f"{api_origin('shop')}/shop/{shop_id}/menu",
        settle_ms=3000,
    )
    await save_shot(shot_desktop_page, "shop-admin-menu")


async def test_shot_shop_admin_orders(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    shop_id = _shops(marketing_seeded)["cafe"]["id"]
    await _goto(
        shot_desktop_page,
        f"{api_origin('shop')}/shop/{shop_id}/orders",
        settle_ms=3000,
    )
    await save_shot(shot_desktop_page, "shop-admin-orders")


async def test_shot_shop_admin_builder(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    shop_id = _shops(marketing_seeded)["cafe"]["id"]
    await _goto(
        shot_desktop_page,
        f"{api_origin('shop')}/shop/{shop_id}/builder",
        settle_ms=3500,
    )
    await save_shot(shot_desktop_page, "shop-admin-builder")


# === CRM / NetWorkle ===


async def test_shot_crm_notes(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    await _goto(shot_desktop_page, f"{api_origin('crm')}/crm/notes", settle_ms=3000)
    await save_shot(shot_desktop_page, "crm-notes")


async def test_shot_crm_entities(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    await _goto(
        shot_desktop_page, f"{api_origin('crm')}/crm/entities", settle_ms=3000
    )
    await save_shot(shot_desktop_page, "crm-entities")


async def test_shot_crm_graph(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    await _goto(shot_desktop_page, f"{api_origin('crm')}/crm/graph", settle_ms=4000)
    await save_shot(shot_desktop_page, "crm-graph")


async def test_shot_crm_tasks(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    await _goto(shot_desktop_page, f"{api_origin('crm')}/crm/tasks", settle_ms=3000)
    await save_shot(shot_desktop_page, "crm-tasks")


# === Sync ===


async def test_shot_sync_chat(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    channel_id = str(marketing_seeded["sync"]["main_channel_id"])
    await _goto(
        shot_desktop_page,
        f"{api_origin('sync')}/sync/c/{channel_id}",
        settle_ms=3500,
    )
    await save_shot(shot_desktop_page, "sync-chat")


# === Worktracker ===


async def test_shot_worktracker_board(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    await _goto(
        shot_desktop_page, f"{api_origin('worktracker')}/worktracker/board",
        settle_ms=3000,
    )
    await save_shot(shot_desktop_page, "worktracker-board")


async def test_shot_worktracker_my(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    await _goto(
        shot_desktop_page, f"{api_origin('worktracker')}/worktracker/my",
        settle_ms=3000,
    )
    await save_shot(shot_desktop_page, "worktracker-my")


# === Wiki ===


async def test_shot_wiki_home(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    await _goto(shot_desktop_page, f"{api_origin('wiki')}/wiki/", settle_ms=3000)
    await save_shot(shot_desktop_page, "wiki-home")


async def test_shot_wiki_page(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    page_ids = marketing_seeded["wiki"]["page_ids"]
    page_id = page_ids[1] if len(page_ids) > 1 else page_ids[0]
    await _goto(
        shot_desktop_page,
        f"{api_origin('wiki')}/wiki/p/{page_id}",
        settle_ms=2500,
    )
    await expect(
        shot_desktop_page.locator("wiki-page-view .title-input")
    ).to_be_visible(timeout=20_000)
    await save_shot(shot_desktop_page, "wiki-page")


# === Office / Documents ===


async def test_shot_office_documents(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    await _goto(
        shot_desktop_page,
        f"{api_origin('office')}/documents/recent",
        settle_ms=3000,
    )
    await save_shot(shot_desktop_page, "office-documents")


async def test_shot_office_editor(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    file_ids = marketing_seeded["office"]["file_ids"]
    if not file_ids:
        pytest.skip("office files не загружены")
    await _goto(
        shot_desktop_page,
        f"{api_origin('office')}/documents/edit/{file_ids[0]}",
        settle_ms=8000,
    )
    await save_shot(shot_desktop_page, "office-editor")


# === Geo ===


async def test_shot_geo_overview(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    await _goto(shot_desktop_page, f"{api_origin('geo')}/geo/", settle_ms=2000)
    await wait_geo_map_ready(
        shot_desktop_page, sources={"pm-src-roads": 3, "pm-src-addresses": 1}
    )
    await save_shot(shot_desktop_page, "geo-overview")


async def test_shot_geo_map_lab(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    await _goto(
        shot_desktop_page, f"{api_origin('geo')}/geo/map-lab", settle_ms=2000
    )
    await wait_geo_map_ready(
        shot_desktop_page,
        zoom=15.2,
        sources={"pm-route": 1, "pm-iso": 2, "pm-src-roads": 3},
    )
    await save_shot(shot_desktop_page, "geo-map-lab")


_ROAD_A = (37.6170, 55.7500)
_ROAD_B = (37.6190, 55.7510)


async def test_shot_geo_route_lab(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    await _goto(
        shot_desktop_page, f"{api_origin('geo')}/geo/route-lab", settle_ms=2000
    )
    await wait_geo_map_ready(shot_desktop_page, zoom=15.8)
    await click_geo_map_at(shot_desktop_page, _ROAD_A)
    await click_geo_map_at(shot_desktop_page, _ROAD_B)
    await wait_geo_map_ready(shot_desktop_page, zoom=15.8, sources={"pm-ov-route": 1})
    await expect(
        shot_desktop_page.locator(".map-metrics")
    ).to_be_visible(timeout=20_000)
    await save_shot(shot_desktop_page, "geo-route-lab")


# === RAG ===


async def test_shot_rag_namespaces(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    await _goto(shot_desktop_page, f"{api_origin('rag')}/rag/", settle_ms=3000)
    await save_shot(shot_desktop_page, "rag-namespaces")


async def test_shot_rag_search(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    await _goto(
        shot_desktop_page, f"{api_origin('rag')}/rag/search", settle_ms=3000
    )
    ns_input = shot_desktop_page.locator(
        "platform-field input.field-pill-enum-input"
    ).first
    await ns_input.click()
    await shot_desktop_page.locator(
        ".enum-option", has_text="default"
    ).first.click()
    query = shot_desktop_page.locator(
        "platform-field.query-field input.field-pill-input"
    )
    await query.fill("витрина")
    await shot_desktop_page.locator(".search-btn").click()
    await expect(
        shot_desktop_page.locator(".result-card").first
    ).to_be_visible(timeout=30_000)
    await shot_desktop_page.wait_for_timeout(1000)
    await save_shot(shot_desktop_page, "rag-search")


# === Flows ===


async def test_shot_flows_editor(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    flow_id = str(marketing_seeded["flows"]["flow_id"])
    await _goto(
        shot_desktop_page,
        f"{api_origin('flows')}/flows/{flow_id}/editor",
        settle_ms=5000,
    )
    await expect(
        shot_desktop_page.locator("flow-editor-page")
    ).to_be_visible(timeout=30_000)
    await save_shot(shot_desktop_page, "flows-editor")


async def test_shot_flows_home(
    shot_desktop_page: Page, marketing_seeded, save_shot
) -> None:
    await _goto(shot_desktop_page, f"{api_origin('flows')}/flows/", settle_ms=3000)
    await save_shot(shot_desktop_page, "flows-home")


# === Лендинг (public, apex) ===


async def test_shot_land_hero(shot_anonymous_page: Page, save_shot) -> None:
    await _goto(shot_anonymous_page, _ui("frontend").apex_origin, settle_ms=3000)
    await dismiss_cookie_banner(shot_anonymous_page)
    await save_shot(shot_anonymous_page, "land-hero")


async def test_shot_land_abilities(shot_anonymous_page: Page, save_shot) -> None:
    await _goto(shot_anonymous_page, _ui("frontend").apex_origin, settle_ms=3000)
    await dismiss_cookie_banner(shot_anonymous_page)
    el = shot_anonymous_page.locator("landing-abilities")
    if await el.count():
        await el.scroll_into_view_if_needed()
        await shot_anonymous_page.wait_for_timeout(1500)
    await save_shot(shot_anonymous_page, "land-abilities")


async def test_shot_land_product_shop(shot_anonymous_page: Page, save_shot) -> None:
    await _goto(
        shot_anonymous_page,
        f"{_ui('frontend').apex_origin}/products/shop",
        settle_ms=3000,
    )
    await dismiss_cookie_banner(shot_anonymous_page)
    await save_shot(shot_anonymous_page, "land-product-shop")
