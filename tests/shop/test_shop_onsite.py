"""Заказ «в заведении»: столы магазина, onsite-валидации, QR стола, снапшот."""

from __future__ import annotations

from typing import Any

from httpx2 import AsyncClient

from apps.shop.models import ShopOrder, ShopOrderItem
from apps.shop.services.notification_service import order_notify_text
from tests.fixtures.shop import API_PREFIX, PUBLIC_PREFIX

_SHOPS = f"{API_PREFIX}/shops"


async def _shop(
    client: AsyncClient, slug: str, *, onsite: bool = True
) -> dict[str, Any]:
    resp = await client.post(
        _SHOPS, json={"slug": slug, "name": f"Cafe {slug}", "kind": "restaurant", "lat": 55.7512, "lng": 37.6184}
    )
    assert resp.status_code == 200, resp.text
    shop = resp.json()
    if onsite:
        resp = await client.patch(
            f"{_SHOPS}/{shop['shop_id']}", json={"onsite_enabled": True}
        )
        assert resp.status_code == 200, resp.text
    await client.post(f"{_SHOPS}/{shop['shop_id']}/publish")
    resp = await client.post(
        f"{_SHOPS}/{shop['shop_id']}/products",
        json={"name": "Паста", "price_minor": 45000},
    )
    assert resp.status_code == 200, resp.text
    shop["product_id"] = resp.json()["shop_product_id"]
    return shop


async def _table(client: AsyncClient, shop_id: str, label: str = "Стол 5") -> dict[str, Any]:
    resp = await client.post(f"{_SHOPS}/{shop_id}/tables", json={"label": label})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _onsite_order(product_id: str, table_id: str, **overrides: Any) -> dict[str, Any]:
    return {
        "items": [{"product_id": product_id, "qty": 1}],
        "customer_name": "Гость",
        "delivery_type": "onsite",
        "table_id": table_id,
        **overrides,
    }


