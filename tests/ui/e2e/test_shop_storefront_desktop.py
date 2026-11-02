"""Витрина Shop в браузере: десктопный лейаут, slug-хост, drawer корзины.

Продовый путь end-to-end: реальный Granian :9027 и shop_worker стека,
Chromium рендерит тот же HTML/CSS, что покупатель на <slug>.linnex.io
(в тестовом стеке суффикс — lvh.me, публичный wildcard DNS на 127.0.0.1).
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

import httpx2
import pytest
import pytest_asyncio
from playwright.async_api import Page, ViewportSize, expect

from core.types import JsonObject, require_json_object
from tests.ui.e2e_worker import ui_e2e_scope_headers
from tests.ui.harness import AppUI

_SHOP_API = "/shop/api/v1"
_SHOP_PUBLIC = f"{_SHOP_API}/public"
_SHOP_ORIGIN = "http://127.0.0.1:9027"
_DESKTOP_VIEWPORT = ViewportSize(width=1440, height=900)
_MOBILE_VIEWPORT = ViewportSize(width=390, height=844)
_SNAPSHOT_WAIT_SECONDS = 45.0


async def _post(
    client: httpx2.AsyncClient,
    headers: dict[str, str],
    path: str,
    json: JsonObject,
) -> JsonObject:
    resp = await client.post(f"{_SHOP_API}{path}", json=json, headers=headers)
    assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text}"
    body: object = resp.json()
    return require_json_object(body, f"POST {path}")


@dataclass(frozen=True)
class Storefront:
    slug: str
    shop_id: str
    plain_product_id: str
    plain_product_name: str


async def _wait_snapshot_products(
    client: httpx2.AsyncClient, slug: str, expected: int
) -> None:
    """Снапшот витрины догоняет каталог: инвалидация sync, ребилд — shop_worker."""
    deadline = asyncio.get_running_loop().time() + _SNAPSHOT_WAIT_SECONDS
    status = 0
    while True:
        resp = await client.get(f"{_SHOP_PUBLIC}/storefront/{slug}")
        status = resp.status_code
        if status == 200:
            body: object = resp.json()
            products = require_json_object(body, "snapshot")["products"]
            if isinstance(products, list) and len(products) == expected:
                return
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"снапшот {slug} не собран: HTTP {status}")
        await asyncio.sleep(0.5)


async def _create_storefront(
    client: httpx2.AsyncClient,
    headers: dict[str, str],
    slug: str,
    *,
    categories: tuple[str, ...],
    products_per_category: int,
    shop_patch: JsonObject | None = None,
) -> Storefront:
    shop = await _post(
        client,
        headers,
        "/shops",
        {"slug": slug, "name": f"E2E Витрина {slug}", "kind": "cafe"},
    )
    shop_id = str(shop["shop_id"])
    if shop_patch is not None:
        resp = await client.patch(
            f"{_SHOP_API}/shops/{shop_id}", json=shop_patch, headers=headers
        )
        assert resp.status_code == 200, f"shop patch: {resp.status_code} {resp.text}"
    plain_product_id = ""
    plain_product_name = ""
    products_total = 0
    for index, name in enumerate(categories):
        category = await _post(
            client, headers, f"/shops/{shop_id}/categories", {"name": name}
        )
        for item in range(products_per_category):
            product = await _post(
                client,
                headers,
                f"/shops/{shop_id}/products",
                {
                    "category_id": category["shop_category_id"],
                    "name": f"{name} блюдо {item + 1}",
                    "price_minor": 25000 + item * 1000,
                    "description": f"Позиция {item + 1} раздела {name}",
                },
            )
            products_total += 1
            if index == 0 and item == 0:
                plain_product_id = str(product["shop_product_id"])
                plain_product_name = str(product["name"])
    if len(categories) > 1:
        group = await _post(
            client,
            headers,
            f"/shops/{shop_id}/modifier-groups",
            {
                "name": "Размер",
                "selection_mode": "single",
                "min_selected": 1,
                "price_mode": "absolute",
            },
        )
        _ = await _post(
            client,
            headers,
            f"/shops/{shop_id}/modifier-groups/{group['shop_modifier_group_id']}/options",
            {"name": "Большой", "price_minor": 40000, "is_default": True},
        )
        modal = await _post(
            client,
            headers,
            f"/shops/{shop_id}/products",
            {
                "category_id": None,
                "name": f"Комбо {slug}",
                "price_minor": 50000,
            },
        )
        _ = await _post(
            client,
            headers,
            f"/shops/{shop_id}/products/{modal['shop_product_id']}/modifier-groups/{group['shop_modifier_group_id']}",
            {},
        )
        products_total += 1
    _ = await _post(client, headers, f"/shops/{shop_id}/publish", {})
    await _wait_snapshot_products(client, slug, products_total)
    return Storefront(
        slug=slug,
        shop_id=shop_id,
        plain_product_id=plain_product_id,
        plain_product_name=plain_product_name,
    )


@pytest_asyncio.fixture
async def storefront(
    shop_client_http: httpx2.AsyncClient,
    shop_worker: None,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> Storefront:
    """Витрина с двумя категориями, товарами и модификатором — через реальный REST."""
    _ = shop_worker
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    slug = f"e2ed-{unique_id[:8]}"
    return await _create_storefront(
        shop_client_http,
        headers,
        slug,
        categories=("Горячее", "Десерты"),
        products_per_category=3,
    )


@pytest_asyncio.fixture
async def themed_storefront(
    shop_client_http: httpx2.AsyncClient,
    shop_worker: None,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> Storefront:
    """Витрина с контактами и обоими способами выдачи — meta-иконки и seg видны."""
    _ = shop_worker
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    slug = f"e2et-{unique_id[:8]}"
    return await _create_storefront(
        shop_client_http,
        headers,
        slug,
        categories=("Горячее", "Десерты"),
        products_per_category=3,
        shop_patch={
            "city": "Москва",
            "address": "Тверская, 1",
            "phone": "+7 495 000-00-00",
            "delivery_enabled": True,
            "pickup_enabled": True,
        },
    )


@pytest_asyncio.fixture
async def flat_storefront(
    shop_client_http: httpx2.AsyncClient,
    shop_worker: None,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> Storefront:
    """Витрина с одной категорией — flat-режим без сайдбара."""
    _ = shop_worker
    headers = {**auth_headers_system, **ui_e2e_scope_headers()}
    slug = f"e2ef-{unique_id[:8]}"
    return await _create_storefront(
        shop_client_http,
        headers,
        slug,
        categories=("Меню",),
        products_per_category=6,
    )


def _page_url(slug: str) -> str:
    return f"{_SHOP_ORIGIN}{_SHOP_PUBLIC}/s/{slug}"


async def _css(page: Page, selector: str, prop: str) -> str:
    value: object = await page.evaluate(
        "([s, p]) => getComputedStyle(document.querySelector(s))[p]",
        [selector, prop],
    )
    if not isinstance(value, str):
        raise AssertionError(f"{selector}.{prop}: ожидали строку, got {value!r}")
    return value


async def _eval_int(page: Page, expression: str) -> int:
    value: object = await page.evaluate(expression)
    if not isinstance(value, int) or isinstance(value, bool):
        raise AssertionError(f"ожидали int, got {value!r}")
    return value


async def _eval_bool(page: Page, expression: str) -> bool:
    value: object = await page.evaluate(expression)
    if not isinstance(value, bool):
        raise AssertionError(f"ожидали bool, got {value!r}")
    return value


async def _rect(page: Page, selector: str) -> dict[str, float]:
    raw: object = await page.evaluate(
        "s => { const r = document.querySelector(s).getBoundingClientRect(); return {left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height}; }",
        selector,
    )
    if not isinstance(raw, dict):
        raise AssertionError(f"{selector}: ожидали rect, got {raw!r}")
    rect: dict[str, float] = {}
    for key in ("left", "right", "top", "bottom", "width", "height"):
        value: object = raw[key]
        if not isinstance(value, (int, float)):
            raise AssertionError(f"{selector}.{key}: ожидали число, got {value!r}")
        rect[key] = float(value)
    return rect


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_desktop_layout_sidebar_and_columns(
    page: Page, storefront: Storefront
) -> None:
    """1440px: wrap 1240, full-bleed hero, левая колонка категорий и 2 колонки блюд."""
    await page.set_viewport_size(_DESKTOP_VIEWPORT)
    _ = await page.goto(_page_url(storefront.slug), wait_until="load")
    await expect(page.locator(".tabs button").first).to_be_visible()
    wrap = await _rect(page, ".wrap")
    assert 1100 < wrap["width"] <= 1240
    hero = await _rect(page, ".hero")
    assert hero["width"] >= 1420
    assert await _css(page, ".tabs", "flexDirection") == "column"
    assert await _css(page, ".tabs", "position") == "sticky"
    tabs = await _rect(page, ".tabs")
    body = await _rect(page, "#mbody")
    assert body["left"] > tabs["right"]
    columns = await _eval_int(
        page,
        "getComputedStyle(document.querySelector('.mchunk')).gridTemplateColumns.split(' ').filter(Boolean).length",
    )
    assert columns >= 2
    assert await _eval_bool(
        page, "document.getElementById('app').classList.contains('flat')"
    ) is False


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_desktop_grid_preset_light_theme(
    page: Page, storefront: Storefront
) -> None:
    """?tpreset=grid&tmode=light: auto-fill сетка >=3 колонок и светлая палитра."""
    await page.set_viewport_size(_DESKTOP_VIEWPORT)
    _ = await page.goto(
        f"{_page_url(storefront.slug)}?tpreset=grid&tmode=light", wait_until="load"
    )
    await expect(page.locator(".gcard").first).to_be_visible()
    columns = await _eval_int(
        page,
        "getComputedStyle(document.querySelector('.grid')).gridTemplateColumns.split(' ').filter(Boolean).length",
    )
    assert columns >= 3
    background = await _css(page, "body", "backgroundColor")
    assert background == "rgb(245, 244, 242)"


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_desktop_cart_drawer_and_product_modal(
    page: Page, storefront: Storefront
) -> None:
    """Корзина — правый drawer на всю высоту с прижатой кнопкой; товар — центр-модалка."""
    await page.set_viewport_size(_DESKTOP_VIEWPORT)
    _ = await page.goto(_page_url(storefront.slug), wait_until="load")
    await expect(page.locator(".item").first).to_be_visible()
    add = page.locator(f".item[data-pid='{storefront.plain_product_id}'] .add")
    await add.click()
    await expect(page.locator("#cart.show")).to_be_visible()
    cart = await _rect(page, "#cart")
    assert cart["right"] > _DESKTOP_VIEWPORT["width"] - 60
    await page.locator("#cart").click()
    await expect(page.locator("#sheet.show")).to_be_visible()
    panel = await _rect(page, "#sheet .panel")
    assert panel["right"] >= _DESKTOP_VIEWPORT["width"] - 40
    assert panel["height"] >= 850
    pay = await _rect(page, "#payBtn")
    assert pay["bottom"] >= panel["bottom"] - 60
    await page.keyboard.press("Escape")
    await expect(page.locator("#sheet.show")).to_be_hidden()
    await page.locator(".item").first.click()
    await expect(page.locator("#csheet.show")).to_be_visible()
    await expect(page.locator("#csheet .panel")).to_contain_text(
        storefront.plain_product_name
    )
    modal = await _rect(page, "#csheet .panel")
    expected_left = (_DESKTOP_VIEWPORT["width"] - modal["width"]) / 2
    assert abs(modal["left"] - expected_left) < 30
    expected_top = (_DESKTOP_VIEWPORT["height"] - modal["height"]) / 2
    assert abs(modal["top"] - expected_top) < 60


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_mobile_layout_regression(
    page: Page, storefront: Storefront
) -> None:
    """390px: мобильная колонка — горизонтальные табы, корзина по центру, sheet снизу."""
    await page.set_viewport_size(_MOBILE_VIEWPORT)
    _ = await page.goto(_page_url(storefront.slug), wait_until="load")
    await expect(page.locator(".tabs button").first).to_be_visible()
    wrap = await _rect(page, ".wrap")
    assert wrap["width"] <= 720
    assert await _css(page, ".tabs", "flexDirection") == "row"
    await page.locator(f".item[data-pid='{storefront.plain_product_id}'] .add").click()
    await expect(page.locator("#cart.show")).to_be_visible()
    cart = await _rect(page, "#cart")
    center = _MOBILE_VIEWPORT["width"] / 2
    assert abs((cart["left"] + cart["right"]) / 2 - center) < 30
    await page.locator(".item").first.click()
    await expect(page.locator("#csheet.show")).to_be_visible()
    sheet = await _rect(page, "#csheet .panel")
    assert sheet["bottom"] >= _MOBILE_VIEWPORT["height"] - 10


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_single_category_flat_layout(
    page: Page, flat_storefront: Storefront
) -> None:
    """Одна категория на десктопе — flat: сайдбар скрыт, поиск без отступа."""
    await page.set_viewport_size(_DESKTOP_VIEWPORT)
    _ = await page.goto(_page_url(flat_storefront.slug), wait_until="load")
    await expect(page.locator(".item").first).to_be_visible()
    assert await _eval_bool(
        page, "document.getElementById('app').classList.contains('flat')"
    ) is True
    await expect(page.locator(".tabs")).to_be_hidden()
    assert await _css(page, "#msw", "marginLeft") == "0px"


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_slug_host_serves_desktop_storefront(
    shop_client_http: httpx2.AsyncClient,
    storefront: Storefront,
) -> None:
    """Host: <slug>.lvh.me — продовый ingress-путь: middleware → резолв → HTML витрины."""
    resp = await shop_client_http.get(
        "/", headers={"Host": f"{storefront.slug}.lvh.me"}
    )
    assert resp.status_code == 200, resp.text[:200]
    assert "text/html" in resp.headers["content-type"]
    assert storefront.slug in resp.text
    assert "@media(min-width:1024px)" in resp.text


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(90)
async def test_builder_web_preview_shows_desktop_layout(
    ui_page_system: Page, storefront: Storefront, shop_ui: AppUI
) -> None:
    """Конструктор витрины в web-режиме: scale-iframe показывает настоящий desktop.

    Регрессия, которую ловит тест: раньше внутренний viewport iframe
    оставался мобильным — «web»-превью рисовало узкую колонку 720px.
    """
    await ui_page_system.set_viewport_size({"width": 1600, "height": 900})
    _ = await ui_page_system.goto(
        f"{shop_ui.origin}/shop/{storefront.shop_id}/builder",
        wait_until="domcontentloaded",
    )
    await expect(ui_page_system.locator("shop-builder-page")).to_be_visible(
        timeout=30_000
    )
    devices = ui_page_system.locator("shop-builder-page .devices button")
    await expect(devices.nth(1)).to_be_visible(timeout=30_000)
    await devices.nth(1).click()
    frame = ui_page_system.locator("shop-builder-page iframe.desktop")
    await expect(frame).to_be_visible()
    src = await frame.get_attribute("src")
    assert src is not None
    assert "tpreset=" in src and "tmode=" in src
    tabs = ui_page_system.frame_locator("iframe.desktop").locator(".tabs")
    await expect(tabs).to_be_visible(timeout=30_000)
    await expect(tabs).to_have_css("flex-direction", "column", timeout=15_000)


def _rgb_channels(css_color: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"rgb\((\d+), (\d+), (\d+)\)", css_color)
    assert match is not None, f"ожидали rgb(), got {css_color!r}"
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_light_theme_readability(
    page: Page, themed_storefront: Storefront
) -> None:
    """Light: нейтральный фон, белый текст hero поверх вуали, тень у карточек."""
    await page.set_viewport_size(_DESKTOP_VIEWPORT)
    _ = await page.goto(
        f"{_page_url(themed_storefront.slug)}?tpreset=grid&tmode=light",
        wait_until="load",
    )
    await expect(page.locator(".gcard").first).to_be_visible()
    assert await _css(page, "body", "backgroundColor") == "rgb(245, 244, 242)"
    hero_title = _rgb_channels(await _css(page, ".hero h1", "color"))
    assert min(hero_title) >= 235
    assert await _css(page, ".gcard", "boxShadow") != "none"
    assert await _css(page, ".add", "color") == "rgb(255, 255, 255)"


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_amber_accent_uses_dark_on_accent(
    page: Page, themed_storefront: Storefront
) -> None:
    """#f2a33c: текст на accent-кнопке тёмный — иначе белый на янтарном нечитаем."""
    await page.set_viewport_size(_DESKTOP_VIEWPORT)
    _ = await page.goto(
        f"{_page_url(themed_storefront.slug)}?taccent=%23f2a33c", wait_until="load"
    )
    await expect(page.locator(".item").first).to_be_visible()
    assert await _css(page, ".add", "color") == "rgb(29, 26, 22)"


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_dark_accent_visible_as_sidebar_text(
    page: Page, themed_storefront: Storefront
) -> None:
    """#111827 в dark-теме: акцентный текст сайдбара осветлён до читаемого --afg."""
    await page.set_viewport_size(_DESKTOP_VIEWPORT)
    _ = await page.goto(
        f"{_page_url(themed_storefront.slug)}?taccent=%23111827", wait_until="load"
    )
    await expect(page.locator(".tabs button.on").first).to_be_visible()
    active = _rgb_channels(await _css(page, ".tabs button.on", "color"))
    assert min(active) > 100


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_meta_icons_render_as_svg(
    page: Page, themed_storefront: Storefront
) -> None:
    """Адрес/телефон/доставка/самовывоз — SVG-иконки; эмодзи в meta не осталось."""
    await page.set_viewport_size(_DESKTOP_VIEWPORT)
    _ = await page.goto(_page_url(themed_storefront.slug), wait_until="load")
    await expect(page.locator(".meta svg").first).to_be_visible()
    assert await page.locator(".meta svg").count() >= 4
    has_emoji = await _eval_bool(
        page,
        "/[\\u{1F300}-\\u{1FAFF}\\u{2600}-\\u{27BF}]/u.test(document.querySelector('.meta').textContent)",
    )
    assert has_emoji is False


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(60)
async def test_focus_ring_on_category_tab(
    page: Page, themed_storefront: Storefront
) -> None:
    """Клавиатурный фокус на категории: видимое кольцо --afg, а не отсутствие стиля."""
    await page.set_viewport_size(_DESKTOP_VIEWPORT)
    _ = await page.goto(_page_url(themed_storefront.slug), wait_until="load")
    tab = page.locator(".tabs button").first
    await expect(tab).to_be_visible()
    await tab.focus()
    await expect(tab).to_have_css("outline-style", "solid", timeout=5000)
    await expect(tab).to_have_css("outline-width", "2px", timeout=5000)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)
