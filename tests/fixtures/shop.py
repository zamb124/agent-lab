"""Фикстуры сервиса shop (shared; не импортировать tests.shop.conftest как pytest_plugins).

Тесты идут по продовому пути: реальный Postgres (platform_shop), настоящий
AuthMiddleware, настоящий Redis (снапшоты витрин). Подмен нет.

HTTP: `shop_client` (владелец в `system`), `shop_client_company2` (чужая
компания), `shop_public_client` (без авторизации — анонимная витрина).

Хелперы `make_*` собирают каталог и меню через REST-зеркала команд: блюдо
каталога попадает на витрину и в заказ только позицией активного меню.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio
from httpx2 import ASGITransport, AsyncClient

from apps.shop.di import ShopDi
from core.di import require_di

API_PREFIX = "/shop/api/v1"
PUBLIC_PREFIX = f"{API_PREFIX}/public"
SHOPS_PREFIX = f"{API_PREFIX}/shops"


async def make_shop(client: AsyncClient, slug: str, **overrides: Any) -> dict[str, Any]:
    """Черновик заведения; ``overrides`` перекрывают name/kind и поля создания."""
    payload = {"slug": slug, "name": f"Shop {slug}", "kind": "restaurant", **overrides}
    resp = await client.post(SHOPS_PREFIX, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def publish_shop(client: AsyncClient, shop_id: str) -> dict[str, Any]:
    resp = await client.post(f"{SHOPS_PREFIX}/{shop_id}/publish")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def make_product(
    client: AsyncClient, shop_id: str, name: str, price_minor: int, **overrides: Any
) -> dict[str, Any]:
    """Блюдо каталога заведения (вне меню на витрине не видно)."""
    resp = await client.post(
        f"{SHOPS_PREFIX}/{shop_id}/products",
        json={"name": name, "price_minor": price_minor, **overrides},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def add_menu_item(
    client: AsyncClient,
    shop_id: str,
    shop_menu_id: str,
    shop_menu_section_id: str,
    shop_product_id: str,
    **overrides: Any,
) -> dict[str, Any]:
    """Позиция меню в разделе; ``overrides`` — price_minor_override/is_available."""
    resp = await client.post(
        f"{SHOPS_PREFIX}/{shop_id}/menus/{shop_menu_id}/items",
        json={
            "shop_menu_section_id": shop_menu_section_id,
            "shop_product_id": shop_product_id,
            **overrides,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def make_active_menu_item(
    client: AsyncClient,
    shop_id: str,
    shop_product_id: str,
    *,
    menu_name: str = "Меню",
    section_name: str = "Раздел",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Меню → раздел → позиция блюда → статус active; тела меню, раздела, позиции."""
    resp = await client.post(f"{SHOPS_PREFIX}/{shop_id}/menus", json={"name": menu_name})
    assert resp.status_code == 200, resp.text
    menu_id = resp.json()["shop_menu_id"]
    resp = await client.post(
        f"{SHOPS_PREFIX}/{shop_id}/menus/{menu_id}/sections", json={"name": section_name}
    )
    assert resp.status_code == 200, resp.text
    section = resp.json()
    item = await add_menu_item(
        client, shop_id, menu_id, section["shop_menu_section_id"], shop_product_id
    )
    resp = await client.post(
        f"{SHOPS_PREFIX}/{shop_id}/menus/{menu_id}/status", json={"status": "active"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json(), section, item


async def shop_with_sellable_item(
    client: AsyncClient,
    slug: str,
    *,
    product_name: str = "Маргарита",
    price_minor: int = 50000,
    delivery_fee: int = 0,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Опубликованное заведение с одним блюдом в активном меню: shop, product, item."""
    shop = await make_shop(client, slug)
    if delivery_fee:
        resp = await client.patch(
            f"{SHOPS_PREFIX}/{shop['shop_id']}", json={"delivery_fee_minor": delivery_fee}
        )
        assert resp.status_code == 200, resp.text
    shop = await publish_shop(client, shop["shop_id"])
    product = await make_product(client, shop["shop_id"], product_name, price_minor)
    _, _, item = await make_active_menu_item(client, shop["shop_id"], product["shop_product_id"])
    return shop, product, item
_PLATFORM_ASGI_BASE_URL = "http://linnex.io"
_PLATFORM_ASGI_HOST_HEADERS = {"Host": "linnex.io"}


@pytest_asyncio.fixture
async def shop_app():
    """ASGI-приложение сервиса."""
    from apps.shop.main import app

    return app


@pytest_asyncio.fixture
async def shop_di(shop_app, setup_database_before_tests: None) -> AsyncIterator[ShopDi]:
    _ = setup_database_before_tests
    async with shop_app.router.lifespan_context(shop_app):
        yield require_di(shop_app, ShopDi)


@pytest_asyncio.fixture
async def shop_client(
    shop_app, shop_di, auth_headers_system
) -> AsyncIterator[AsyncClient]:
    """HTTP клиент для Shop API (ASGI transport, владелец system)."""
    _ = shop_di
    async with AsyncClient(
        transport=ASGITransport(app=shop_app),
        base_url=_PLATFORM_ASGI_BASE_URL,
        headers={**_PLATFORM_ASGI_HOST_HEADERS, **auth_headers_system},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def shop_client_company2(
    shop_app, shop_di, auth_headers_company2
) -> AsyncIterator[AsyncClient]:
    """Пользователь другой компании: данные `system` ему недоступны."""
    _ = shop_di
    async with AsyncClient(
        transport=ASGITransport(app=shop_app),
        base_url=_PLATFORM_ASGI_BASE_URL,
        headers={**_PLATFORM_ASGI_HOST_HEADERS, **auth_headers_company2},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def shop_public_client(shop_app, shop_di, unique_id: str) -> AsyncIterator[AsyncClient]:
    """Анонимный клиент без Authorization: публичная витрина и агрегатор.

    Уникальный ``X-Forwarded-For`` на тест — IP-лимит заказов считается
    по заголовку, иначе весь прогон делит один счётчик на 127.0.0.1.
    """
    _ = shop_di
    n = int(unique_id[:8], 16)
    ip = f"10.{(n >> 8) % 254 + 1}.{n % 254 + 1}.7"
    async with AsyncClient(
        transport=ASGITransport(app=shop_app),
        base_url=_PLATFORM_ASGI_BASE_URL,
        headers={**_PLATFORM_ASGI_HOST_HEADERS, "X-Forwarded-For": ip},
    ) as client:
        yield client
