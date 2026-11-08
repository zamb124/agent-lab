"""Витринная лента в браузере: баннеры, полки, КБЖУ, «скоро вернётся», апсейл.

Продовый путь: реальный Granian :9027 + shop_worker собирает снапшот
с разрешёнными полками; Chromium рендерит feed-блок на phone/tablet/
desktop/embed. Скриншот-матрица — артефакты artifacts/shop-feed/.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import httpx2
import pytest
import pytest_asyncio
from playwright.async_api import Page, ViewportSize, expect

from core.types import JsonObject, JsonValue, require_json_object
from tests.ui.e2e_worker import ui_e2e_scope_headers

_SHOP_API = "/shop/api/v1"
_SHOP_PUBLIC = f"{_SHOP_API}/public"
_SHOP_ORIGIN = "http://127.0.0.1:9027"
_PHONE = ViewportSize(width=390, height=844)
_TABLET = ViewportSize(width=834, height=1112)
_DESKTOP = ViewportSize(width=1440, height=900)
_SNAPSHOT_WAIT_SECONDS = 45.0
_ARTIFACTS = Path(__file__).resolve().parents[3] / "artifacts" / "shop-feed"


async def _post(
    client: httpx2.AsyncClient,
    headers: dict[str, str],
    path: str,
    json: JsonObject,
) -> JsonObject:
    resp = await client.post(f"{_SHOP_API}{path}", json=json, headers=headers)
    assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text}"
    body = cast("JsonValue", resp.json())
    return require_json_object(body, f"POST {path}")


@dataclass(frozen=True)
class FeedStorefront:
    slug: str
    shop_id: str
    product_id: str
    product_name: str
    unavailable_id: str
    extra_id: str


async def _wait_snapshot_feed(
    client: httpx2.AsyncClient, slug: str, shelves: int, banners: int
) -> None:
    """Ждём снапшот с собранной лентой: ребилд идёт через shop_worker."""
    deadline = asyncio.get_running_loop().time() + _SNAPSHOT_WAIT_SECONDS
    while True:
        resp = await client.get(f"{_SHOP_PUBLIC}/storefront/{slug}")
        if resp.status_code == 200:
            body = require_json_object(cast("JsonValue", resp.json()), "snapshot")
            got_shelves = body.get("shelves")
            got_banners = body.get("banners")
            if (
                isinstance(got_shelves, list)
                and len(got_shelves) == shelves
                and isinstance(got_banners, list)
                and len(got_banners) == banners
            ):
                return
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"лента {slug} не собрана")
        await asyncio.sleep(0.5)


@pytest_asyncio.fixture
async def feed_storefront(
    shop_client_http: httpx2.AsyncClient,
    shop_worker: None,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> FeedStorefront:
    """Витрина с лентой: баннер, полки new/comeback/upsell, КБЖУ, «скоро»."""
    _ = shop_worker
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    slug = f"e2feed-{unique_id[:6]}"
    shop = await _post(
        shop_client_http,
        headers,
        "/shops",
        {"slug": slug, "name": f"Лента {slug}", "kind": "cafe", "lat": 55.7512, "lng": 37.6184},
    )
    shop_id = str(shop["shop_id"])
    resp = await shop_client_http.patch(
        f"{_SHOP_API}/shops/{shop_id}",
        json={"features": {"nutrition": True, "back_in_stock": True}},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    category = await _post(
        shop_client_http, headers, f"/shops/{shop_id}/categories", {"name": "Кофе"}
    )
    product = await _post(
        shop_client_http,
        headers,
        f"/shops/{shop_id}/products",
        {
            "category_id": category["shop_category_id"],
            "name": "Капучино",
            "price_minor": 25000,
            "description": "На овсяном молоке",
            "nutrition": {"kcal": 120.0, "protein_g": 4.0, "fat_g": 5.0, "carb_g": 14.0},
        },
    )
    product_id = str(product["shop_product_id"])
    extra = await _post(
        shop_client_http,
        headers,
        f"/shops/{shop_id}/products",
        {"name": "Сироп", "price_minor": 5000},
    )
    unavailable = await _post(
        shop_client_http,
        headers,
        f"/shops/{shop_id}/products",
        {"name": "Тирамису", "price_minor": 35000},
    )
    unavailable_id = str(unavailable["shop_product_id"])
    group = await _post(
        shop_client_http,
        headers,
        f"/shops/{shop_id}/modifier-groups",
        {"name": "Топпинг", "selection_mode": "multi"},
    )
    gid = str(group["shop_modifier_group_id"])
    _ = await _post(
        shop_client_http,
        headers,
        f"/shops/{shop_id}/modifier-groups/{gid}/options",
        {
            "name": "Корица",
            "price_minor": 3000,
            "nutrition_delta": {"kcal": 40.0, "carb_g": 8.0},
        },
    )
    _ = await _post(
        shop_client_http,
        headers,
        f"/shops/{shop_id}/products/{product_id}/modifier-groups/{gid}",
        {},
    )
    _ = await _post(
        shop_client_http,
        headers,
        f"/shops/{shop_id}/shelves",
        {"kind": "new", "title": "Новинки недели"},
    )
    _ = await _post(
        shop_client_http,
        headers,
        f"/shops/{shop_id}/shelves",
        {"kind": "comeback"},
    )
    _ = await _post(
        shop_client_http,
        headers,
        f"/shops/{shop_id}/shelves",
        {
            "kind": "upsell",
            "placement": "cart",
            "product_ids": [str(extra["shop_product_id"])],
        },
    )
    _ = await _post(
        shop_client_http,
        headers,
        f"/shops/{shop_id}/shelves",
        {"kind": "favorites"},
    )
    _ = await _post(
        shop_client_http,
        headers,
        f"/shops/{shop_id}/banners",
        {"title": "Дегустация", "subtitle": "Каждую пятницу", "link": f"product:{product_id}"},
    )
    resp = await shop_client_http.patch(
        f"{_SHOP_API}/shops/{shop_id}/products/{unavailable_id}",
        json={"is_available": False},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    _ = await _post(shop_client_http, headers, f"/shops/{shop_id}/publish", {})
    await _wait_snapshot_feed(shop_client_http, slug, shelves=4, banners=1)
    return FeedStorefront(
        slug=slug,
        shop_id=shop_id,
        product_id=product_id,
        product_name="Капучино",
        unavailable_id=unavailable_id,
        extra_id=str(extra["shop_product_id"]),
    )


def _url(sf: FeedStorefront, suffix: str = "") -> str:
    return f"{_SHOP_ORIGIN}{_SHOP_PUBLIC}/s/{sf.slug}{suffix}"


async def _shot(page: Page, name: str, slug: str) -> None:
    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    # Анимации fade-in (.sh/.item/.cchunk) при full_page-захвате перезапускаются
    # и ловятся на середине — для детерминированного снимка выключаем их.
    # Fixed-элементы (нав, корзина, шиты) в full_page дорисовываются на месте
    # вьюпорта — переводим в absolute, чтобы легли по краю документа.
    _ = await page.add_style_tag(
        content="*{animation:none!important;transition:none!important}"
        + "body{position:relative!important}"
        + ".acctnav,.cart,.sheet,.toast,.bdrop{position:absolute!important}"
    )
    _ = await page.screenshot(path=str(_ARTIFACTS / f"{slug}-{name}.png"), full_page=True)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_feed_renders_banners_shelves_comeback(
    page: Page, feed_storefront: FeedStorefront
) -> None:
    """Лента: сторис-баннер, полка «Новинки», «Скоро вернётся» с пилюлей «Скоро»."""
    await page.set_viewport_size(_PHONE)
    _ = await page.goto(_url(feed_storefront), wait_until="load")
    await expect(page.locator(".bnr")).to_have_count(1)
    await expect(page.locator(".bnr .btxt b")).to_have_text("Дегустация")
    await expect(page.locator(".sh h2").first).to_have_text("Новинки недели")
    await expect(page.locator(".shcard").first).to_be_visible()
    comeback = page.locator(".sh", has_text="Скоро вернётся")
    await expect(comeback.locator(".shcard")).to_have_count(1)
    await expect(comeback.locator(".soon")).to_have_text("Скоро")
    await expect(comeback.locator("[data-qty]")).to_have_count(0)
    await _shot(page, "phone-feed", feed_storefront.slug)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_banner_deeplink_opens_product(
    page: Page, feed_storefront: FeedStorefront
) -> None:
    """Тап по баннеру с `product:`-deeplink открывает карточку товара."""
    await page.set_viewport_size(_PHONE)
    _ = await page.goto(_url(feed_storefront), wait_until="load")
    await page.locator(".bnr").click()
    await expect(page.locator("#csheet.show")).to_be_visible()
    await expect(page.locator("#csheet .panel")).to_contain_text(
        feed_storefront.product_name
    )


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_nutrition_strip_recalculates_on_option(
    page: Page, feed_storefront: FeedStorefront
) -> None:
    """features.nutrition: полоса КБЖУ в карточке, выбор топпинга прибавляет 40 ккал."""
    await page.set_viewport_size(_PHONE)
    _ = await page.goto(_url(feed_storefront), wait_until="load")
    await page.locator(f".item[data-pid='{feed_storefront.product_id}']").click()
    await expect(page.locator("#csheet.show")).to_be_visible()
    nutri = page.locator("#csheet .nutri").first
    await expect(nutri).to_be_visible()
    await expect(nutri).to_contain_text("120")
    await page.locator("#csheet .opt", has_text="Корица").click()
    await expect(nutri).to_contain_text("160")
    cta = page.locator("#csheet button.big")
    cta_box = await cta.bounding_box()
    assert cta_box is not None
    # Шит — модалка: CTA целиком во вьюпорте, нижний нав под вуалью.
    assert cta_box["y"] + cta_box["height"] <= _PHONE["height"] - 1
    nav_box = await page.locator(".acctnav").bounding_box()
    assert nav_box is not None
    top_el = cast(
        "bool",
        await page.evaluate(
            "(y) => Boolean(document.elementFromPoint(195, y)?.closest('.sheet'))",
            nav_box["y"] + nav_box["height"] / 2,
        ),
    )
    assert top_el, "sheet must overlay the bottom nav"
    await _shot(page, "phone-nutrition", feed_storefront.slug)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_unavailable_product_shows_notify_button(
    page: Page, feed_storefront: FeedStorefront
) -> None:
    """back_in_stock: недоступная позиция — кнопка «Сообщить о появлении», без степпера."""
    await page.set_viewport_size(_PHONE)
    _ = await page.goto(_url(feed_storefront), wait_until="load")
    await page.locator(f".shcard[data-pid='{feed_storefront.unavailable_id}']").click()
    await expect(page.locator("#csheet.show")).to_be_visible()
    await expect(
        page.locator("#csheet .big", has_text="Сообщить о появлении")
    ).to_be_visible()
    await expect(page.locator("#csheet .crow")).to_have_count(0)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_cart_upsell_shelf(
    page: Page, feed_storefront: FeedStorefront
) -> None:
    """placement=cart: полка апсейла рисуется внутри шита корзины."""
    await page.set_viewport_size(_PHONE)
    _ = await page.goto(_url(feed_storefront), wait_until="load")
    await page.locator(f".item[data-pid='{feed_storefront.extra_id}'] .add").click()
    await expect(page.locator("#cart.show")).to_be_visible()
    await page.locator("#cart").click()
    await expect(page.locator("#sheet.show")).to_be_visible()
    panel = page.locator("#sheet .panel")
    await expect(panel.locator(".sh h2")).to_have_text("Добавить к заказу")
    await expect(panel.locator(".shcard")).to_have_count(1)
    await _shot(page, "phone-cart-upsell", feed_storefront.slug)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_favorites_heart_auth_and_shelf(
    page: Page, feed_storefront: FeedStorefront, unique_id: str
) -> None:
    """features.favorites: сердечко → авторизация эмулятором → полка «Избранное»."""
    await page.set_viewport_size(_PHONE)
    _ = await page.goto(_url(feed_storefront), wait_until="load")
    # Сердечки на карточках полки и каталога; полка «Избранное» пуста и скрыта.
    heart = page.locator(
        f".shcard[data-pid='{feed_storefront.product_id}'] .fav"
    ).first
    await expect(heart).to_be_visible()
    await expect(
        page.locator(f".item[data-pid='{feed_storefront.product_id}'] .fav")
    ).to_be_visible()
    fav_shelf = page.locator(".sh", has_text="Избранное")
    await expect(fav_shelf).to_have_count(0)

    # Тап по сердечку открывает customer-auth; эмулятор подтверждает сам.
    await heart.click()
    auth = page.locator("platform-customer-auth")
    await expect(auth.locator(".sheet")).to_be_visible()
    await auth.locator("input[type=tel]").fill(f"+7999{int(unique_id[:8], 16) % 10**7:07d}")
    await auth.locator("button.primary").click()
    await auth.locator("button.method", has_text="Эмулятор").click()
    await expect(heart).to_have_class("fav on", timeout=15_000)
    await expect(
        page.locator(f".item[data-pid='{feed_storefront.product_id}'] .fav")
    ).to_have_class("fav on")

    # Полка «Избранное» дорисовалась с позицией — без перезагрузки.
    await expect(fav_shelf.locator(".shcard")).to_have_count(1)
    await _shot(page, "phone-favorites", feed_storefront.slug)

    # Повторный тап снимает отметку — полка снова пустая.
    await heart.click()
    await expect(heart).not_to_have_class("fav on")
    await expect(fav_shelf.locator(".shcard")).to_have_count(0)

    # Залогиненный тап: сессия резолвится через /me до открытия шита —
    # auth-модалка не вспыхивает и не закрывается.
    await heart.click()
    await expect(auth.locator(".sheet")).not_to_be_visible()
    await expect(heart).to_have_class("fav on", timeout=10_000)
    await expect(auth.locator(".sheet")).not_to_be_visible()


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_feed_screenshot_matrix(
    page: Page, feed_storefront: FeedStorefront
) -> None:
    """Приёмочная матрица: phone 390 / tablet 834 / desktop 1440 / embed — артефакты."""
    for name, viewport in (
        ("phone", _PHONE),
        ("tablet", _TABLET),
        ("desktop", _DESKTOP),
    ):
        await page.set_viewport_size(viewport)
        _ = await page.goto(_url(feed_storefront), wait_until="load")
        await expect(page.locator(".bnr")).to_have_count(1)
        await expect(page.locator(".shcard").first).to_be_visible()
        await _shot(page, name, feed_storefront.slug)
    await page.set_viewport_size(_PHONE)
    _ = await page.goto(_url(feed_storefront, "?embed=1"), wait_until="load")
    await expect(page.locator(".bnr")).to_have_count(1)
    await _shot(page, "embed", feed_storefront.slug)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_hero_shelf_panel(
    page: Page,
    feed_storefront: FeedStorefront,
    shop_client_http: httpx2.AsyncClient,
    auth_headers_system: dict[str, str],
    shop_worker: None,
) -> None:
    """Hero-полка: рельс широких карточек, читаемый подзаголовок, у каждой
    карточки видны название, цена и кнопка. Регрессия клипа: класс ``hero``
    страничной шапки давал полке ``height:260px;overflow:hidden`` — низ
    карточек обрезался; теперь полка адресуется через ``data-layout``."""
    _ = shop_worker
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    _ = await _post(
        shop_client_http,
        headers,
        f"/shops/{feed_storefront.shop_id}/shelves",
        {
            "kind": "manual",
            "title": "Выбор бариста",
            "subtitle": "Капучино и десерты — авторская подборка",
            "layout": "hero",
            "product_ids": [
                feed_storefront.product_id,
                feed_storefront.extra_id,
                feed_storefront.unavailable_id,
            ],
        },
    )
    await _wait_snapshot_feed(shop_client_http, feed_storefront.slug, shelves=5, banners=1)
    for name, viewport in (
        ("phone", _PHONE),
        ("tablet", _TABLET),
        ("desktop", _DESKTOP),
    ):
        await page.set_viewport_size(viewport)
        _ = await page.goto(_url(feed_storefront), wait_until="load")
        shelf = page.locator('.sh[data-layout="hero"]')
        await expect(shelf).to_have_count(1)
        await expect(shelf.locator(".sh-h .sub")).to_have_text(
            "Капучино и десерты — авторская подборка"
        )
        cards = shelf.locator(".shcard")
        assert await cards.count() == 3
        # Панель врезана в контейнер — не прилипает к кромке вьюпорта.
        shelf_box = await shelf.bounding_box()
        assert shelf_box is not None
        assert shelf_box["x"] >= 12
        await expect(shelf.locator(".add").first).to_be_visible()
        for i in range(3):
            card = cards.nth(i)
            await card.scroll_into_view_if_needed()
            await expect(card.locator("h3")).to_be_visible()
            # Цена зашита в кнопку добавления; у недоступной позиции — отдельным .price.
            if i == 2:
                await expect(card.locator(".price")).to_be_visible()
            else:
                await expect(card.locator(".add")).to_contain_text("₽")
            # Низ ряда «цена + кнопка» обязан лежать внутри рамки полки —
            # иначе это старый клип height+overflow от шапки.
            row_box = await card.locator(".row").bounding_box()
            shelf_box = await shelf.bounding_box()
            assert row_box is not None and shelf_box is not None
            assert row_box["y"] + row_box["height"] <= (
                shelf_box["y"] + shelf_box["height"] + 1
            )
        await _shot(page, f"hero-{name}", feed_storefront.slug)
