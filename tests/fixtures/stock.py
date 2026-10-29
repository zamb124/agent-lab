"""Фикстуры сервиса stock (shared; не импортировать tests.stock.conftest как pytest_plugins).

Тесты идут по продовому пути: реальный Postgres (platform_stock), настоящий
AuthMiddleware, настоящий OpenFGA (`ensure_warehouse_defaults` пишет tuples).
Подмен и заглушек здесь нет.

HTTP: `stock_client` (владелец в `system`), `stock_client_company2` (чужая компания).
Домен: `stock_di`, `stock_init` (компания `system` инициализирована).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx2 import ASGITransport, AsyncClient

from apps.stock.di import StockDi
from apps.stock.models import StockLocationUsage
from core.di import require_di

API_PREFIX = "/stock/api/v1"
_PLATFORM_ASGI_BASE_URL = "http://humanitec.ru"
_PLATFORM_ASGI_HOST_HEADERS = {"Host": "humanitec.ru"}


@pytest_asyncio.fixture
async def stock_app():
    """ASGI-приложение сервиса."""
    from apps.stock.main import app

    return app


@pytest_asyncio.fixture
async def stock_di(stock_app, setup_database_before_tests: None) -> AsyncIterator[StockDi]:
    _ = setup_database_before_tests
    async with stock_app.router.lifespan_context(stock_app):
        yield require_di(stock_app, StockDi)


@pytest_asyncio.fixture
async def stock_init(stock_di) -> StockDi:
    """`init_company_stock` для `system` — виртуальные локации и базовые ЕИ."""
    await stock_di.company_init_service.init_company_stock(company_id="system")
    return stock_di


@pytest_asyncio.fixture
async def stock_client(
    stock_app, stock_di, auth_headers_system
) -> AsyncIterator[AsyncClient]:
    """HTTP клиент для Stock API (ASGI transport, владелец system)."""
    _ = stock_di
    async with AsyncClient(
        transport=ASGITransport(app=stock_app),
        base_url=_PLATFORM_ASGI_BASE_URL,
        headers={**_PLATFORM_ASGI_HOST_HEADERS, **auth_headers_system},
    ) as client:
        yield client


@pytest_asyncio.fixture
async def stock_client_company2(
    stock_app, stock_di, auth_headers_company2
) -> AsyncIterator[AsyncClient]:
    """Пользователь другой компании: данные `system` ему недоступны."""
    _ = stock_di
    async with AsyncClient(
        transport=ASGITransport(app=stock_app),
        base_url=_PLATFORM_ASGI_BASE_URL,
        headers={**_PLATFORM_ASGI_HOST_HEADERS, **auth_headers_company2},
    ) as client:
        yield client


def supplier_location_id(company_id: str) -> str:
    return f"{company_id}:{StockLocationUsage.SUPPLIER.value}"


def customer_location_id(company_id: str) -> str:
    return f"{company_id}:{StockLocationUsage.CUSTOMER.value}"


__all__ = [
    "API_PREFIX",
    "customer_location_id",
    "supplier_location_id",
]
