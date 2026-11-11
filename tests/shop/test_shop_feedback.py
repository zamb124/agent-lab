"""Отзывы на заказ: оценка выполненного заказа, лента витрины, рейтинг.

Продовый путь: заказ покупателем → перевод в ``done`` админом →
POST ``/storefront/{slug}/orders/{code}/feedback`` → отзыв в
``/my/orders``, лента ``/storefront/{slug}/reviews`` и агрегат
``rating`` в снапшоте витрины (после инвалидации кэша).
"""

from __future__ import annotations

from httpx2 import AsyncClient

from apps.shop.models.order_feedback import ShopOrderFeedback
from core.types import JsonObject, JsonValue, parse_json_object
from tests.fixtures.shop import API_PREFIX, PUBLIC_PREFIX, auth_customer

_SHOPS = f"{API_PREFIX}/shops"


async def _published_shop(client: AsyncClient, slug: str) -> JsonObject:
    resp = await client.post(
        _SHOPS,
        json={"slug": slug, "name": f"FB {slug}", "kind": "cafe", "lat": 55.7512, "lng": 37.6184},
    )
    assert resp.status_code == 200, resp.text
    shop = parse_json_object(resp.text, "shop")
    resp = await client.post(f"{_SHOPS}/{_id(shop, 'shop_id')}/publish")
    assert resp.status_code == 200, resp.text
    return shop


async def _product(client: AsyncClient, shop_id: str, name: str) -> JsonObject:
    resp = await client.post(
        f"{_SHOPS}/{shop_id}/products",
        json={"name": name, "price_minor": 25000},
    )
    assert resp.status_code == 200, resp.text
    return parse_json_object(resp.text, "product")


async def _order_done(
    admin: AsyncClient,
    public_client: AsyncClient,
    slug: str,
    shop_id: str,
    product_id: str,
) -> tuple[str, str]:
    """Заказ покупателя → ``done`` цепочкой статусов; (public_code, order_id)."""
    resp = await public_client.post(
        f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
        json={
            "customer_name": "Тест Отзывов",
            "delivery_type": "pickup",
            "items": [{"product_id": product_id, "qty": 1}],
        },
    )
    assert resp.status_code == 200, resp.text
    code = str(resp.json()["public_code"])
    admin_orders = await admin.get(f"{_SHOPS}/{shop_id}/orders")
    assert admin_orders.status_code == 200, admin_orders.text
    order_id = next(
        str(o["shop_order_id"])
        for o in admin_orders.json()["items"]
        if o["public_code"] == code
    )
    url = f"{_SHOPS}/{shop_id}/orders/{order_id}/status"
    for status in ("accepted", "preparing", "done"):
        resp = await admin.post(url, params={"status": status})
        assert resp.status_code == 200, (status, resp.text)
    return code, order_id


def _id(obj: JsonObject, key: str) -> str:
    value = obj[key]
    assert isinstance(value, str)
    return value


def _str_rows(obj: JsonObject, key: str) -> list[str]:
    raw = obj[key]
    assert isinstance(raw, list)
    return [x for x in raw if isinstance(x, str)]


def _feedback_url(slug: str, code: str) -> str:
    return f"{PUBLIC_PREFIX}/storefront/{slug}/orders/{code}/feedback"


