"""Заказы shop: приём с витрины, идемпотентность, матрица статусов."""

from __future__ import annotations

from typing import Any

from httpx2 import AsyncClient

from tests.fixtures.shop import API_PREFIX, PUBLIC_PREFIX, auth_customer

_SHOPS = f"{API_PREFIX}/shops"


async def _shop_with_product(
    client: AsyncClient, slug: str, *, delivery_fee: int = 0
) -> tuple[dict[str, Any], dict[str, Any]]:
    resp = await client.post(
        _SHOPS,
        json={
            "slug": slug,
            "name": f"Shop {slug}",
            "kind": "restaurant",
        },
    )
    assert resp.status_code == 200, resp.text
    shop = resp.json()
    if delivery_fee:
        resp = await client.patch(
            f"{_SHOPS}/{shop['shop_id']}", json={"delivery_fee_minor": delivery_fee}
        )
        assert resp.status_code == 200
    await client.post(f"{_SHOPS}/{shop['shop_id']}/publish")
    resp = await client.post(
        f"{_SHOPS}/{shop['shop_id']}/products",
        json={"name": "Маргарита", "price_minor": 50000},
    )
    assert resp.status_code == 200, resp.text
    return shop, resp.json()


def _order_body(product_id: str, **overrides: Any) -> dict[str, Any]:
    return {
        "items": [{"product_id": product_id, "qty": 2}],
        "customer_name": "Иван",
        "delivery_type": "pickup",
        **overrides,
    }


class TestOrderCreate:
    async def test_order_totals_and_public_code(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"ord-{unique_id[:8]}"
        shop, product = await _shop_with_product(
            shop_client, slug, delivery_fee=30000
        )
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(
                product["shop_product_id"],
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
        _, product = await _shop_with_product(shop_client, slug)
        body = _order_body(product["shop_product_id"], idempotency_key=f"k-{unique_id}")
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
        _, product = await _shop_with_product(shop_client, slug)
        created = (
            await shop_public_client.post(
                f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
                json=_order_body(product["shop_product_id"]),
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
        slug = f"drord-{unique_id[:8]}"
        resp = await shop_client.post(
            _SHOPS, json={"slug": slug, "name": "Draft"}
        )
        shop = resp.json()
        await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/products",
            json={"name": "X", "price_minor": 100},
        )
        # Сессия покупателя есть (scope — компания), но витрина-черновик не опубликована.
        await auth_customer(shop_public_client, company_id="system")
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body("whatever"),
        )
        assert resp.status_code == 404

    async def test_delivery_requires_address(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"noaddr-{unique_id[:8]}"
        _, product = await _shop_with_product(shop_client, slug)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(product["shop_product_id"], delivery_type="delivery"),
        )
        assert resp.status_code == 409

    async def test_order_rate_limited_by_ip(
        self, shop_client: AsyncClient, shop_app, shop_di, unique_id: str
    ) -> None:
        """11-й заказ с того же IP за минуту — 429."""
        from httpx2 import ASGITransport, AsyncClient

        slug = f"rl-{unique_id[:8]}"
        _, product = await _shop_with_product(shop_client, slug)
        async with AsyncClient(
            transport=ASGITransport(app=shop_app),
            base_url="http://linnex.io",
            headers={
                "Host": "linnex.io",
                "X-Forwarded-For": f"203.0.113.{int(unique_id[:4], 16) % 254 + 1}",
            },
        ) as limited:
            await auth_customer(limited, slug)
            for i in range(10):
                resp = await limited.post(
                    f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
                    json=_order_body(
                        product["shop_product_id"], idempotency_key=f"rl-{i}-{unique_id}"
                    ),
                )
                assert resp.status_code == 200, resp.text
            resp = await limited.post(
                f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
                json=_order_body(
                    product["shop_product_id"], idempotency_key=f"rl-x-{unique_id}"
                ),
            )
            assert resp.status_code == 429
            assert resp.json()["error_code"] == "order_rate_limited"

    async def test_unavailable_product_rejected(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"unav-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug)
        await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}/products/{product['shop_product_id']}",
            json={"is_available": False},
        )
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(product["shop_product_id"]),
        )
        assert resp.status_code == 409


class TestOrderStatusFlow:
    async def test_status_transition_chain(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"flow-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug)
        created = (
            await shop_public_client.post(
                f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
                json=_order_body(product["shop_product_id"]),
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
        shop, product = await _shop_with_product(shop_client, slug)
        await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(product["shop_product_id"]),
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
        shop, product = await _shop_with_product(shop_client, slug)
        await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(product["shop_product_id"]),
        )
        resp = await shop_client_company2.get(f"{_SHOPS}/{shop['shop_id']}/orders")
        assert resp.status_code == 404

    async def test_order_embed_source_persisted(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Заказ из embed-виджета помечается source=embed и виден в админ-списке."""
        slug = f"emb-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug)
        created = (
            await shop_public_client.post(
                f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
                json=_order_body(product["shop_product_id"], source="embed"),
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
