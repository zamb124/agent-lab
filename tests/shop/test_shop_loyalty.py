"""Лояльность «N-я покупка — награда»: прогресс, claim, возврат.

Продовый путь: ``features.loyalty`` + ``PUT /shops/{id}/loyalty`` →
заказы покупателя до ``done`` → прогресс в ``/personal`` → награда →
``use_loyalty_reward`` в ``/cart/price`` и ``/orders`` → скидка в заказе,
возврат награды при отмене, полное отключение флагом.
"""

from __future__ import annotations

from httpx2 import AsyncClient

from core.types import JsonObject, parse_json_object
from tests.fixtures.shop import API_PREFIX, PUBLIC_PREFIX, auth_customer

_SHOPS = f"{API_PREFIX}/shops"


def _id(obj: JsonObject, key: str) -> str:
    value = obj[key]
    assert isinstance(value, str)
    return value


async def _published_shop(client: AsyncClient, slug: str) -> JsonObject:
    resp = await client.post(
        _SHOPS,
        json={"slug": slug, "name": f"LY {slug}", "kind": "cafe", "lat": 55.7512, "lng": 37.6184},
    )
    assert resp.status_code == 200, resp.text
    shop = parse_json_object(resp.text, "shop")
    resp = await client.post(f"{_SHOPS}/{_id(shop, 'shop_id')}/publish")
    assert resp.status_code == 200, resp.text
    return shop


async def _enable_loyalty(
    client: AsyncClient, shop_id: str, *, goal: int = 2, kind: str = "discount_minor", value: int = 50000
) -> None:
    resp = await client.patch(f"{_SHOPS}/{shop_id}", json={"features": {"loyalty": True}})
    assert resp.status_code == 200, resp.text
    resp = await client.put(
        f"{_SHOPS}/{shop_id}/loyalty",
        json={"orders_goal": goal, "reward_kind": kind, "reward_value": value},
    )
    assert resp.status_code == 200, resp.text


async def _product(client: AsyncClient, shop_id: str, name: str) -> JsonObject:
    resp = await client.post(
        f"{_SHOPS}/{shop_id}/products",
        json={"name": name, "price_minor": 25000},
    )
    assert resp.status_code == 200, resp.text
    return parse_json_object(resp.text, "product")


async def _order(
    public_client: AsyncClient, slug: str, product_id: str, *, reward: bool = False
) -> tuple[str, JsonObject]:
    """Заказ покупателя (pickup); (public_code, тело ответа)."""
    resp = await public_client.post(
        f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
        json={
            "customer_name": "Тест Лояльности",
            "delivery_type": "pickup",
            "items": [{"product_id": product_id, "qty": 1}],
            "use_loyalty_reward": reward,
        },
    )
    assert resp.status_code == 200, resp.text
    body = parse_json_object(resp.text, "order")
    return str(resp.json()["public_code"]), body


async def _order_id(admin: AsyncClient, shop_id: str, public_code: str) -> str:
    resp = await admin.get(f"{_SHOPS}/{shop_id}/orders")
    assert resp.status_code == 200, resp.text
    return next(
        str(o["shop_order_id"])
        for o in resp.json()["items"]
        if o["public_code"] == public_code
    )


async def _set_status(admin: AsyncClient, shop_id: str, order_id: str, status: str) -> None:
    resp = await admin.post(
        f"{_SHOPS}/{shop_id}/orders/{order_id}/status", params={"status": status}
    )
    assert resp.status_code == 200, (status, resp.text)


async def _order_done(
    admin: AsyncClient, public_client: AsyncClient, slug: str, shop_id: str, product_id: str
) -> str:
    code, _ = await _order(public_client, slug, product_id)
    order_id = await _order_id(admin, shop_id, code)
    for status in ("accepted", "preparing", "done"):
        await _set_status(admin, shop_id, order_id, status)
    return code


async def _loyalty_of(public_client: AsyncClient, slug: str) -> JsonObject | None:
    resp = await public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}/personal")
    assert resp.status_code == 200, resp.text
    data = parse_json_object(resp.text, "personal")
    loyalty = data.get("loyalty")
    return loyalty if isinstance(loyalty, dict) else None


