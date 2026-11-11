"""Часы работы витрины: shop_open_state (юниты) + блок заказа по API.

Семантика ``working_hours``: ключ "0".."6" (Пн..Вс), "HH:MM-HH:MM" локально
по ``shop.timezone``; ``om==cm`` — выходной; ``om>cm`` — overnight через
полночь. Пустой словарь — без ограничений (всегда открыто).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from httpx2 import AsyncClient

from apps.shop.services.hours import shop_open_state
from tests.fixtures.shop import API_PREFIX, PUBLIC_PREFIX, auth_customer
from tests.shop.test_shop_delivery_zone import _order_body, _shop_with_product

_SHOPS = f"{API_PREFIX}/shops"

_NOW = datetime(2026, 11, 4, 15, 0, tzinfo=UTC)  # среда 18:00 Москвы (UTC+3)


def _wh(day_hours: dict[int, str]) -> dict[str, str]:
    return {str(d): h for d, h in day_hours.items()}


class TestShopOpenState:
    def test_empty_hours_always_open(self) -> None:
        st = shop_open_state({}, "Europe/Moscow", _NOW)
        assert st.open and st.next_open is None

    def test_inside_range_open(self) -> None:
        st = shop_open_state(
            _wh({2: "09:00-22:00"}), "Europe/Moscow", _NOW
        )  # ср 18:00
        assert st.open

    def test_before_range_closed_today_label(self) -> None:
        before = _NOW.replace(hour=4)  # ср 07:00 Москва
        st = shop_open_state(_wh({2: "09:00-22:00"}), "Europe/Moscow", before)
        assert not st.open and st.next_open == "в 09:00"

    def test_after_range_closed_next_day(self) -> None:
        after = _NOW.replace(hour=20, minute=30)  # ср 23:30 Москва
        st = shop_open_state(
            _wh({2: "09:00-22:00", 3: "10:00-18:00"}), "Europe/Moscow", after
        )
        assert not st.open
        assert st.next_open == "завтра в 10:00"

    def test_day_off_skipped_to_next_workday(self) -> None:
        st = shop_open_state(
            _wh({5: "10:00-18:00"}), "Europe/Moscow", _NOW
        )  # ср — ближайшее Сб
        assert not st.open and st.next_open == "Сб в 10:00"

    def test_overnight_evening_open(self) -> None:
        evening = _NOW.replace(hour=20)  # ср 23:00 Москва
        st = shop_open_state(_wh({2: "22:00-06:00"}), "Europe/Moscow", evening)
        assert st.open

    def test_overnight_early_morning_open_from_prev_day(self) -> None:
        night = _NOW.replace(day=5, hour=0, minute=0)  # чт 03:00 Москва
        st = shop_open_state(_wh({2: "22:00-06:00"}), "Europe/Moscow", night)
        assert st.open

    def test_overnight_daytime_closed(self) -> None:
        st = shop_open_state(_wh({2: "22:00-06:00"}), "Europe/Moscow", _NOW)
        assert not st.open and st.next_open == "в 22:00"

    def test_all_days_off_closed_forever(self) -> None:
        st = shop_open_state(
            _wh(dict.fromkeys(range(7), "00:00-00:00")), "Europe/Moscow", _NOW
        )
        assert not st.open and st.next_open is None

    def test_bad_tz_falls_back_moscow(self) -> None:
        st = shop_open_state(_wh({2: "09:00-22:00"}), "Mars/Olympus", _NOW)
        assert st.open


async def _patch_hours(
    client: AsyncClient, shop: dict[str, Any], hours: dict[str, str]
) -> None:
    resp = await client.patch(
        f"{_SHOPS}/{shop['shop_id']}", json={"working_hours": hours}
    )
    assert resp.status_code == 200, resp.text


class TestClosedShopOrderRejection:
    async def test_closed_shop_rejects_all_types(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"closed-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug)
        await _patch_hours(
            shop_client, shop, dict.fromkeys((str(d) for d in range(7)), "00:00-00:00")
        )
        await auth_customer(shop_public_client, slug)
        for dtype in ("pickup", "delivery"):
            resp = await shop_public_client.post(
                f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
                json=_order_body(product["product_id"], delivery_type=dtype),
            )
            assert resp.status_code == 409, (dtype, resp.text)
            assert resp.json()["error_code"] == "shop_closed"

    async def test_open_now_range_accepts_order(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"open-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug)
        # Диапазон вокруг текущего часа по Москве — детерминированно открыто.
        hour = datetime.now(ZoneInfo("Europe/Moscow")).hour
        span = f"{(hour - 1) % 24:02d}:00-{(hour + 1) % 24:02d}:00"
        await _patch_hours(
            shop_client, shop, dict.fromkeys((str(d) for d in range(7)), span)
        )
        await auth_customer(shop_public_client, slug)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(product["product_id"], delivery_type="pickup"),
        )
        assert resp.status_code == 200, resp.text

    async def test_shop_closed_includes_next_open(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"nxt-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug)
        await _patch_hours(
            shop_client, shop, dict.fromkeys((str(d) for d in range(7)), "00:00-00:01")
        )
        await auth_customer(shop_public_client, slug)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(product["product_id"], delivery_type="pickup"),
        )
        assert resp.status_code == 409
        assert "next_open" in resp.json().get("error_params", {})