class TestFeedback:
    async def test_anonymous_feedback_rejected(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"fba-{unique_id[:8]}"
        _ = await _published_shop(shop_client, slug)
        resp = await shop_public_client.post(
            _feedback_url(slug, "ABCD"), json={"rating": 5}
        )
        assert resp.status_code in (401, 403), resp.text

    async def test_feedback_requires_done_order(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Свежий заказ (``new``) оценить нельзя — 409 feedback_not_ready."""
        slug = f"fbr-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        product = await _product(shop_client, shop_id, "Латте")
        _ = await auth_customer(shop_public_client, slug)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json={
                "customer_name": "Тест Отзывов",
                "delivery_type": "pickup",
                "items": [{"product_id": _id(product, "product_id"), "qty": 1}],
            },
        )
        assert resp.status_code == 200, resp.text
        code = str(resp.json()["public_code"])
        resp = await shop_public_client.post(
            _feedback_url(slug, code), json={"rating": 5}
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["error_code"] == "feedback_not_ready"

    async def test_feedback_foreign_order_rejected(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Чужой по ``public_code`` — 404, строка отзыва не создаётся."""
        slug = f"fbf-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        product = await _product(shop_client, shop_id, "Латте")

        _ = await auth_customer(shop_public_client, slug)
        code, order_id = await _order_done(
            shop_client, shop_public_client, slug, shop_id, _id(product, "product_id")
        )

        # Ре-авторизация тем же клиентом — новый покупатель (новый телефон):
        # чужой public_code для него выглядит как несуществующий.
        second = await auth_customer(shop_public_client, slug)
        assert second["customer_id"] != ""
        resp = await shop_public_client.post(
            _feedback_url(slug, code), json={"rating": 1}
        )
        assert resp.status_code == 404, resp.text
        assert await ShopOrderFeedback.find_by_order(order_id) is None

    async def test_feedback_create_and_update_idempotent(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"fbc-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        product = await _product(shop_client, shop_id, "Латте")
        customer = await auth_customer(shop_public_client, slug)
        code, order_id = await _order_done(
            shop_client, shop_public_client, slug, shop_id, _id(product, "product_id")
        )

        resp = await shop_public_client.post(
            _feedback_url(slug, code),
            json={"rating": 5, "chips": ["quality", "speed"], "comment": "Супер"},
        )
        assert resp.status_code == 200, resp.text
        body = parse_json_object(resp.text, "feedback")
        assert body["rating"] == 5
        assert _str_rows(body, "chips") == ["quality", "speed"]
        labels = body["chip_labels"]
        assert isinstance(labels, dict)
        assert labels["quality"] == "Качество на уровне"

        # Повторная отправка — редактирование той же строки, не дубль.
        resp = await shop_public_client.post(
            _feedback_url(slug, code), json={"rating": 3, "comment": "Норм"}
        )
        assert resp.status_code == 200, resp.text
        rows = await ShopOrderFeedback.list_many_by_order_ids([order_id])
        assert len(rows) == 1
        assert rows[0].rating == 3
        assert rows[0].customer_id == str(customer["customer_id"])

        # Детали заказа: отзыв на месте, can_review снят.
        detail = await shop_public_client.get(f"{PUBLIC_PREFIX}/my/orders/{code}")
        assert detail.status_code == 200, detail.text
        data = detail.json()
        assert data["can_review"] is False
        fb = data["feedback"]
        assert isinstance(fb, dict)
        assert fb["rating"] == 3
        assert fb["comment"] == "Норм"

        # Список заказов — те же поля.
        listed = await shop_public_client.get(f"{PUBLIC_PREFIX}/my/orders")
        assert listed.status_code == 200, listed.text
        item = next(i for i in listed.json()["items"] if i["public_code"] == code)
        assert item["can_review"] is False
        fb_item = item["feedback"]
        assert isinstance(fb_item, dict)
        assert fb_item["rating"] == 3

    async def test_feedback_validation(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"fbv-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        product = await _product(shop_client, shop_id, "Латте")
        _ = await auth_customer(shop_public_client, slug)
        code, _ = await _order_done(
            shop_client, shop_public_client, slug, shop_id, _id(product, "product_id")
        )
        for bad in ({"rating": 0}, {"rating": 6}, {"rating": 5, "chips": ["junk"]}):
            resp = await shop_public_client.post(_feedback_url(slug, code), json=bad)
            assert resp.status_code == 422, (bad, resp.text)
        too_long: JsonValue = {"rating": 4, "comment": "x" * 1001}
        resp = await shop_public_client.post(_feedback_url(slug, code), json=too_long)
        assert resp.status_code == 422, resp.text

    async def test_reviews_feature_disabled(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """``features.reviews=false``: can_review погашен, рейтинг из снапшота убран."""
        slug = f"fbd-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        product = await _product(shop_client, shop_id, "Латте")
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop_id}", json={"features": {"reviews": False}}
        )
        assert resp.status_code == 200, resp.text

        _ = await auth_customer(shop_public_client, slug)
        code, _ = await _order_done(
            shop_client, shop_public_client, slug, shop_id, _id(product, "product_id")
        )
        detail = await shop_public_client.get(f"{PUBLIC_PREFIX}/my/orders/{code}")
        assert detail.json()["can_review"] is False

        snap = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        rating = snap.json()["rating"]
        assert rating == {"avg": None, "count": 0}
        assert snap.json()["features"]["reviews"] is False

    async def test_reviews_feed_and_snapshot_rating(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"fbl-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        product = await _product(shop_client, shop_id, "Латте")
        _ = await auth_customer(shop_public_client, slug)
        code, _ = await _order_done(
            shop_client, shop_public_client, slug, shop_id, _id(product, "product_id")
        )
        resp = await shop_public_client.post(
            _feedback_url(slug, code),
            json={"rating": 4, "chips": ["service"], "comment": "Вкусно"},
        )
        assert resp.status_code == 200, resp.text

        feed = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}/reviews")
        assert feed.status_code == 200, feed.text
        body = feed.json()
        assert body["count"] == 1
        assert body["avg_rating"] == 4.0
        item = body["items"][0]
        assert item["rating"] == 4
        assert item["customer_name"] == "Тест Отзывов"
        labels = item["chip_labels"]
        assert isinstance(labels, dict)
        assert labels["service"] == "Вежливый сервис"

        # Агрегат дошёл до снапшота — бейдж рейтинга на витрине.
        snap = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        rating = snap.json()["rating"]
        assert rating["count"] == 1
        assert rating["avg"] == 4.0

    async def test_review_name_never_leaks_phone(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """customer_name=телефон (UI-заказ без имени) → в ленте «Гость», не PII."""
        slug = f"fbp-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        product = await _product(shop_client, shop_id, "Латте")
        customer = await auth_customer(shop_public_client, slug)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json={
                "customer_name": str(customer["phone_e164"]),
                "delivery_type": "pickup",
                "items": [{"product_id": _id(product, "product_id"), "qty": 1}],
            },
        )
        assert resp.status_code == 200, resp.text
        code = str(resp.json()["public_code"])
        orders = await shop_client.get(f"{_SHOPS}/{shop_id}/orders")
        order_id = next(
            str(o["shop_order_id"])
            for o in orders.json()["items"]
            if o["public_code"] == code
        )
        url = f"{_SHOPS}/{shop_id}/orders/{order_id}/status"
        for status in ("accepted", "preparing", "done"):
            resp = await shop_client.post(url, params={"status": status})
            assert resp.status_code == 200, (status, resp.text)

        resp = await shop_public_client.post(
            _feedback_url(slug, code), json={"rating": 5}
        )
        assert resp.status_code == 200, resp.text
        feed = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}/reviews")
        assert feed.status_code == 200, feed.text
        item = feed.json()["items"][0]
        assert item["customer_name"] == ""
        assert str(customer["phone_e164"]) not in feed.text
