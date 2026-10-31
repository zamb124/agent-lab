"""Фикстуры сервиса shop (shared; не импортировать tests.shop.conftest как pytest_plugins).

Тесты идут по продовому пути: реальный Postgres (platform_shop), настоящий
AuthMiddleware, настоящий Redis (снапшоты витрин). Подмен нет.

HTTP: `shop_client` (владелец в `system`), `shop_client_company2` (чужая
компания), `shop_public_client` (без авторизации — анонимная витрина).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx2 import ASGITransport, AsyncClient

from apps.shop.di import ShopDi
from core.di import require_di

API_PREFIX = "/shop/api/v1"
PUBLIC_PREFIX = f"{API_PREFIX}/public"
_PLATFORM_ASGI_BASE_URL = "http://humanitec.ru"
_PLATFORM_ASGI_HOST_HEADERS = {"Host": "humanitec.ru"}


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
        base_url=_PLATFORM_ASGI_HOST_HEADERS,
        headers={**_PLATFORM_ASGI_HOST_HEADERS, **auth_headers_company2},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def shop_public_client(shop_app, shop_di) -> AsyncIterator[AsyncClient]:
    """Анонимный клиент без Authorization: публичная витрина и агрегатор."""
    _ = shop_di
    async with AsyncClient(
        transport=ASGITransport(app=shop_app),
        base_url=_PLATFORM_ASGI_BASE_URL,
        headers=_PLATFORM_ASGI_HOST_HEADERS,
    ) as client:
        yield client
