"""E2E customer-auth: start → emulator → verify → cookie → заказ → me/logout.

Реальные Postgres/Redis тестового стенда; эмулятор провайдера
(`emulator_enabled`) закрывает direct-поток без внешних сервисов.
"""

from __future__ import annotations

from httpx2 import AsyncClient

from core.types import JsonObject, parse_json_object
from tests.fixtures.shop import CUSTOMER_AUTH_PREFIX, PUBLIC_PREFIX, auth_customer

_SHOPS = "/shop/api/v1/shops"


def _id(obj: JsonObject, key: str) -> str:
    value = obj[key]
    assert isinstance(value, str)
    return value


def _obj_list(obj: JsonObject, key: str) -> list[JsonObject]:
    items = obj[key]
    assert isinstance(items, list)
    return [item for item in items if isinstance(item, dict)]


async def _shop_with_product(client: AsyncClient, slug: str) -> JsonObject:
    resp = await client.post(
        f"{_SHOPS}",
        json={"slug": slug, "name": "Тест", "lat": 55.7512, "lng": 37.6184},
    )
    assert resp.status_code == 200, resp.text
    shop = parse_json_object(resp.text, "shop")
    shop_id = _id(shop, "shop_id")
    resp = await client.post(f"{_SHOPS}/{shop_id}/publish")
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{_SHOPS}/{shop_id}/products",
        json={"name": "Борщ", "price_minor": 30000},
    )
    assert resp.status_code == 200, resp.text
    shop["product_id"] = _id(
        parse_json_object(resp.text, "product"), "shop_product_id"
    )
    return shop


class TestCustomerAuth:
    async def test_emulator_flow_and_order(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"cua-{unique_id[:8]}"
        shop = await _shop_with_product(shop_client, slug)

        # start: методы включают эмулятор; challenge живёт в Redis.
        # Номер уникальный: rate limit считает start по телефону на час.
        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert resp.status_code == 200, resp.text
        snap = parse_json_object(resp.text, "storefront")
        company_id = _id(snap, "company_id")
        resp = await shop_public_client.post(
            f"{CUSTOMER_AUTH_PREFIX}/start",
            json={"company_id": company_id, "phone": f"+7998{int(unique_id[:7], 16) % 10**7:07d}"},
        )
        assert resp.status_code == 200, resp.text
        start = parse_json_object(resp.text, "start")
        assert any(
            m["kind"] == "emulator" for m in _obj_list(start, "methods")
        )

        customer = await auth_customer(shop_public_client, slug)
        assert str(customer["phone_e164"]).startswith("+7999")

        # me читает сессию из customer_token cookie.
        resp = await shop_public_client.get(f"{CUSTOMER_AUTH_PREFIX}/me")
        assert resp.status_code == 200, resp.text
        me = parse_json_object(resp.text, "me")
        assert me["customer_id"] == customer["customer_id"]

        # Заказ проходит с верифицированным номером сессии, не из формы.
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json={
                "items": [{"product_id": shop["product_id"], "qty": 1}],
                "customer_name": "Пётр",
                "delivery_type": "pickup",
            },
        )
        assert resp.status_code == 200, resp.text
        resp = await shop_client.get(f"{_SHOPS}/{_id(shop, 'shop_id')}/orders")
        assert resp.status_code == 200, resp.text
        orders = parse_json_object(resp.text, "orders")
        order_items = _obj_list(orders, "items")
        assert order_items[0]["customer_id"] == customer["customer_id"]
        assert order_items[0]["customer_phone"] == customer["phone_e164"]

        resp = await shop_public_client.post(f"{CUSTOMER_AUTH_PREFIX}/logout")
        assert resp.status_code == 200, resp.text
        resp = await shop_public_client.get(f"{CUSTOMER_AUTH_PREFIX}/me")
        assert resp.status_code == 401

    async def test_order_requires_customer_session(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"cur-{unique_id[:8]}"
        shop = await _shop_with_product(shop_client, slug)
        # Обход авто-авторизации фикстуры: без cookie заказ отклонён.
        resp = await shop_public_client.request(
            "POST",
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json={
                "items": [{"product_id": shop["product_id"], "qty": 1}],
                "customer_name": "Пётр",
                "delivery_type": "pickup",
            },
        )
        assert resp.status_code == 401, resp.text

    async def test_scope_mismatch_rejected(
        self,
        shop_client: AsyncClient,
        shop_client_company2: AsyncClient,
        shop_public_client: AsyncClient,
        unique_id: str,
    ) -> None:
        slug_a = f"csca-{unique_id[:8]}"
        slug_b = f"cscb-{unique_id[:8]}"
        # Витрина B живёт в чужой компании: scope сессии привязан к company_id.
        shop_b = await _shop_with_product(shop_client_company2, slug_b)
        _ = await _shop_with_product(shop_client, slug_a)
        # Сессия выдана для компании A — заказ в витрине компании B отклоняется.
        _ = await auth_customer(shop_public_client, slug_a)
        resp = await shop_public_client.request(
            "POST",
            f"{PUBLIC_PREFIX}/storefront/{slug_b}/orders",
            json={
                "items": [{"product_id": shop_b["product_id"], "qty": 1}],
                "customer_name": "Пётр",
                "delivery_type": "pickup",
            },
        )
        assert resp.status_code in (403, 409), resp.text
        assert resp.json()["error_code"] == "forbidden_scope"

    async def test_invalid_phone_rejected(
        self, shop_public_client: AsyncClient
    ) -> None:
        resp = await shop_public_client.post(
            f"{CUSTOMER_AUTH_PREFIX}/start",
            json={"company_id": "system", "phone": "123"},
        )
        assert resp.status_code == 400, resp.text

