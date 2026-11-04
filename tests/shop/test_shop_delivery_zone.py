"""Зоны доставки: полигон директора, live delivery-check, изоляция адресов.

В тестовом окружении `GEOCODING__ENABLED=false` — геокодер детерминированно
возвращает None, поэтому зоновые проверки идут через сохранённые адреса
покупателя (`customer_address_id`, координаты в строке БД) — тот же путь,
что прод использует для адресов из чипов чекаута.
"""

from __future__ import annotations

from typing import Any

from httpx2 import AsyncClient

from core.customers.contracts import new_id
from core.customers.models import CustomerAddress
from tests.fixtures.shop import API_PREFIX, PUBLIC_PREFIX, auth_customer

_SHOPS = f"{API_PREFIX}/shops"
_AUTH = f"{PUBLIC_PREFIX}/customer-auth"

# Полигон «центр Москвы»: квадрат lng 37.55-37.75, lat 55.70-55.80.
_ZONE = {
    "type": "Polygon",
    "coordinates": [
        [
            [37.55, 55.70],
            [37.75, 55.70],
            [37.75, 55.80],
            [37.55, 55.80],
            [37.55, 55.70],
        ]
    ],
}
_INSIDE = (55.75, 37.62)   # (lat, lng) внутри квадрата
_OUTSIDE = (55.50, 37.20)  # далеко за пределами


