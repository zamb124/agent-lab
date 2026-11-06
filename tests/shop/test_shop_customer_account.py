"""Кабинет покупателя shop: сквозные заказы, ownership, отмена, me, geo, PWA."""

from __future__ import annotations

from typing import Any

from httpx2 import ASGITransport, AsyncClient

from tests.fixtures.shop import API_PREFIX, PUBLIC_PREFIX, auth_customer

_SHOPS = f"{API_PREFIX}/shops"
_HOST = {"Host": "linnex.io"}


async def _shop_with_product(
    client: AsyncClient, slug: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    resp = await client.post(
        _SHOPS, json={"slug": slug, "name": f"Shop {slug}", "kind": "restaurant"}
    )
    assert resp.status_code == 200, resp.text
    shop = resp.json()
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


async def _order(
    client: AsyncClient, slug: str, product_id: str, **overrides: Any
) -> dict[str, Any]:
    resp = await client.post(
        f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
        json=_order_body(product_id, **overrides),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestMyOrders:
    async def test_cross_store_history(
        self,
        shop_app,
        shop_client: AsyncClient,
        shop_client_company2: AsyncClient,
        unique_id: str,
    ) -> None:
        """Один покупатель, заказы в двух витринах разных компаний — в одной ленте."""
        slug_a, slug_b = f"acc-a-{unique_id[:6]}", f"acc-b-{unique_id[:6]}"
        _, product_a = await _shop_with_product(shop_client, slug_a)
        _, product_b = await _shop_with_product(shop_client_company2, slug_b)
        phone = f"+7999{int(unique_id[:7], 16) % 10**7:07d}"

        async with AsyncClient(
            transport=ASGITransport(app=shop_app),
            base_url="http://linnex.io",
            headers=_HOST,
        ) as client:
            await auth_customer(client, slug_a, phone=phone)
            first = await _order(client, slug_a, product_a["shop_product_id"])
            # Верификация во второй витрине мержит scope: заказ в другой компании.
            await auth_customer(client, slug_b, phone=phone)
            second = await _order(client, slug_b, product_b["shop_product_id"])

            resp = await client.get(f"{PUBLIC_PREFIX}/my/orders")
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["total"] == 2
            codes = [i["public_code"] for i in body["items"]]
            assert codes == [second["public_code"], first["public_code"]]
            shops = {i["public_code"]: i["shop"] for i in body["items"]}
            assert shops[first["public_code"]]["slug"] == slug_a
            assert shops[second["public_code"]]["slug"] == slug_b
            assert all(i["active"] for i in body["items"])
            assert all(i["items_count"] == 1 for i in body["items"])

            me = await client.get(f"{PUBLIC_PREFIX}/customer-auth/me")
            assert me.status_code == 200
            assert len(me.json()["scope_company_ids"]) >= 2

    async def test_detail_and_status_history(
        self,
        shop_client: AsyncClient,
        shop_public_client: AsyncClient,
        unique_id: str,
    ) -> None:
        slug = f"det-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug)
        created = await _order(
            shop_public_client, slug, product["shop_product_id"]
        )
        detail = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/my/orders/{created['public_code']}"
        )
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["status"] == "new"
        assert body["can_cancel"] is True
        assert body["items"][0]["name"] == "Маргарита"
        assert body["items"][0]["qty"] == 2
        assert body["total_minor"] == 100000
        history = body["status_history"]
        assert [h["status"] for h in history] == ["new"]

        orders = (await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/orders")).json()
        order_id = orders["items"][0]["shop_order_id"]
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/orders/{order_id}/status",
            params={"status": "accepted"},
        )
        assert resp.status_code == 200, resp.text

        detail = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/my/orders/{created['public_code']}"
        )
        body = detail.json()
        assert body["status"] == "accepted"
        assert body["can_cancel"] is False
        assert [h["status"] for h in body["status_history"]] == ["new", "accepted"]

    async def test_ownership_isolation(
        self, shop_app, shop_client: AsyncClient, shop_public_client: AsyncClient,
        unique_id: str,
    ) -> None:
        """Чужой public_code для детали и отмены — not-found, а не access-denied."""
        slug = f"own-{unique_id[:8]}"
        _, product = await _shop_with_product(shop_client, slug)
        created = await _order(shop_public_client, slug, product["shop_product_id"])

        async with AsyncClient(
            transport=ASGITransport(app=shop_app),
            base_url="http://linnex.io",
            headers=_HOST,
        ) as stranger:
            await auth_customer(stranger, slug)
            detail = await stranger.get(
                f"{PUBLIC_PREFIX}/my/orders/{created['public_code']}"
            )
            assert detail.status_code == 404
            cancel = await stranger.post(
                f"{PUBLIC_PREFIX}/my/orders/{created['public_code']}/cancel"
            )
            assert cancel.status_code == 404
            listing = await stranger.get(f"{PUBLIC_PREFIX}/my/orders")
            assert listing.json()["total"] == 0

    async def test_cancel_only_when_new(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"cnc-{unique_id[:8]}"
        _, product = await _shop_with_product(shop_client, slug)
        created = await _order(shop_public_client, slug, product["shop_product_id"])
        code = created["public_code"]

        cancel = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/my/orders/{code}/cancel"
        )
        assert cancel.status_code == 200, cancel.text
        assert cancel.json()["status"] == "cancelled"

        again = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/my/orders/{code}/cancel"
        )
        assert again.status_code in (400, 409)

    async def test_my_orders_anonymous_401(
        self, shop_app, shop_di, unique_id: str
    ) -> None:
        _ = shop_di
        async with AsyncClient(
            transport=ASGITransport(app=shop_app),
            base_url="http://linnex.io",
            headers=_HOST,
        ) as anon:
            resp = await anon.get(f"{PUBLIC_PREFIX}/my/orders")
            assert resp.status_code == 401


class TestCustomerMe:
    async def test_me_and_rename(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"me-{unique_id[:8]}"
        await _shop_with_product(shop_client, slug)
        customer = await auth_customer(shop_public_client, slug)

        me = await shop_public_client.get(f"{PUBLIC_PREFIX}/customer-auth/me")
        assert me.status_code == 200, me.text
        assert me.json()["customer_id"] == customer["customer_id"]
        assert me.json()["phone_e164"] == customer["phone_e164"]

        renamed = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/customer-auth/me", json={"name": "Пётр"}
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["name"] == "Пётр"
        me = await shop_public_client.get(f"{PUBLIC_PREFIX}/customer-auth/me")
        assert me.json()["name"] == "Пётр"


class TestStorefrontGeoAndPwa:
    async def test_geo_shape(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"geo-{unique_id[:8]}"
        await _shop_with_product(shop_client, slug)
        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}/geo")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "lat" in body and "lng" in body and "delivery_zone" in body

    async def test_geo_missing_slug_404(
        self, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/no-{unique_id[:8]}/geo"
        )
        assert resp.status_code == 404

    async def test_pwa_files(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"pwa-{unique_id[:8]}"
        await _shop_with_product(shop_client, slug)
        manifest = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/{slug}/manifest.webmanifest"
        )
        assert manifest.status_code == 200, manifest.text
        body = manifest.json()
        assert body["name"]
        assert body["start_url"]
        icon = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/{slug}/icon.svg"
        )
        assert icon.status_code == 200
        assert "svg" in icon.headers["content-type"]
        sw = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}/sw.js")
        assert sw.status_code == 200
        assert "javascript" in sw.headers["content-type"]
