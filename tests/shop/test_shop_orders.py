"""Заказы shop: приём с витрины, идемпотентность, матрица статусов."""

from __future__ import annotations

from typing import Any

from httpx2 import AsyncClient

from tests.fixtures.shop import (
    API_PREFIX,
    PUBLIC_PREFIX,
    make_active_menu_item,
    make_product,
    make_shop,
    shop_with_sellable_item,
)

_SHOPS = f"{API_PREFIX}/shops"


def _order_body(shop_menu_item_id: str, **overrides: Any) -> dict[str, Any]:
    return {
        "items": [{"shop_menu_item_id": shop_menu_item_id, "qty": 2}],
        "customer_name": "Иван",
        "customer_phone": "+79991112233",
        "delivery_type": "pickup",
        **overrides,
    }


class TestOrderCreate:
    async def test_order_totals_and_public_code(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"ord-{unique_id[:8]}"
        _, _, item = await shop_with_sellable_item(
            shop_client, slug, delivery_fee=30000
        )
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(
                item["shop_menu_item_id"],
                delivery_type="delivery",
                address="ул. Ленина, 1",
            ),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_minor"] == 50000 * 2 + 30000
        assert body["currency"] == "RUB"
        assert body["status"] == "new"
        assert len(body["public_code"]) >= 6

    async def test_order_idempotency_same_code(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"idem-{unique_id[:8]}"
        _, _, item = await shop_with_sellable_item(shop_client, slug)
        body = _order_body(item["shop_menu_item_id"], idempotency_key=f"k-{unique_id}")
        first = (
            await shop_public_client.post(
                f"{PUBLIC_PREFIX}/storefront/{slug}/orders", json=body
            )
        ).json()
        second = (
            await shop_public_client.post(
                f"{PUBLIC_PREFIX}/storefront/{slug}/orders", json=body
            )
        ).json()
        assert first["public_code"] == second["public_code"]
        shops = (await shop_client.get(_SHOPS)).json()["items"]
        shop_id = next(s["shop_id"] for s in shops if s["slug"] == slug)
        orders = (await shop_client.get(f"{_SHOPS}/{shop_id}/orders")).json()
        assert orders["total"] == 1

    async def test_order_status_by_public_code(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"st-{unique_id[:8]}"
        _, _, item = await shop_with_sellable_item(shop_client, slug)
        created = (
            await shop_public_client.post(
                f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
                json=_order_body(item["shop_menu_item_id"]),
            )
        ).json()
        status = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/orders/{created['public_code']}"
        )
        assert status.status_code == 200
        assert status.json()["status"] == "new"
        assert status.json()["public_code"] == created["public_code"]

    async def test_order_on_draft_shop_rejected(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Черновик заведения не принимает заказы даже на позицию активного меню."""
        slug = f"drord-{unique_id[:8]}"
        shop = await make_shop(shop_client, slug, name="Draft")
        product = await make_product(shop_client, shop["shop_id"], "X", 100)
        _, _, item = await make_active_menu_item(
            shop_client, shop["shop_id"], product["shop_product_id"]
        )
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(item["shop_menu_item_id"]),
        )
        assert resp.status_code == 404

    async def test_item_of_draft_menu_rejected(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Позиция меню, снятого в черновик, в заказ не берётся: menu_item_not_found."""
        slug = f"drmenu-{unique_id[:8]}"
        shop, _, item = await shop_with_sellable_item(shop_client, slug)
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/menus/{item['shop_menu_id']}/status",
            json={"status": "draft"},
        )
        assert resp.status_code == 200, resp.text
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(item["shop_menu_item_id"]),
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "menu_item_not_found"

    async def test_unknown_menu_item_rejected(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"nomi-{unique_id[:8]}"
        await shop_with_sellable_item(shop_client, slug)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(f"shopmi_missing_{unique_id[:8]}"),
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "menu_item_not_found"

    async def test_delivery_requires_address(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"noaddr-{unique_id[:8]}"
        _, _, item = await shop_with_sellable_item(shop_client, slug)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(item["shop_menu_item_id"], delivery_type="delivery"),
        )
        assert resp.status_code == 409

    async def test_order_rate_limited_by_ip(
        self, shop_client: AsyncClient, shop_app, shop_di, unique_id: str
    ) -> None:
        """11-й заказ с того же IP за минуту — 429."""
        from httpx2 import ASGITransport, AsyncClient

        slug = f"rl-{unique_id[:8]}"
        _, _, item = await shop_with_sellable_item(shop_client, slug)
        async with AsyncClient(
            transport=ASGITransport(app=shop_app),
            base_url="http://linnex.io",
            headers={
                "Host": "linnex.io",
                "X-Forwarded-For": f"203.0.113.{int(unique_id[:4], 16) % 254 + 1}",
            },
        ) as limited:
            for i in range(10):
                resp = await limited.post(
                    f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
                    json=_order_body(
                        item["shop_menu_item_id"], idempotency_key=f"rl-{i}-{unique_id}"
                    ),
                )
                assert resp.status_code == 200, resp.text
            resp = await limited.post(
                f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
                json=_order_body(
                    item["shop_menu_item_id"], idempotency_key=f"rl-x-{unique_id}"
                ),
            )
            assert resp.status_code == 429
            assert resp.json()["error_code"] == "order_rate_limited"

    async def test_unavailable_product_rejected(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"unav-{unique_id[:8]}"
        shop, product, item = await shop_with_sellable_item(shop_client, slug)
        await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}/products/{product['shop_product_id']}",
            json={"is_available": False},
        )
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(item["shop_menu_item_id"]),
        )
        assert resp.status_code == 409


    async def test_unavailable_menu_item_rejected(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Позиция, выключенная в меню, отклоняется при доступном блюде каталога."""
        slug = f"unmi-{unique_id[:8]}"
        shop, _, item = await shop_with_sellable_item(shop_client, slug)
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}/menu-items/{item['shop_menu_item_id']}",
            json={"is_available": False},
        )
        assert resp.status_code == 200, resp.text
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(item["shop_menu_item_id"]),
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "product_unavailable"

    async def test_menu_item_price_override_used(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Цена позиции меню перекрывает цену каталога; заказ хранит shop_menu_item_id."""
        slug = f"ovr-{unique_id[:8]}"
        shop, product, item = await shop_with_sellable_item(shop_client, slug)
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}/menu-items/{item['shop_menu_item_id']}",
            json={"price_minor_override": 42000},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["effective_price_minor"] == 42000
        created = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(item["shop_menu_item_id"]),
        )
        assert created.status_code == 200, created.text
        assert created.json()["total_minor"] == 42000 * 2
        orders = (await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/orders")).json()
        row = next(o for o in orders["items"] if o["public_code"] == created.json()["public_code"])
        assert [(i["product_id"], i["shop_menu_item_id"], i["price_minor"]) for i in row["items"]] == [
            (product["shop_product_id"], item["shop_menu_item_id"], 42000)
        ]


class TestOrderStatusFlow:
    async def test_status_transition_chain(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"flow-{unique_id[:8]}"
        shop, _, item = await shop_with_sellable_item(shop_client, slug)
        created = (
            await shop_public_client.post(
                f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
                json=_order_body(item["shop_menu_item_id"]),
            )
        ).json()
        orders = (await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/orders")).json()
        order_id = orders["items"][0]["shop_order_id"]
        url = f"{_SHOPS}/{shop['shop_id']}/orders/{order_id}/status"
        for status in ("accepted", "preparing", "delivering", "done"):
            resp = await shop_client.post(url, params={"status": status})
            assert resp.status_code == 200, (status, resp.text)
            assert resp.json()["status"] == status
        status = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/orders/{created['public_code']}"
        )
        assert status.json()["status"] == "done"

    async def test_invalid_transition_rejected(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"badtr-{unique_id[:8]}"
        shop, _, item = await shop_with_sellable_item(shop_client, slug)
        await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(item["shop_menu_item_id"]),
        )
        orders = (await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/orders")).json()
        order_id = orders["items"][0]["shop_order_id"]
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/orders/{order_id}/status",
            params={"status": "done"},
        )
        assert resp.status_code == 409

    async def test_orders_isolation(
        self,
        shop_client: AsyncClient,
        shop_client_company2: AsyncClient,
        shop_public_client: AsyncClient,
        unique_id: str,
    ) -> None:
        slug = f"oiso-{unique_id[:8]}"
        shop, _, item = await shop_with_sellable_item(shop_client, slug)
        await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(item["shop_menu_item_id"]),
        )
        resp = await shop_client_company2.get(f"{_SHOPS}/{shop['shop_id']}/orders")
        assert resp.status_code == 404

    async def test_order_embed_source_persisted(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Заказ из embed-виджета помечается source=embed и виден в админ-списке."""
        slug = f"emb-{unique_id[:8]}"
        shop, _, item = await shop_with_sellable_item(shop_client, slug)
        created = (
            await shop_public_client.post(
                f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
                json=_order_body(item["shop_menu_item_id"], source="embed"),
            )
        )
        assert created.status_code == 200, created.text
        orders = (
            await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/orders")
        ).json()
        row = next(
            o for o in orders["items"] if o["public_code"] == created.json()["public_code"]
        )
        assert row["source"] == "embed"
