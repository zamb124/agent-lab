"""Зоны доставки: полигон директора, live delivery-check, изоляция адресов.

В тестовом окружении `GEOCODING__ENABLED=false` — геокодер детерминированно
возвращает None, поэтому зоновые проверки идут через сохранённые адреса
покупателя (`customer_address_id`, координаты в строке БД) — тот же путь,
что прод использует для адресов из чипов чекаута.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx2
import pytest
from httpx2 import AsyncClient
from oxyde import execute_raw

from apps.geo.models.geo_import_state import GeoImportState
from apps.shop.di import ShopDi
from apps.shop.models.shop import Shop
from apps.shop.services.order_service import ShopOrderService
from core.clients.geocoding.nominatim import NominatimGeocoder
from core.clients.service_client import ServiceClient
from core.config.models import GeocodingConfig
from core.customers.address_service import CustomerAddressService
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


_NOMINATIM_EMU_URL = "http://127.0.0.1:18098"


def _emu_geocoder(di: ShopDi) -> NominatimGeocoder:
    """Реальный NominatimGeocoder → локальный эмулятор провайдера на 18098."""
    return NominatimGeocoder(
        GeocodingConfig(enabled=True, nominatim_base_url=_NOMINATIM_EMU_URL),
        di.redis_client,
    )


class TestDeliveryCheckServiceChain:
    """Сервис ← реальный NominatimGeocoder ← эмулятор провайдера на 18098.

    Полная прод-цепочка check_delivery: запрос ``"<lat>,<lng>"`` отдаёт
    эмулятору точку, ответ парсится геокодером, точка проверяется по
    полигону магазина — без моков и перехвата HTTP.
    """

    async def test_inside_zone_deliverable(
        self,
        shop_client: AsyncClient,
        shop_di,
        nominatim_service: None,
        unique_id: str,
    ) -> None:
        _ = nominatim_service
        slug = f"svc-in-{unique_id[:8]}"
        _ = await _shop_with_product(
            shop_client, slug, patch={"delivery_zone": _ZONE}
        )
        shop = await Shop.get_by_slug(slug)
        assert shop is not None
        service = ShopOrderService(_emu_geocoder(shop_di), shop_di.service_client)
        result = await service.check_delivery(shop, "55.75,37.62")
        assert result["ok"] is True
        assert result["inside_zone"] is True
        assert result["lat"] == pytest.approx(55.75)

    async def test_outside_zone_not_deliverable(
        self,
        shop_client: AsyncClient,
        shop_di,
        nominatim_service: None,
        unique_id: str,
    ) -> None:
        _ = nominatim_service
        slug = f"svc-out-{unique_id[:8]}"
        _ = await _shop_with_product(
            shop_client, slug, patch={"delivery_zone": _ZONE}
        )
        shop = await Shop.get_by_slug(slug)
        assert shop is not None
        service = ShopOrderService(_emu_geocoder(shop_di), shop_di.service_client)
        result = await service.check_delivery(shop, "55.50,37.20")
        assert result["ok"] is False
        assert result["inside_zone"] is False
        assert result["reason"] == "out_of_delivery_zone"

    async def test_provider_empty_unverifiable(
        self,
        shop_client: AsyncClient,
        shop_di,
        nominatim_service: None,
        unique_id: str,
    ) -> None:
        _ = nominatim_service
        slug = f"svc-none-{unique_id[:8]}"
        _ = await _shop_with_product(
            shop_client, slug, patch={"delivery_zone": _ZONE}
        )
        shop = await Shop.get_by_slug(slug)
        assert shop is not None
        service = ShopOrderService(_emu_geocoder(shop_di), shop_di.service_client)
        result = await service.check_delivery(shop, f"Нет такого {unique_id}")
        assert result["ok"] is False
        assert result["reason"] == "address_unverifiable"

    async def test_order_create_saved_address_chain(
        self,
        shop_client: AsyncClient,
        shop_public_client: AsyncClient,
        shop_di,
        unique_id: str,
    ) -> None:
        """Заказ с `customer_address_id`: touch_used обновляет last_used_at."""
        slug = f"touch-{unique_id[:8]}"
        _, product = await _shop_with_product(shop_client, slug)
        customer = await auth_customer(shop_public_client, slug)
        row = await _save_address(customer["customer_id"], *_INSIDE, address="Дом")
        before = row.last_used_at
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(
                product["shop_product_id"], customer_address_id=row.customer_address_id
            ),
        )
        assert resp.status_code == 200, resp.text
        fresh = await CustomerAddress.get_for_customer(
            customer["customer_id"], row.customer_address_id
        )
        assert fresh is not None and fresh.last_used_at >= before


class TestCustomerAddressService:
    """CustomerAddressService: лимит, дедуп, изоляция владельца."""

    async def test_cap_evicts_oldest(
        self, shop_di, unique_id: str
    ) -> None:
        service = CustomerAddressService(shop_di.geocoder)
        cid = f"cust_cap_{unique_id[:8]}"
        for i in range(CustomerAddressService.MAX_ADDRESSES + 2):
            _ = await service.add(cid, address=f"Адрес {unique_id[:6]} {i}")
        rows = await service.list_for_customer(cid)
        assert len(rows) == CustomerAddressService.MAX_ADDRESSES
        # самые новые остались — вытеснены самые старые
        addrs = {r.address for r in rows}
        assert f"Адрес {unique_id[:6]} 0" not in addrs
        assert f"Адрес {unique_id[:6]} {CustomerAddressService.MAX_ADDRESSES + 1}" in addrs

    async def test_dedup_returns_same_row(
        self, shop_di, unique_id: str
    ) -> None:
        service = CustomerAddressService(shop_di.geocoder)
        cid = f"cust_dedup_{unique_id[:8]}"
        first = await service.add(cid, address=f"Одинаковый {unique_id[:6]}", label="Дом")
        second = await service.add(cid, address=f"одинаковый {unique_id[:6]}", label="Работа")
        assert first.customer_address_id == second.customer_address_id
        assert len(await service.list_for_customer(cid)) == 1

    async def test_delete_foreign_returns_false(
        self, shop_di, unique_id: str
    ) -> None:
        service = CustomerAddressService(shop_di.geocoder)
        row = await service.add(
            f"cust_a_{unique_id[:8]}", address=f"Чужой {unique_id[:6]}"
        )
        ok = await service.delete(
            f"cust_b_{unique_id[:8]}", row.customer_address_id
        )
        assert ok is False
        assert (
            await service.list_for_customer(f"cust_a_{unique_id[:8]}")
        )[0].customer_address_id == row.customer_address_id


class TestGeocodeEndpoints:
    """Геокод-эндпоинты при выключенном провайдере — детерминированные отказы."""

    async def test_aggregate_geocode_unverifiable(
        self, shop_public_client: AsyncClient
    ) -> None:
        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/aggregate/geocode", params={"address": "Москва"}
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "address_unverifiable"

    async def test_shop_geocode_op_unverifiable(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        resp = await shop_client.post(
            _SHOPS, json={"slug": f"geo-{unique_id[:8]}", "name": "G"}
        )
        shop: dict[str, Any] = resp.json()
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/geocode",
            json={"address": "Москва, Тверская 1"},
        )
        assert resp.status_code == 404
        assert resp.json()["error_code"] == "address_unverifiable"

    async def test_snapshot_contains_delivery_zone(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"snap-{unique_id[:8]}"
        _ = await _shop_with_product(
            shop_client, slug, patch={"delivery_zone": _ZONE}
        )
        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert resp.status_code == 200
        assert resp.json()["delivery_zone"]["type"] == "Polygon"


class TestMarketCoverage:
    async def test_aggregate_coverage_badges(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug_zoned = f"mz-{unique_id[:8]}"
        slug_open = f"mo-{unique_id[:8]}"
        _ = await _shop_with_product(
            shop_client, slug_zoned, patch={"delivery_zone": _ZONE}
        )
        _ = await _shop_with_product(shop_client, slug_open)
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


class TestDeliveryZoneValidation:
    """PATCH shops: delivery_zone — строго один внешний ring GeoJSON Polygon."""

    async def _patch(
        self, client: AsyncClient, slug: str, zone: Any
    ) -> httpx2.Response:
        resp = await client.post(
            _SHOPS, json={"slug": slug, "name": f"Z {slug}", "kind": "cafe"}
        )
        assert resp.status_code == 200, resp.text
        shop = resp.json()
        return await client.patch(
            f"{_SHOPS}/{shop['shop_id']}", json={"delivery_zone": zone}
        )

    async def test_valid_polygon_accepted(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        resp = await self._patch(shop_client, f"zv-ok-{unique_id[:8]}", _ZONE)
        assert resp.status_code == 200, resp.text

    async def test_empty_object_clears_zone(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        resp = await self._patch(shop_client, f"zv-clr-{unique_id[:8]}", {})
        assert resp.status_code == 200, resp.text

    async def test_multipolygon_rejected(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        zone = {"type": "MultiPolygon", "coordinates": [_ZONE["coordinates"]]}
        resp = await self._patch(shop_client, f"zv-mp-{unique_id[:8]}", zone)
        assert resp.status_code == 400
        assert resp.json()["error_code"] == "invalid_delivery_zone"

    async def test_polygon_with_hole_rejected(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        hole = _ZONE["coordinates"]
        zone = {"type": "Polygon", "coordinates": [hole, hole]}
        resp = await self._patch(shop_client, f"zv-h-{unique_id[:8]}", zone)
        assert resp.status_code == 400

    async def test_unclosed_ring_rejected(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        zone = {
            "type": "Polygon",
            "coordinates": [[[37.5, 55.7], [37.7, 55.7], [37.7, 55.8], [37.6, 55.9]]],
        }
        resp = await self._patch(shop_client, f"zv-u-{unique_id[:8]}", zone)
        assert resp.status_code == 400

    async def test_non_numeric_rejected(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        zone = {
            "type": "Polygon",
            "coordinates": [[["a", 55.7], [37.7, 55.7], [37.7, 55.8], ["a", 55.7]]],
        }
        resp = await self._patch(shop_client, f"zv-nn-{unique_id[:8]}", zone)
        assert resp.status_code == 400

    async def test_out_of_bounds_rejected(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        zone = {
            "type": "Polygon",
            "coordinates": [[[200.0, 55.7], [37.7, 55.7], [37.7, 55.8], [200.0, 55.7]]],
        }
        resp = await self._patch(shop_client, f"zv-b-{unique_id[:8]}", zone)
        assert resp.status_code == 400

    async def test_oversized_ring_rejected(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        # 257 точек замкнутого кольца — за пределом разумного редактора.
        ring = [[37.5 + i * 0.0001, 55.7] for i in range(256)]
        ring.append(ring[0])
        zone = {"type": "Polygon", "coordinates": [ring]}
        resp = await self._patch(shop_client, f"zv-big-{unique_id[:8]}", zone)
        assert resp.status_code == 400

    async def test_self_intersecting_bowtie_rejected(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        # «Песочные часы»: диагонали пересекаются — у зоны нет «внутри».
        zone = {
            "type": "Polygon",
            "coordinates": [
                [
                    [37.5, 55.7],
                    [37.7, 55.9],
                    [37.7, 55.7],
                    [37.5, 55.9],
                    [37.5, 55.7],
                ]
            ],
        }
        resp = await self._patch(shop_client, f"zv-bt-{unique_id[:8]}", zone)
        assert resp.status_code == 400
        assert resp.json()["error_code"] == "invalid_delivery_zone"

    async def test_pinched_ring_rejected(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        # Вершина (37.6, 55.75) повторяется вне соседних рёбер — защемление.
        zone = {
            "type": "Polygon",
            "coordinates": [
                [
                    [37.5, 55.7],
                    [37.7, 55.7],
                    [37.6, 55.75],
                    [37.5, 55.8],
                    [37.6, 55.75],
                    [37.5, 55.7],
                ]
            ],
        }
        resp = await self._patch(shop_client, f"zv-pn-{unique_id[:8]}", zone)
        assert resp.status_code == 400

    async def test_duplicate_vertex_rejected(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        # Дублирующаяся вершина подряд — нулевая грань.
        zone = {
            "type": "Polygon",
            "coordinates": [
                [
                    [37.5, 55.7],
                    [37.7, 55.7],
                    [37.7, 55.7],
                    [37.7, 55.8],
                    [37.5, 55.7],
                ]
            ],
        }
        resp = await self._patch(shop_client, f"zv-dv-{unique_id[:8]}", zone)
        assert resp.status_code == 400

    async def test_collinear_midpoint_accepted(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        # Точка на собственном ребре (как midpoint-вставка terra-draw) — легально.
        zone = {
            "type": "Polygon",
            "coordinates": [
                [
                    [37.5, 55.7],
                    [37.6, 55.7],
                    [37.7, 55.7],
                    [37.7, 55.8],
                    [37.5, 55.8],
                    [37.5, 55.7],
                ]
            ],
        }
        resp = await self._patch(shop_client, f"zv-mp2-{unique_id[:8]}", zone)
        assert resp.status_code == 200, resp.text


@pytest.mark.xdist_group("geo")
class TestCourierEta:
    """ETA курьера: ``prep_minutes`` + дорога по живому графу geo на 9028.

    Полная прод-цепочка: реальный ``NominatimGeocoder`` → эмулятор на 18098
    (адрес вида ``"<lat>,<lng>"`` геокодится в точку), ``GeoClient``/
    ``ServiceClient`` → granian geo. Граф — своё поколение ``_ETA_GEN``,
    опубликованное строкой ``geo_import_state``; синглтон сериализован
    общей группой ``xdist_group("geo")``.
    """

    _ETA_GEN = 880_000_001
    _SHOP_POINT = (55.75000, 37.61700)
    _CUST_POINT = (55.75030, 37.61840)
    _TRAVEL_S = 40.0

    async def _seed_graph(self) -> int:
        gen = self._ETA_GEN
        for table in ("geo_road_edges", "geo_road_vertices"):
            _ = await execute_raw(
                f"DELETE FROM {table} WHERE generation = $1", [gen], using="geo"
            )
        _ = await execute_raw(
            """
            INSERT INTO geo_road_vertices (node_id, lat, lng, generation)
            SELECT node_id, lat, lng, $1
            FROM (VALUES (1,55.75000,37.61700),(2,55.75030,37.61840)) AS v(node_id, lat, lng)
            """,
            [gen],
            using="geo",
        )
        _ = await execute_raw(
            """
            INSERT INTO geo_road_edges (
                source, target, src_lat, src_lng, dst_lat, dst_lng, length_m,
                car_cost, car_reverse_cost, foot_cost, foot_reverse_cost,
                bike_cost, bike_reverse_cost, scooter_cost, scooter_reverse_cost,
                oneway, highway, name, osm_way_id, generation
            ) VALUES (
                1,2,55.75000,37.61700,55.75030,37.61840,100.0,
                60,60,90,90,45,45,40,40, 0,'residential','тест',0,$1
            )
            """,
            [gen],
            using="geo",
        )
        state = await GeoImportState.get_state()
        previous = state.current_generation if state is not None else 0
        _ = await execute_raw(
            """
            INSERT INTO geo_import_state (id, current_generation, status, updated_at)
            VALUES (1, $1, 'idle', $2)
            ON CONFLICT (id) DO UPDATE SET current_generation = $1, updated_at = $2
            """,
            [gen, datetime.now(UTC)],
            using="geo",
        )
        return previous

    async def test_check_delivery_eta(
        self,
        geo_service: None,
        shop_di,
        nominatim_service: None,
        unique_id: str,
    ) -> None:
        _ = geo_service, nominatim_service
        previous = await self._seed_graph()
        try:
            svc = ShopOrderService(
                geocoder=_emu_geocoder(shop_di), service_client=ServiceClient()
            )
            shop = Shop(
                shop_id=f"eta-{unique_id[:8]}",
                company_id="system",
                slug=f"eta-{unique_id[:8]}",
                created_by_user_id="test",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                address=f"{self._SHOP_POINT[0]},{self._SHOP_POINT[1]}",
                prep_minutes=20,
                courier_mode="scooter",
            )
            result = await svc.check_delivery(
                shop, f"{self._CUST_POINT[0]},{self._CUST_POINT[1]}"
            )
            assert result["ok"] is True
            assert result["courier_mode"] == "scooter"
            assert result["prep_minutes"] == 20
            assert result["duration_s"] == pytest.approx(self._TRAVEL_S)
            # ETA = ceil((20*60 + 40) / 60) = 21 минута.
            assert result["eta_minutes"] == 21
        finally:
            _ = await execute_raw(
                "UPDATE geo_import_state SET current_generation = $1, updated_at = $2"
                " WHERE id = 1",
                [previous, datetime.now(UTC)],
                using="geo",
            )

    async def test_check_delivery_geo_down_graceful(
        self,
        geo_service: None,
        shop_di,
        nominatim_service: None,
        unique_id: str,
    ) -> None:
        """Без опубликованного поколения метрик нет, но чек жив (degrade)."""
        _ = geo_service, nominatim_service
        previous = await self._seed_graph()
        try:
            _ = await execute_raw(
                "UPDATE geo_import_state SET current_generation = 0, updated_at = $1"
                " WHERE id = 1",
                [datetime.now(UTC)],
                using="geo",
            )
            svc = ShopOrderService(
                geocoder=_emu_geocoder(shop_di), service_client=ServiceClient()
            )
            shop = Shop(
                shop_id=f"etad-{unique_id[:8]}",
                company_id="system",
                slug=f"etad-{unique_id[:8]}",
                created_by_user_id="test",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                address=f"{self._SHOP_POINT[0]},{self._SHOP_POINT[1]}",
            )
            result = await svc.check_delivery(
                shop, f"{self._CUST_POINT[0]},{self._CUST_POINT[1]}"
            )
            assert result["ok"] is True
            assert "eta_minutes" not in result
        finally:
            _ = await execute_raw(
                "UPDATE geo_import_state SET current_generation = $1, updated_at = $2"
                " WHERE id = 1",
                [previous, datetime.now(UTC)],
                using="geo",
            )
