"""Промо shop: CRUD акций, PromoEngine в заказе и preview корзины.

Продовый путь: реальный Postgres + Redis, REST-зеркала команд, публичный
/cart/price считается тем же движком, что и авторитетный create_order.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx2 import AsyncClient

from tests.fixtures.shop import API_PREFIX, PUBLIC_PREFIX

_SHOPS = f"{API_PREFIX}/shops"


async def _shop_with_product(
    client: AsyncClient, slug: str, price: int = 50000
) -> tuple[dict[str, Any], dict[str, Any]]:
    resp = await client.post(
        _SHOPS, json={"slug": slug, "name": f"Shop {slug}", "kind": "restaurant"}
    )
    assert resp.status_code == 200, resp.text
    shop = resp.json()
    await client.post(f"{_SHOPS}/{shop['shop_id']}/publish")
    resp = await client.post(
        f"{_SHOPS}/{shop['shop_id']}/products",
        json={"name": "Пицца", "price_minor": price},
    )
    assert resp.status_code == 200, resp.text
    return shop, resp.json()


async def _make_product(client: AsyncClient, shop_id: str, name: str, price: int) -> dict[str, Any]:
    resp = await client.post(
        f"{_SHOPS}/{shop_id}/products", json={"name": name, "price_minor": price}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _make_promo(
    client: AsyncClient, shop_id: str, name: str, **overrides: Any
) -> dict[str, Any]:
    body = {
        "name": name,
        "condition": {"type": "always"},
        "action": {"type": "percent_order", "pct": 10},
        **overrides,
    }
    resp = await client.post(f"{_SHOPS}/{shop_id}/promos", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _order_body(items: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    return {
        "items": items,
        "customer_name": "Иван",
        "delivery_type": "pickup",
        **kw,
    }


def _cart_body(items: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    return {"items": items, "delivery_type": "pickup", **kw}


class TestPromoAdmin:
    async def test_promo_crud(self, shop_client: AsyncClient, unique_id: str) -> None:
        shop, _ = await _shop_with_product(shop_client, f"pr-{unique_id[:8]}")
        shop_id = shop["shop_id"]
        promo = await _make_promo(
            shop_client,
            shop_id,
            "Скидка 10%",
            priority=5,
            stacking="exclusive",
            window={"weekdays": [0, 1, 2, 3, 4, 5, 6]},
        )
        pid = promo["shop_promo_id"]
        assert promo["priority"] == 5
        assert promo["stacking"] == "exclusive"
        listing = await shop_client.get(f"{_SHOPS}/{shop_id}/promos")
        assert listing.status_code == 200
        assert [p["shop_promo_id"] for p in listing.json()["promos"]] == [pid]
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop_id}/promos/{pid}", json={"is_active": False}
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False
        resp = await shop_client.delete(f"{_SHOPS}/{shop_id}/promos/{pid}")
        assert resp.status_code == 200
        listing = await shop_client.get(f"{_SHOPS}/{shop_id}/promos")
        assert listing.json()["promos"] == []

    async def test_isolation_other_company(
        self,
        shop_client: AsyncClient,
        shop_client_company2: AsyncClient,
        unique_id: str,
    ) -> None:
        shop, _ = await _shop_with_product(shop_client, f"pi-{unique_id[:8]}")
        resp = await shop_client_company2.get(f"{_SHOPS}/{shop['shop_id']}/promos")
        assert resp.status_code == 404


class TestPromoEngine:
    async def test_percent_items_discount_in_order(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"pd-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug, price=50000)
        await _make_promo(
            shop_client,
            shop["shop_id"],
            "-20% на пиццу",
            action={
                "type": "percent_items",
                "pct": 20,
                "product_ids": [product["shop_product_id"]],
            },
        )
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body([{"product_id": product["shop_product_id"], "qty": 2}]),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["total_minor"] == 2 * 50000 - 2 * 10000
        code = resp.json()["public_code"]
        status = await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/orders")
        order = next(o for o in status.json()["items"] if o["public_code"] == code)
        detail = await shop_client.get(
            f"{_SHOPS}/{shop['shop_id']}/orders/{order['shop_order_id']}"
        )
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["discount_minor"] == 20000
        assert body["items_total_minor"] == 100000
        assert body["items"][0]["discount_minor"] == 20000
        assert body["promos"][0]["name"] == "-20% на пиццу"
        assert body["promos"][0]["saved_minor"] == 20000

    async def test_cart_price_parity_with_order(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"pp-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug, price=30000)
        await _make_promo(
            shop_client,
            shop["shop_id"],
            "-10%",
            action={"type": "percent_order", "pct": 10},
        )
        items = [{"product_id": product["shop_product_id"], "qty": 3}]
        preview = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/cart/price",
            json=_cart_body(items),
        )
        assert preview.status_code == 200, preview.text
        pv = preview.json()
        assert pv["items_total_minor"] == 90000
        assert pv["discount_minor"] == 9000
        assert pv["total_minor"] == 81000
        assert pv["applied_promos"][0]["name"] == "-10%"
        assert pv["below_min_order"] is False
        order = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(items),
        )
        assert order.status_code == 200, order.text
        assert order.json()["total_minor"] == pv["total_minor"]

    async def test_n_plus_m_free_cheapest(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"nm-{unique_id[:8]}"
        shop, pizza = await _shop_with_product(shop_client, slug, price=50000)
        cola = await _make_product(shop_client, shop["shop_id"], "Кола", 10000)
        await _make_promo(
            shop_client,
            shop["shop_id"],
            "2+1",
            action={"type": "n_plus_m_free", "n": 2, "m": 1},
        )
        items = [
            {"product_id": pizza["shop_product_id"], "qty": 2},
            {"product_id": cola["shop_product_id"], "qty": 1},
        ]
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders", json=_order_body(items)
        )
        assert resp.status_code == 200, resp.text
        # Дешевейший из трёх — кола за 10000.
        assert resp.json()["total_minor"] == 110000 - 10000
        # Второй заказ: 3 пиццы → бесплатна одна пицца.
        resp2 = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body([{"product_id": pizza["shop_product_id"], "qty": 3}]),
        )
        assert resp2.status_code == 200
        assert resp2.json()["total_minor"] == 2 * 50000

    async def test_fixed_bundle_price(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"fb-{unique_id[:8]}"
        shop, pizza = await _shop_with_product(shop_client, slug, price=70000)
        cola = await _make_product(shop_client, shop["shop_id"], "Кола", 15000)
        await _make_promo(
            shop_client,
            shop["shop_id"],
            "Комбо 800",
            action={
                "type": "fixed_bundle_price",
                "price_minor": 80000,
                "items": [
                    {"product_id": pizza["shop_product_id"], "qty": 1},
                    {"product_id": cola["shop_product_id"], "qty": 1},
                ],
            },
        )
        items = [
            {"product_id": pizza["shop_product_id"], "qty": 1},
            {"product_id": cola["shop_product_id"], "qty": 1},
        ]
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders", json=_order_body(items)
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["total_minor"] == 80000
        # Одна пицца без колы — комбо не собирается, скидки нет.
        resp2 = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/cart/price",
            json=_cart_body([{"product_id": pizza["shop_product_id"], "qty": 1}]),
        )
        assert resp2.status_code == 200
        assert resp2.json()["discount_minor"] == 0
        assert resp2.json()["applied_promos"] == []

    async def test_exclusive_beats_lower_priority(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"ex-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug, price=50000)
        await _make_promo(
            shop_client,
            shop["shop_id"],
            "-5% обычная",
            priority=0,
            action={"type": "percent_order", "pct": 5},
        )
        await _make_promo(
            shop_client,
            shop["shop_id"],
            "-30% эксклюзив",
            priority=10,
            stacking="exclusive",
            action={"type": "percent_order", "pct": 30},
        )
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/cart/price",
            json=_cart_body([{"product_id": product["shop_product_id"], "qty": 2}]),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["discount_minor"] == 30000
        assert len(body["applied_promos"]) == 1
        assert body["applied_promos"][0]["name"] == "-30% эксклюзив"

    async def test_future_window_not_applied(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"wn-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug, price=50000)
        future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        await _make_promo(
            shop_client,
            shop["shop_id"],
            "Будущая акция",
            window={"starts_at": future},
            action={"type": "percent_order", "pct": 50},
        )
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/cart/price",
            json=_cart_body([{"product_id": product["shop_product_id"], "qty": 1}]),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["discount_minor"] == 0
        assert resp.json()["applied_promos"] == []

    async def test_inactive_promo_ignored(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"ia-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug, price=50000)
        await _make_promo(
            shop_client,
            shop["shop_id"],
            "Выключенная",
            is_active=False,
            action={"type": "percent_order", "pct": 90},
        )
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body([{"product_id": product["shop_product_id"], "qty": 1}]),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["total_minor"] == 50000

    async def test_free_delivery_over_min_total(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"fd-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug, price=100000)
        shop_id = shop["shop_id"]
        resp = await shop_client.patch(f"{_SHOPS}/{shop_id}", json={"delivery_fee_minor": 30000})
        assert resp.status_code == 200
        await _make_promo(
            shop_client,
            shop_id,
            "Бесплатная доставка от 800",
            condition={"type": "min_total", "minor": 80000},
            action={"type": "free_delivery"},
        )
        items = [{"product_id": product["shop_product_id"], "qty": 1}]
        preview = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/cart/price",
            json=_cart_body(items, delivery_type="delivery"),
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["delivery_fee_minor"] == 0
        assert preview.json()["total_minor"] == 100000
        order = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(items, delivery_type="delivery", address="ул. Ленина, 1"),
        )
        assert order.status_code == 200, order.text
        assert order.json()["total_minor"] == 100000

    async def test_storefront_snapshot_has_promos(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"sp-{unique_id[:8]}"
        shop, _ = await _shop_with_product(shop_client, slug)
        promo = await _make_promo(
            shop_client,
            shop["shop_id"],
            "Счастливые часы",
            action={"type": "n_plus_m_free", "n": 2, "m": 1},
        )
        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert resp.status_code == 200, resp.text
        promos = resp.json()["promos"]
        assert [p["id"] for p in promos] == [promo["shop_promo_id"]]
        assert promos[0]["name"] == "Счастливые часы"
        assert promos[0]["action"]["type"] == "n_plus_m_free"