async def _shop_with_product(
    client: AsyncClient, slug: str, *, patch: dict[str, Any] | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    resp = await client.post(
        _SHOPS, json={"slug": slug, "name": f"Shop {slug}", "kind": "restaurant"}
    )
    assert resp.status_code == 200, resp.text
    shop = resp.json()
    if patch:
        resp = await client.patch(f"{_SHOPS}/{shop['shop_id']}", json=patch)
        assert resp.status_code == 200, resp.text
    await client.post(f"{_SHOPS}/{shop['shop_id']}/publish")
    resp = await client.post(
        f"{_SHOPS}/{shop['shop_id']}/products",
        json={"name": "Маргарита", "price_minor": 50000},
    )
    assert resp.status_code == 200, resp.text
    return shop, resp.json()


def _order_body(product_id: str, **overrides: Any) -> dict[str, Any]:
    return {
        "items": [{"product_id": product_id, "qty": 1}],
        "customer_name": "Иван",
        "delivery_type": "delivery",
        **overrides,
    }


async def _save_address(
    customer_id: str, lat: float, lng: float, address: str
) -> CustomerAddress:
    row = CustomerAddress(
        customer_address_id=new_id("caddr"),
        customer_id=customer_id,
        label="Дом",
        address=address,
        lat=lat,
        lng=lng,
    )
    return await CustomerAddress.objects.create(instance=row)


class TestDeliveryZoneEnforcement:
    async def test_saved_address_inside_zone_delivers(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"zin-{unique_id[:8]}"
        _, product = await _shop_with_product(
            shop_client, slug, patch={"delivery_zone": _ZONE}
        )
        customer = await auth_customer(shop_public_client, slug)
        row = await _save_address(
            customer["customer_id"], *_INSIDE, address="Москва, Тверская 1"
        )
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(
                product["shop_product_id"], customer_address_id=row.customer_address_id
            ),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["total_minor"] == 50000

    async def test_saved_address_outside_zone_rejected(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"zout-{unique_id[:8]}"
        _, product = await _shop_with_product(
            shop_client, slug, patch={"delivery_zone": _ZONE}
        )
        customer = await auth_customer(shop_public_client, slug)
        row = await _save_address(
            customer["customer_id"], *_OUTSIDE, address="Московская обл, Одинцово"
        )
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(
                product["shop_product_id"], customer_address_id=row.customer_address_id
            ),
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "out_of_delivery_zone"

    async def test_foreign_address_rejected(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """`customer_address_id` чужого покупателя — address_unknown, не чужие координаты."""
        slug = f"zfrg-{unique_id[:8]}"
        _, product = await _shop_with_product(shop_client, slug)
        row = await _save_address("cust_someone_else", *_INSIDE, address="Чужой адрес")
        await auth_customer(shop_public_client, slug)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(
                product["shop_product_id"], customer_address_id=row.customer_address_id
            ),
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "address_unknown"

    async def test_zone_with_unverifiable_address_rejected(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Текстовый адрес + зона: без рабочего геокода — address_unverifiable, не пропуск."""
        slug = f"zunv-{unique_id[:8]}"
        _, product = await _shop_with_product(
            shop_client, slug, patch={"delivery_zone": _ZONE}
        )
        await auth_customer(shop_public_client, slug)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(
                product["shop_product_id"], address="Москва, Тверская 1"
            ),
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "address_unverifiable"


class TestDeliveryCheckEndpoint:
    async def test_no_zone_any_address_ok(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"chk-{unique_id[:8]}"
        await _shop_with_product(shop_client, slug)
        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/{slug}/delivery-check",
            params={"address": "Москва, Тверская 1"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is True
        assert body["requires_zone"] is False

    async def test_zone_unverifiable_address_not_ok(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"chkz-{unique_id[:8]}"
        await _shop_with_product(shop_client, slug, patch={"delivery_zone": _ZONE})
        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/{slug}/delivery-check",
            params={"address": "Москва, Тверская 1"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ok"] is False
        assert body["reason"] == "address_unverifiable"
        assert body["requires_zone"] is True

    async def test_delivery_disabled(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"chkoff-{unique_id[:8]}"
        await _shop_with_product(shop_client, slug, patch={"delivery_enabled": False})
        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/{slug}/delivery-check",
            params={"address": "Москва"},
        )
        assert resp.status_code == 200
        assert resp.json()["reason"] == "delivery_disabled"


class TestCustomerScopeInvariant:
    async def test_wrong_company_scope_forbidden(
        self,
        shop_client: AsyncClient,
        shop_client_company2: AsyncClient,
        shop_public_client: AsyncClient,
        unique_id: str,
    ) -> None:
        """Сессия покупателя от витрины system не заказывает у компании company2."""
        slug = f"scope-{unique_id[:8]}"
        _, product = await _shop_with_product(shop_client_company2, slug)
        await auth_customer(shop_public_client, company_id="system")
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(product["shop_product_id"], delivery_type="pickup"),
        )
        assert resp.status_code == 403
        assert resp.json()["error_code"] == "forbidden_scope"

    async def test_phone_comes_from_session(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """В заказе — верифицированный телефон сессии, а не что-то из формы."""
        slug = f"ph-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug)
        phone = f"+7999{int(unique_id[:7], 16) % 10**7:07d}"
        customer = await auth_customer(shop_public_client, slug, phone=phone)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(product["shop_product_id"], delivery_type="pickup"),
        )
        assert resp.status_code == 200, resp.text
        orders = await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/orders")
        assert orders.status_code == 200
        order = next(o for o in orders.json()["items"] if o["public_code"] == resp.json()["public_code"])
        assert order["customer_phone"] == customer["phone_e164"] == phone


class TestCustomerAddressesApi:
    async def test_crud_roundtrip(
        self, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        await auth_customer(shop_public_client, company_id="system")
        resp = await shop_public_client.post(
            f"{_AUTH}/addresses",
            json={"address": "Москва, Тверская 1", "label": "Дом"},
        )
        assert resp.status_code == 200, resp.text
        view = resp.json()
        assert view["address"] == "Москва, Тверская 1"
        assert view["label"] == "Дом"

        listed = await shop_public_client.get(f"{_AUTH}/addresses")
        assert listed.status_code == 200
        ids = [a["customer_address_id"] for a in listed.json()["addresses"]]
        assert view["customer_address_id"] in ids

        deleted = await shop_public_client.delete(
            f"{_AUTH}/addresses/{view['customer_address_id']}"
        )
        assert deleted.status_code in (200, 204)
        listed = await shop_public_client.get(f"{_AUTH}/addresses")
        ids = [a["customer_address_id"] for a in listed.json()["addresses"]]
        assert view["customer_address_id"] not in ids

    async def test_duplicate_address_dedup(
        self, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Тот же адрес дважды → одна строка (touch_used), не дубликат."""
        await auth_customer(shop_public_client, company_id="system")
        body = {"address": f"Москва, ул. {unique_id[:6]}", "label": "Дом"}
        first = await shop_public_client.post(f"{_AUTH}/addresses", json=body)
        second = await shop_public_client.post(f"{_AUTH}/addresses", json=body)
        assert first.status_code == 200 and second.status_code == 200
        assert (
            first.json()["customer_address_id"]
            == second.json()["customer_address_id"]
        )

    async def test_addresses_require_session(
        self, shop_public_client: AsyncClient
    ) -> None:
        resp = await shop_public_client.get(f"{_AUTH}/addresses")
        assert resp.status_code == 401


class TestMarketCoverage:
    async def test_aggregate_coverage_badges(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug_zoned = f"mz-{unique_id[:8]}"
        slug_open = f"mo-{unique_id[:8]}"
        await _shop_with_product(
            shop_client, slug_zoned, patch={"delivery_zone": _ZONE}
        )
        await _shop_with_product(shop_client, slug_open)
        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/aggregate/shops",
            params={"lat": _INSIDE[0], "lng": _INSIDE[1]},
        )
        assert resp.status_code == 200, resp.text
        by_slug = {i["slug"]: i for i in resp.json()["items"]}
        assert by_slug[slug_zoned]["delivery_coverage"] == "yes"
        assert by_slug[slug_open]["delivery_coverage"] == "unknown"

        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/aggregate/shops",
            params={"lat": _OUTSIDE[0], "lng": _OUTSIDE[1]},
        )
        by_slug = {i["slug"]: i for i in resp.json()["items"]}
        assert by_slug[slug_zoned]["delivery_coverage"] == "no"