async def test_theme_screenshot_matrix(
    page: Page, themed_storefront: Storefront
) -> None:
    """Матрица приёмки: 3 пресета × 2 темы desktop + 2 mobile — скриншоты в artifacts."""
    out_dir = Path(__file__).resolve().parents[3] / "artifacts" / "shop-themes"
    out_dir.mkdir(parents=True, exist_ok=True)
    async def _settled() -> None:
        # Чанки дорисовываются IntersectionObserver'ом: ждём, пока очередь
        # опустеет (#msent удаляется), затем — конец fade у последнего чанка.
        await expect(page.locator("#msent")).to_have_count(0, timeout=5000)
        last = page.locator("#mbody .mchunk").last
        await expect(last).to_be_visible()
        await expect(last).to_have_css("opacity", "1", timeout=5000)

    await page.set_viewport_size(_DESKTOP_VIEWPORT)
    for preset in ("menu", "grid", "compact"):
        for mode in ("dark", "light"):
            _ = await page.goto(
                f"{_page_url(themed_storefront.slug)}?tpreset={preset}&tmode={mode}",
                wait_until="load",
            )
            await _settled()
            _ = await page.screenshot(path=str(out_dir / f"{preset}-{mode}.png"))
    await page.set_viewport_size(_MOBILE_VIEWPORT)
    for mode in ("dark", "light"):
        _ = await page.goto(
            f"{_page_url(themed_storefront.slug)}?tmode={mode}",
            wait_until="load",
        )
        await _settled()
        _ = await page.screenshot(path=str(out_dir / f"mobile-{mode}.png"))