class TestShopTables:
    async def test_table_crud(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"tbl-{unique_id[:8]}"
        shop = await _shop(shop_client, slug)
        url = f"{_SHOPS}/{shop['shop_id']}/tables"

        table = await _table(shop_client, shop["shop_id"], "У окна")
        assert table["label"] == "У окна"
        assert table["shop_id"] == shop["shop_id"]

        items = (await shop_client.get(url)).json()["items"]
        assert [t["shop_table_id"] for t in items] == [table["shop_table_id"]]

        resp = await shop_client.patch(
            f"{url}/{table['shop_table_id']}", json={"label": "У барной стойки"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["label"] == "У барной стойки"

        resp = await shop_client.delete(f"{url}/{table['shop_table_id']}")
        assert resp.status_code == 200, resp.text
        assert (await shop_client.get(url)).json()["items"] == []

    async def test_tables_isolated_between_shops(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        slug_a, slug_b = f"ta-{unique_id[:8]}", f"tb-{unique_id[:8]}"
        shop_a = await _shop(shop_client, slug_a)
        shop_b = await _shop(shop_client, slug_b)
        table = await _table(shop_client, shop_a["shop_id"])

        resp = await shop_client.patch(
            f"{_SHOPS}/{shop_b['shop_id']}/tables/{table['shop_table_id']}",
            json={"label": "Чужой"},
        )
        assert resp.status_code == 404
        resp = await shop_client.delete(
            f"{_SHOPS}/{shop_b['shop_id']}/tables/{table['shop_table_id']}"
        )
        assert resp.status_code == 404
        items = (
            await shop_client.get(f"{_SHOPS}/{shop_b['shop_id']}/tables")
        ).json()["items"]
        assert items == []

    async def test_tables_isolated_between_companies(
        self,
        shop_client: AsyncClient,
        shop_client_company2: AsyncClient,
        unique_id: str,
    ) -> None:
        slug = f"tc-{unique_id[:8]}"
        shop = await _shop(shop_client, slug)
        resp = await shop_client_company2.get(f"{_SHOPS}/{shop['shop_id']}/tables")
        assert resp.status_code == 404
        resp = await shop_client_company2.post(
            f"{_SHOPS}/{shop['shop_id']}/tables", json={"label": "X"}
        )
        assert resp.status_code == 404

    async def test_onsite_enabled_roundtrip(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"oen-{unique_id[:8]}"
        resp = await shop_client.post(
            _SHOPS, json={"slug": slug, "name": "R", "kind": "restaurant", "lat": 55.7512, "lng": 37.6184}
        )
        shop = resp.json()
        assert shop["onsite_enabled"] is False
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}", json={"onsite_enabled": True}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["onsite_enabled"] is True


class TestOnsiteOrder:
    async def test_onsite_order_verified_phone(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"onp-{unique_id[:8]}"
        shop = await _shop(shop_client, slug)
        table = await _table(shop_client, shop["shop_id"])
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_onsite_order(shop["product_id"], table["shop_table_id"]),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "new"
        orders = (
            await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/orders")
        ).json()["items"]
        assert orders[0]["delivery_type"] == "onsite"
        assert orders[0]["table_id"] == table["shop_table_id"]
        assert orders[0]["table_label"] == "Стол 5"
        assert orders[0]["customer_phone"].startswith("+7")

    async def test_onsite_requires_enabled(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"off-{unique_id[:8]}"
        shop = await _shop(shop_client, slug, onsite=False)
        table = await _table(shop_client, shop["shop_id"])
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_onsite_order(shop["product_id"], table["shop_table_id"]),
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "onsite_disabled"

    async def test_onsite_requires_table(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"not-{unique_id[:8]}"
        shop = await _shop(shop_client, slug)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_onsite_order(shop["product_id"], table_id=""),
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "table_required"

    async def test_onsite_unknown_table(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"unk-{unique_id[:8]}"
        shop = await _shop(shop_client, slug)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_onsite_order(shop["product_id"], "shoptable_never"),
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "table_unknown"

    async def test_onsite_table_of_other_shop_rejected(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug_a, slug_b = f"xta-{unique_id[:8]}", f"xtb-{unique_id[:8]}"
        shop_a = await _shop(shop_client, slug_a)
        shop_b = await _shop(shop_client, slug_b)
        foreign = await _table(shop_client, shop_a["shop_id"])
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug_b}/orders",
            json=_onsite_order(shop_b["product_id"], foreign["shop_table_id"]),
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "table_unknown"

    async def test_pickup_and_delivery_use_session_phone(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Телефон не из формы: pickup/delivery берут верифицированный номер сессии."""
        slug = f"ph-{unique_id[:8]}"
        shop = await _shop(shop_client, slug)
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}", json={"delivery_enabled": True}
        )
        assert resp.status_code == 200, resp.text
        for dtype, extra in (("pickup", {}), ("delivery", {"address": "ул. Мира, 2"})):
            resp = await shop_public_client.post(
                f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
                json={
                    "items": [{"product_id": shop["product_id"], "qty": 1}],
                    "customer_name": "Гость",
                    "delivery_type": dtype,
                    **extra,
                },
            )
            assert resp.status_code == 200, (dtype, resp.text)
        orders = (
            await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/orders")
        ).json()["items"]
        assert {o["delivery_type"] for o in orders} == {"pickup", "delivery"}
        assert all(o["customer_phone"].startswith("+7") for o in orders)

    async def test_table_label_is_snapshot(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"snp-{unique_id[:8]}"
        shop = await _shop(shop_client, slug)
        table = await _table(shop_client, shop["shop_id"], "Стол 7")
        await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_onsite_order(shop["product_id"], table["shop_table_id"]),
        )
        await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}/tables/{table['shop_table_id']}",
            json={"label": "Стол 77"},
        )
        orders = (
            await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/orders")
        ).json()["items"]
        assert orders[0]["table_label"] == "Стол 7"

    async def test_onsite_idempotent(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"oid-{unique_id[:8]}"
        shop = await _shop(shop_client, slug)
        table = await _table(shop_client, shop["shop_id"])
        body = _onsite_order(
            shop["product_id"], table["shop_table_id"], idempotency_key=f"o-{unique_id}"
        )
        first = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders", json=body
        )
        second = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders", json=body
        )
        assert first.json()["public_code"] == second.json()["public_code"]
        orders = (
            await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/orders")
        ).json()
        assert orders["total"] == 1

    async def test_onsite_flow_skips_delivering(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"ofl-{unique_id[:8]}"
        shop = await _shop(shop_client, slug)
        table = await _table(shop_client, shop["shop_id"])
        created = (
            await shop_public_client.post(
                f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
                json=_onsite_order(shop["product_id"], table["shop_table_id"]),
            )
        ).json()
        orders = (
            await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/orders")
        ).json()
        order_id = orders["items"][0]["shop_order_id"]
        url = f"{_SHOPS}/{shop['shop_id']}/orders/{order_id}/status"
        for status in ("accepted", "preparing", "done"):
            resp = await shop_client.post(url, params={"status": status})
            assert resp.status_code == 200, (status, resp.text)
        status = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/orders/{created['public_code']}"
        )
        assert status.json()["status"] == "done"
        assert status.json()["delivery_type"] == "onsite"
        assert status.json()["table_label"] == "Стол 5"


class TestTableQr:
    async def test_table_qr_svg(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"tqr-{unique_id[:8]}"
        shop = await _shop(shop_client, slug)
        table = await _table(shop_client, shop["shop_id"])
        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/{slug}/tables/{table['shop_table_id']}/qr.svg"
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/svg")
        assert resp.headers["etag"]

    async def test_table_qr_unknown_table_404(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"tq4-{unique_id[:8]}"
        await _shop(shop_client, slug)
        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/{slug}/tables/shoptable_never/qr.svg"
        )
        assert resp.status_code == 404

    async def test_tables_in_snapshot(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"tsn-{unique_id[:8]}"
        shop = await _shop(shop_client, slug)
        table = await _table(shop_client, shop["shop_id"])
        snap = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert snap.status_code == 200, snap.text
        body = snap.json()
        assert body["onsite_enabled"] is True
        assert body["tables"] == [{"id": table["shop_table_id"], "label": "Стол 5"}]


class TestOnsiteNotify:
    async def test_notify_text_onsite_shows_table(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Строка стола в Telegram-тексте; у pickup такой строки нет."""
        slug = f"tgn-{unique_id[:8]}"
        shop = await _shop(shop_client, slug)
        table = await _table(shop_client, shop["shop_id"])
        await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_onsite_order(shop["product_id"], table["shop_table_id"]),
        )
        orders = (
            await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/orders")
        ).json()["items"]
        order = await ShopOrder.get_by_id(orders[0]["shop_order_id"])
        assert order is not None
        items = await ShopOrderItem.list_by_order(order.shop_order_id)
        text = order_notify_text(order, items)
        assert "В заведении: Стол 5" in text
        assert "Доставка" not in text