class TestLoyalty:
    async def test_program_defaults_and_set(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """GET — дефолты без строки в БД; PUT — запись программы."""
        slug = f"lyp-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        resp = await shop_client.get(f"{_SHOPS}/{shop_id}/loyalty")
        assert resp.status_code == 200, resp.text
        program = resp.json()
        assert program["orders_goal"] == 5
        assert program["reward_kind"] == "discount_minor"
        assert program["reward_value"] == 50000
        resp = await shop_client.put(
            f"{_SHOPS}/{shop_id}/loyalty",
            json={"orders_goal": 3, "reward_kind": "discount_percent", "reward_value": 15},
        )
        assert resp.status_code == 200, resp.text
        program = resp.json()
        assert program["orders_goal"] == 3
        assert program["reward_kind"] == "discount_percent"
        assert program["reward_value"] == 15
        resp = await shop_client.get(f"{_SHOPS}/{shop_id}/loyalty")
        assert resp.json()["reward_value"] == 15

    async def test_progress_accrues_to_reward(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """goal=2: done → progress 1; второй done → награда и сброс прогресса."""
        slug = f"lya-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        await _enable_loyalty(shop_client, shop_id, goal=2)
        product = await _product(shop_client, shop_id, "Латте")
        _ = await auth_customer(shop_public_client, slug)

        _ = await _order_done(
            shop_client, shop_public_client, slug, shop_id, _id(product, "product_id")
        )
        loyalty = await _loyalty_of(shop_public_client, slug)
        assert loyalty is not None
        assert loyalty["progress"] == 1
        assert loyalty["rewards_available"] == 0
        assert loyalty["orders_goal"] == 2

        _ = await _order_done(
            shop_client, shop_public_client, slug, shop_id, _id(product, "product_id")
        )
        loyalty = await _loyalty_of(shop_public_client, slug)
        assert loyalty is not None
        assert loyalty["progress"] == 0
        assert loyalty["rewards_available"] == 1

    async def test_goal_one_grants_reward_each_order(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """goal=1 — краевой случай: каждый done сразу даёт награду."""
        slug = f"lyg-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        await _enable_loyalty(shop_client, shop_id, goal=1)
        product = await _product(shop_client, shop_id, "Чай")
        _ = await auth_customer(shop_public_client, slug)

        _ = await _order_done(
            shop_client, shop_public_client, slug, shop_id, _id(product, "product_id")
        )
        loyalty = await _loyalty_of(shop_public_client, slug)
        assert loyalty is not None
        assert loyalty["progress"] == 0
        assert loyalty["rewards_available"] == 1

    async def test_reward_claim_discounts_order(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """claim: cart/price показывает скидку, заказ пишет loyalty_reward_minor."""
        slug = f"lyc-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        await _enable_loyalty(shop_client, shop_id, goal=1, value=10000)
        product = await _product(shop_client, shop_id, "Латте")
        _ = await auth_customer(shop_public_client, slug)
        pid = _id(product, "product_id")
        _ = await _order_done(shop_client, shop_public_client, slug, shop_id, pid)

        # Предпросмотр корзины — скидка видна до заказа, награда не списана.
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/cart/price",
            json={
                "items": [{"product_id": pid, "qty": 1}],
                "delivery_type": "pickup",
                "use_loyalty_reward": True,
            },
        )
        assert resp.status_code == 200, resp.text
        priced = resp.json()
        assert priced["loyalty_reward_minor"] == 10000
        assert priced["total_minor"] == priced["items_total_minor"] - 10000

        code, body = await _order(shop_public_client, slug, pid, reward=True)
        assert body["loyalty_reward_minor"] == 10000
        assert body["total_minor"] == 25000 - 10000

        loyalty = await _loyalty_of(shop_public_client, slug)
        assert loyalty is not None
        assert loyalty["rewards_available"] == 0

        # Деталь заказа кабинета несёт скидку награды.
        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/my/orders/{code}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["loyalty_reward_minor"] == 10000

    async def test_claim_without_reward_conflict(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """use_loyalty_reward без наград — 409 loyalty_reward_unavailable."""
        slug = f"lyn-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        await _enable_loyalty(shop_client, shop_id, goal=5)
        product = await _product(shop_client, shop_id, "Латте")
        _ = await auth_customer(shop_public_client, slug)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json={
                "customer_name": "Тест",
                "delivery_type": "pickup",
                "items": [{"product_id": _id(product, "product_id"), "qty": 1}],
                "use_loyalty_reward": True,
            },
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["error_code"] == "loyalty_reward_unavailable"

    async def test_cancel_returns_reward(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Отмена заказа с наградой возвращает её на счёт покупателя."""
        slug = f"lyr-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        await _enable_loyalty(shop_client, shop_id, goal=1)
        product = await _product(shop_client, shop_id, "Латте")
        _ = await auth_customer(shop_public_client, slug)
        pid = _id(product, "product_id")
        _ = await _order_done(shop_client, shop_public_client, slug, shop_id, pid)

        code, _ = await _order(shop_public_client, slug, pid, reward=True)
        loyalty = await _loyalty_of(shop_public_client, slug)
        assert loyalty is not None
        assert loyalty["rewards_available"] == 0

        order_id = await _order_id(shop_client, shop_id, code)
        await _set_status(shop_client, shop_id, order_id, "cancelled")
        loyalty = await _loyalty_of(shop_public_client, slug)
        assert loyalty is not None
        assert loyalty["rewards_available"] == 1

    async def test_feature_disabled(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Флаг выключен: personal без loyalty, claim — 409, снапшот пуст."""
        slug = f"lyd-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        product = await _product(shop_client, shop_id, "Латте")
        _ = await auth_customer(shop_public_client, slug)

        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}/personal")
        assert resp.status_code == 200, resp.text
        assert resp.json()["loyalty"] is None

        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json={
                "customer_name": "Тест",
                "delivery_type": "pickup",
                "items": [{"product_id": _id(product, "product_id"), "qty": 1}],
                "use_loyalty_reward": True,
            },
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["error_code"] == "loyalty_disabled"

        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/cart/price",
            json={
                "items": [{"product_id": _id(product, "product_id"), "qty": 1}],
                "delivery_type": "pickup",
                "use_loyalty_reward": True,
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["loyalty_reward_minor"] == 0

        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert resp.status_code == 200, resp.text
        snap = parse_json_object(resp.text, "snapshot")
        assert snap.get("loyalty") is None

    async def test_snapshot_exposes_program_when_on(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """При включённой фиче снапшот несёт параметры программы для UI."""
        slug = f"lys-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        await _enable_loyalty(
            shop_client, shop_id, goal=7, kind="discount_percent", value=20
        )
        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert resp.status_code == 200, resp.text
        snap = parse_json_object(resp.text, "snapshot")
        loyalty = snap.get("loyalty")
        assert isinstance(loyalty, dict)
        assert loyalty["orders_goal"] == 7
        assert loyalty["reward_kind"] == "discount_percent"
        assert loyalty["reward_value"] == 20

    async def test_percent_reward_caps_at_items_total(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Процентная награда считается от суммы позиций, без доставки."""
        slug = f"lyv-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        await _enable_loyalty(
            shop_client, shop_id, goal=1, kind="discount_percent", value=50
        )
        product = await _product(shop_client, shop_id, "Латте")
        _ = await auth_customer(shop_public_client, slug)
        pid = _id(product, "product_id")
        _ = await _order_done(shop_client, shop_public_client, slug, shop_id, pid)

        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/cart/price",
            json={
                "items": [{"product_id": pid, "qty": 2}],
                "delivery_type": "pickup",
                "use_loyalty_reward": True,
            },
        )
        assert resp.status_code == 200, resp.text
        priced = resp.json()
        assert priced["loyalty_reward_minor"] == priced["items_total_minor"] // 2
