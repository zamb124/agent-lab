"""Фикстуры сервиса shop (shared; не импортировать tests.shop.conftest как pytest_plugins).

Тесты идут по продовому пути: реальный Postgres (platform_shop), настоящий
AuthMiddleware, настоящий Redis (снапшоты витрин). Подмен нет.

HTTP: `shop_client` (владелец в `system`), `shop_client_company2` (чужая
компания), `shop_public_client` (без авторизации — анонимная витрина).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi import FastAPI
from httpx2 import URL, ASGITransport, AsyncClient, Response
from httpx2._client import USE_CLIENT_DEFAULT, UseClientDefault
from httpx2._types import (
    AuthTypes,
    CookieTypes,
    HeaderTypes,
    QueryParamTypes,
    RequestContent,
    RequestData,
    RequestExtensions,
    RequestFiles,
    TimeoutTypes,
)

from apps.shop.di import ShopDi
from core.di import require_di
from core.types import JsonObject, parse_json_object

API_PREFIX = "/shop/api/v1"
PUBLIC_PREFIX = f"{API_PREFIX}/public"
CUSTOMER_AUTH_PREFIX = f"{PUBLIC_PREFIX}/customer-auth"


async def auth_customer(
    client: AsyncClient,
    slug: str | None = None,
    phone: str | None = None,
    *,
    company_id: str | None = None,
) -> JsonObject:
    """Эмуляторный customer-auth: start → method=emulator → verify → cookie.

    `customer_token` остаётся в cookie jar клиента — последующие заказы
    проходят `require_customer` уже авторизованным покупателем.
    Номер генерируется уникальным: rate limit считает start по телефону.
    `company_id` можно передать напрямую — для витрин без публичного снапшота.
    """
    if phone is None:
        import secrets as _secrets

        phone = f"+7999{_secrets.randbelow(10**7):07d}"
    if company_id is None:
        assert slug is not None, "slug or company_id required"
        snap_resp = await client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert snap_resp.status_code == 200, snap_resp.text
        raw_company_id = parse_json_object(snap_resp.text, "storefront")["company_id"]
        assert isinstance(raw_company_id, str)
        company_id = raw_company_id
    resp = await client.post(
        f"{CUSTOMER_AUTH_PREFIX}/start", json={"company_id": company_id, "phone": phone}
    )
    assert resp.status_code == 200, resp.text
    raw_challenge_id = parse_json_object(resp.text, "auth start")["challenge_id"]
    assert isinstance(raw_challenge_id, str)
    challenge_id = raw_challenge_id
    resp = await client.post(
        f"{CUSTOMER_AUTH_PREFIX}/method",
        json={
            "challenge_id": challenge_id,
            "company_id": company_id,
            "method": "emulator",
        },
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{CUSTOMER_AUTH_PREFIX}/verify",
        json={
            "challenge_id": challenge_id,
            "company_id": company_id,
            "direct": {
                "kind": "contact_share",
                "provider": "emulator",
                "contact_phone": phone,
            },
        },
    )
    assert resp.status_code == 200, resp.text
    customer = parse_json_object(resp.text, "customer verify")["customer"]
    assert isinstance(customer, dict)
    return customer
_PLATFORM_ASGI_BASE_URL = "http://linnex.io"
_PLATFORM_ASGI_HOST_HEADERS = {"Host": "linnex.io"}


@pytest_asyncio.fixture
async def shop_app() -> FastAPI:
    """ASGI-приложение сервиса."""
    from apps.shop.main import app

    return app


@pytest_asyncio.fixture
async def shop_di(
    shop_app: FastAPI, setup_database_before_tests: None
) -> AsyncIterator[ShopDi]:
    _ = setup_database_before_tests
    async with shop_app.router.lifespan_context(shop_app):
        yield require_di(shop_app, ShopDi)


@pytest_asyncio.fixture
async def shop_client(
    shop_app: FastAPI, shop_di, auth_headers_system: dict[str, str]
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
    shop_app: FastAPI, shop_di, auth_headers_company2: dict[str, str]
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
async def shop_public_client(
    shop_app: FastAPI, shop_di, unique_id: str
) -> AsyncIterator[AsyncClient]:
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
        original_post = client.post

        async def post_with_customer_auth(
            url: URL | str,
            *,
            content: RequestContent | None = None,
            data: RequestData | None = None,
            files: RequestFiles | None = None,
            json: object = None,
            params: QueryParamTypes | None = None,
            headers: HeaderTypes | None = None,
            cookies: CookieTypes | None = None,
            auth: AuthTypes | UseClientDefault = USE_CLIENT_DEFAULT,
            follow_redirects: bool | UseClientDefault = USE_CLIENT_DEFAULT,
            timeout: TimeoutTypes | UseClientDefault = USE_CLIENT_DEFAULT,
            extensions: RequestExtensions | None = None,
        ) -> Response:
            # Заказ требует customer-сессии (customers.mdc): до первого заказа
            # тест проходит эмуляторную авторизацию по slug из URL.
            if (
                "/storefront/" in str(url)
                and str(url).endswith("/orders")
                and client.cookies.get("customer_token") is None
            ):
                slug = str(url).split("/storefront/")[1].split("/")[0]
                _ = await auth_customer(client, slug)
            return await original_post(
                url,
                content=content,
                data=data,
                files=files,
                json=json,
                params=params,
                headers=headers,
                cookies=cookies,
                auth=auth,
                follow_redirects=follow_redirects,
                timeout=timeout,
                extensions=extensions,
            )

        client.post = post_with_customer_auth
        yield client
