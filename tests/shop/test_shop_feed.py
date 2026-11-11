"""Лента витрины: полки, баннеры, фича-флаги, КБЖУ, «сообщить о появлении».

Продовый путь: REST `/shops/{id}/shelves|banners` → ребилд снапшота →
публичный GET `/public/storefront/{slug}`. Подписка на возврат товара идёт
через эмуляторную customer-авторизацию (customers.mdc).
"""

from __future__ import annotations

from httpx2 import AsyncClient

from apps.shop.models.back_in_stock import ShopBackInStock
from apps.shop.models.favorite import ShopFavorite
from core.types import JsonObject, JsonValue, parse_json_object
from tests.fixtures.shop import API_PREFIX, PUBLIC_PREFIX, auth_customer

_SHOPS = f"{API_PREFIX}/shops"


async def _published_shop(client: AsyncClient, slug: str) -> JsonObject:
    resp = await client.post(
        _SHOPS, json={"slug": slug, "name": f"Feed {slug}", "kind": "cafe", "lat": 55.7512, "lng": 37.6184}
    )
    assert resp.status_code == 200, resp.text
    shop = parse_json_object(resp.text, "shop")
    resp = await client.post(f"{_SHOPS}/{_id(shop, 'shop_id')}/publish")
    assert resp.status_code == 200, resp.text
    return shop


async def _product(
    client: AsyncClient, shop_id: str, name: str, **kw: JsonValue
) -> JsonObject:
    resp = await client.post(
        f"{_SHOPS}/{shop_id}/products",
        json={"name": name, "price_minor": 25000, **kw},
    )
    assert resp.status_code == 200, resp.text
    return parse_json_object(resp.text, "product")


async def _snapshot(client: AsyncClient, slug: str) -> JsonObject:
    resp = await client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
    assert resp.status_code == 200, resp.text
    return parse_json_object(resp.text, "storefront snapshot")


def _id(obj: JsonObject, key: str) -> str:
    value = obj[key]
    assert isinstance(value, str)
    return value


def _rows(obj: JsonObject, key: str) -> list[JsonObject]:
    raw = obj[key]
    assert isinstance(raw, list)
    return [x for x in raw if isinstance(x, dict)]


def _str_rows(obj: JsonObject, key: str) -> list[str]:
    raw = obj[key]
    assert isinstance(raw, list)
    return [x for x in raw if isinstance(x, str)]


class TestShelves:
    async def test_shelf_crud_and_reorder(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"shf-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        hits = await shop_client.post(
            f"{_SHOPS}/{shop_id}/shelves", json={"kind": "hits", "title": "Хиты"}
        )
        assert hits.status_code == 200, hits.text
        manual = await shop_client.post(
            f"{_SHOPS}/{shop_id}/shelves",
            json={"kind": "manual", "title": "Подборка", "layout": "grid"},
        )
        assert manual.status_code == 200, manual.text
        first = parse_json_object(hits.text, "shelf")
        second = parse_json_object(manual.text, "shelf")

        listed = await shop_client.get(f"{_SHOPS}/{shop_id}/shelves")
        listed_ids = [
            _id(s, "shop_shelf_id")
            for s in _rows(parse_json_object(listed.text, "shelves"), "items")
        ]
        assert listed_ids == [
            _id(first, "shop_shelf_id"),
            _id(second, "shop_shelf_id"),
        ]

        reordered = await shop_client.put(
            f"{_SHOPS}/{shop_id}/shelves/order",
            json={
                "shelf_ids": [
                    _id(second, "shop_shelf_id"),
                    _id(first, "shop_shelf_id"),
                ]
            },
        )
        assert reordered.status_code == 200, reordered.text
        listed = await shop_client.get(f"{_SHOPS}/{shop_id}/shelves")
        listed_ids = [
            _id(s, "shop_shelf_id")
            for s in _rows(parse_json_object(listed.text, "shelves"), "items")
        ]
        assert listed_ids == [
            _id(second, "shop_shelf_id"),
            _id(first, "shop_shelf_id"),
        ]

        patched = await shop_client.patch(
            f"{_SHOPS}/{shop_id}/shelves/{_id(first, 'shop_shelf_id')}",
            json={"title": "Популярное", "is_active": False},
        )
        assert patched.status_code == 200, patched.text
        assert parse_json_object(patched.text, "shelf")["title"] == "Популярное"

        snap = await _snapshot(shop_public_client, slug)
        shelf_ids = {_id(s, "id") for s in _rows(snap, "shelves")}
        assert _id(second, "shop_shelf_id") in shelf_ids
        assert _id(first, "shop_shelf_id") not in shelf_ids, (
            "inactive shelf must be hidden"
        )

        removed = await shop_client.delete(
            f"{_SHOPS}/{shop_id}/shelves/{_id(second, 'shop_shelf_id')}"
        )
        assert removed.status_code == 200, removed.text
        snap = await _snapshot(shop_public_client, slug)
        assert _rows(snap, "shelves") == []

    async def test_manual_shelf_resolves_products(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"mshf-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        latte = await _product(shop_client, shop_id, "Латте")
        _ = await _product(shop_client, shop_id, "Раф")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/shelves",
            json={
                "kind": "manual",
                "product_ids": [_id(latte, "product_id")],
            },
        )
        assert resp.status_code == 200, resp.text
        snap = await _snapshot(shop_public_client, slug)
        shelf = next(s for s in _rows(snap, "shelves") if s["kind"] == "manual")
        assert _str_rows(shelf, "product_ids") == [_id(latte, "product_id")]

    async def test_new_shelf_resolves_recent_products(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"nshf-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        latte = await _product(shop_client, shop_id, "Латте")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/shelves", json={"kind": "new"}
        )
        assert resp.status_code == 200, resp.text
        snap = await _snapshot(shop_public_client, slug)
        shelf = next(s for s in _rows(snap, "shelves") if s["kind"] == "new")
        assert _id(latte, "product_id") in _str_rows(shelf, "product_ids")

    async def test_comeback_shelf_resolves_unavailable_products(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Полка «Скоро вернётся» — позиции, ушедшие из наличия."""
        slug = f"cshf-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        cake = await _product(shop_client, shop_id, "Тирамису")
        pid = _id(cake, "product_id")
        _ = await _product(shop_client, shop_id, "Латте")
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop_id}/products/{pid}", json={"is_available": False}
        )
        assert resp.status_code == 200, resp.text
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/shelves", json={"kind": "comeback"}
        )
        assert resp.status_code == 200, resp.text
        snap = await _snapshot(shop_public_client, slug)
        shelf = next(s for s in _rows(snap, "shelves") if s["kind"] == "comeback")
        assert _str_rows(shelf, "product_ids") == [pid]


class TestBanners:
    async def test_banner_crud_and_snapshot(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"bnr-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        product = await _product(shop_client, shop_id, "Сет")
        product_id = _id(product, "product_id")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/banners",
            json={
                "title": "Сезонное",
                "subtitle": "Только до воскресенья",
                "link": f"product:{product_id}",
            },
        )
        assert resp.status_code == 200, resp.text
        banner = parse_json_object(resp.text, "banner")
        assert banner["link"] == f"product:{product_id}"

        second = await shop_client.post(
            f"{_SHOPS}/{shop_id}/banners", json={"title": "Второй"}
        )
        assert second.status_code == 200, second.text
        second_banner = parse_json_object(second.text, "banner")
        reordered = await shop_client.put(
            f"{_SHOPS}/{shop_id}/banners/order",
            json={
                "banner_ids": [
                    _id(second_banner, "shop_banner_id"),
                    _id(banner, "shop_banner_id"),
                ]
            },
        )
        assert reordered.status_code == 200, reordered.text

        snap = await _snapshot(shop_public_client, slug)
        snap_banners = _rows(snap, "banners")
        assert [_id(b, "id") for b in snap_banners] == [
            _id(second_banner, "shop_banner_id"),
            _id(banner, "shop_banner_id"),
        ]
        assert snap_banners[1]["link"] == f"product:{product_id}"

        patched = await shop_client.patch(
            f"{_SHOPS}/{shop_id}/banners/{_id(banner, 'shop_banner_id')}",
            json={"is_active": False},
        )
        assert patched.status_code == 200, patched.text
        snap = await _snapshot(shop_public_client, slug)
        assert [_id(b, "id") for b in _rows(snap, "banners")] == [
            _id(second_banner, "shop_banner_id")
        ]

    async def test_feed_html_renders_banners_and_shelves(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"fhtml-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        _ = await _product(shop_client, shop_id, "Латте")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/shelves",
            json={"kind": "new", "title": "Новинки недели"},
        )
        assert resp.status_code == 200, resp.text
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/banners", json={"title": "Акция дня"}
        )
        assert resp.status_code == 200, resp.text
        html = await shop_public_client.get(f"{PUBLIC_PREFIX}/s/{slug}")
        assert html.status_code == 200
        assert "Акция дня" in html.text
        assert "Новинки недели" in html.text


class TestFeaturesAndNutrition:
    async def test_features_roundtrip(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"ft-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop_id}",
            json={"features": {"nutrition": True, "back_in_stock": True}},
        )
        assert resp.status_code == 200, resp.text
        features = parse_json_object(resp.text, "shop")["features"]
        assert isinstance(features, dict)
        assert features["nutrition"] is True
        assert features["back_in_stock"] is True
        rejected = await shop_client.patch(
            f"{_SHOPS}/{shop_id}",
            json={"features": {"junk": True}},
        )
        assert rejected.status_code == 422, "неизвестный флаг — fail-closed 422"
        snap = await _snapshot(shop_public_client, slug)
        snap_features = snap["features"]
        assert isinstance(snap_features, dict)
        assert snap_features["nutrition"] is True

    async def test_nutrition_in_snapshot_and_product_payload(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"nut-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        product = await _product(
            shop_client,
            shop_id,
            "Боул",
            nutrition={
                "kcal": 420.0,
                "protein_g": 18.0,
                "fat_g": 12.0,
                "carb_g": 55.0,
            },
        )
        product_id = _id(product, "product_id")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/modifier-groups",
            json={"name": "Топпинг", "selection_mode": "multi"},
        )
        assert resp.status_code == 200, resp.text
        group = parse_json_object(resp.text, "group")
        gid = _id(group, "shop_modifier_group_id")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/modifier-groups/{gid}/options",
            json={
                "name": "Авокадо",
                "price_minor": 9000,
                "nutrition_delta": {"kcal": 80.0, "fat_g": 7.0},
            },
        )
        assert resp.status_code == 200, resp.text
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/products/{product_id}/modifier-groups/{gid}",
            json={},
        )
        assert resp.status_code == 200, resp.text

        snap = await _snapshot(shop_public_client, slug)
        p = next(x for x in _rows(snap, "products") if x["id"] == product_id)
        nutrition = p["nutrition"]
        assert isinstance(nutrition, dict)
        assert nutrition["kcal"] == 420.0
        groups = _rows(p, "modifier_groups")
        options = _rows(groups[0], "options")
        assert options[0]["nutrition_delta"] == {"kcal": 80.0, "fat_g": 7.0}
        assert options[0]["photo_file_id"] is None

    async def test_unavailable_product_in_snapshot_for_notify(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Недоступная позиция остаётся в снапшоте — витрина рисует «скоро вернётся»."""
        slug = f"unav-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        product = await _product(shop_client, shop_id, "Тирамису")
        product_id = _id(product, "product_id")
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop_id}/products/{product_id}",
            json={"is_available": False},
        )
        assert resp.status_code == 200, resp.text
        snap = await _snapshot(shop_public_client, slug)
        p = next(x for x in _rows(snap, "products") if x["id"] == product_id)
        assert p["is_available"] is False


class TestNotifyBack:
    async def test_anonymous_notify_rejected(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"nan-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        product = await _product(shop_client, _id(shop, "shop_id"), "Тирамису")
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/notify-back",
            json={"product_id": _id(product, "product_id")},
        )
        assert resp.status_code in (401, 403), resp.text

    async def test_customer_subscribes_to_unavailable_product(
        self,
        shop_client: AsyncClient,
        shop_public_client: AsyncClient,
        unique_id: str,
    ) -> None:
        slug = f"nb-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        product = await _product(shop_client, shop_id, "Тирамису")
        pid = _id(product, "product_id")
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop_id}/products/{pid}", json={"is_available": False}
        )
        assert resp.status_code == 200, resp.text

        customer = await auth_customer(shop_public_client, slug)
        customer_id = str(customer["customer_id"])
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/notify-back",
            json={"product_id": pid},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["subscribed"] is True

        sub = await ShopBackInStock.find_by_product_and_customer(pid, customer_id)
        assert sub is not None
        assert sub.notified_at is None

        # Повторная подписка идемпотентна — не плодит строки.
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/notify-back",
            json={"product_id": pid},
        )
        assert resp.status_code == 200, resp.text
        pending = await ShopBackInStock.list_pending_by_product(pid)
        assert len(pending) == 1


class TestPersonal:
    """`GET /storefront/{slug}/personal`: «как всегда» + подписки покупателя."""

    async def test_anonymous_personal_rejected(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"pan-{unique_id[:8]}"
        _ = await _published_shop(shop_client, slug)
        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/{slug}/personal"
        )
        assert resp.status_code in (401, 403), resp.text

    async def test_personal_usual_and_back_in_stock(
        self,
        shop_client: AsyncClient,
        shop_public_client: AsyncClient,
        unique_id: str,
    ) -> None:
        slug = f"per-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        latte = await _product(shop_client, shop_id, "Латте")
        latte_id = _id(latte, "product_id")
        gone = await _product(shop_client, shop_id, "Тирамису")
        gone_id = _id(gone, "product_id")
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop_id}/products/{gone_id}",
            json={"is_available": False},
        )
        assert resp.status_code == 200, resp.text
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/shelves",
            json={"kind": "usual", "title": "Как всегда"},
        )
        assert resp.status_code == 200, resp.text

        _ = await auth_customer(shop_public_client, slug)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json={
                "customer_name": "Тест Персональный",
                "delivery_type": "pickup",
                "items": [{"product_id": latte_id, "qty": 2}],
            },
        )
        assert resp.status_code == 200, resp.text
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/notify-back",
            json={"product_id": gone_id},
        )
        assert resp.status_code == 200, resp.text

        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/{slug}/personal"
        )
        assert resp.status_code == 200, resp.text
        body = parse_json_object(resp.text, "personal")
        assert _str_rows(body, "back_in_stock_ids") == [gone_id]
        usual = _rows(body, "usual")
        assert [u["product_id"] for u in usual] == [latte_id]
        assert usual[0]["count"] == 2

        # Повторный заказ суммирует штуки — позиция остаётся первой.
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json={
                "customer_name": "Тест Персональный",
                "delivery_type": "pickup",
                "items": [{"product_id": latte_id, "qty": 1}],
            },
        )
        assert resp.status_code == 200, resp.text
        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/{slug}/personal"
        )
        assert resp.status_code == 200, resp.text
        usual = _rows(parse_json_object(resp.text, "personal"), "usual")
        assert usual[0]["product_id"] == latte_id
        assert usual[0]["count"] == 3


class TestFavorites:
    """Избранное покупателя: сердечко, ``/personal``, полка ``favorites``."""

    async def test_anonymous_favorite_rejected(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"fan-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        product = await _product(shop_client, _id(shop, "shop_id"), "Латте")
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/favorites",
            json={"product_id": _id(product, "product_id"), "favorite": True},
        )
        assert resp.status_code in (401, 403), resp.text

    async def test_favorite_set_unset_idempotent(
        self,
        shop_client: AsyncClient,
        shop_public_client: AsyncClient,
        unique_id: str,
    ) -> None:
        slug = f"fav-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        latte = await _product(shop_client, shop_id, "Латте")
        latte_id = _id(latte, "product_id")
        raf = await _product(shop_client, shop_id, "Раф")
        raf_id = _id(raf, "product_id")

        customer = await auth_customer(shop_public_client, slug)
        customer_id = str(customer["customer_id"])
        fav_url = f"{PUBLIC_PREFIX}/storefront/{slug}/favorites"

        resp = await shop_public_client.post(
            fav_url, json={"product_id": latte_id, "favorite": True}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["favorite"] is True
        resp = await shop_public_client.post(
            fav_url, json={"product_id": raf_id, "favorite": True}
        )
        assert resp.status_code == 200, resp.text

        # Повторный set идемпотентен — одна строка на пару.
        resp = await shop_public_client.post(
            fav_url, json={"product_id": latte_id, "favorite": True}
        )
        assert resp.status_code == 200, resp.text
        favorites = await ShopFavorite.list_by_shop_customer_by_created_desc(
            shop_id, customer_id
        )
        assert [f.product_id for f in favorites] == [raf_id, latte_id]

        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/{slug}/personal"
        )
        assert resp.status_code == 200, resp.text
        body = parse_json_object(resp.text, "personal")
        assert _str_rows(body, "favorite_ids") == [raf_id, latte_id]

        resp = await shop_public_client.post(
            fav_url, json={"product_id": latte_id, "favorite": False}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["favorite"] is False
        # Повторный unset тоже идемпотентен.
        resp = await shop_public_client.post(
            fav_url, json={"product_id": latte_id, "favorite": False}
        )
        assert resp.status_code == 200, resp.text
        favorites = await ShopFavorite.list_by_shop_customer_by_created_desc(
            shop_id, customer_id
        )
        assert [f.product_id for f in favorites] == [raf_id]

    async def test_favorite_foreign_product_rejected(
        self,
        shop_client: AsyncClient,
        shop_public_client: AsyncClient,
        unique_id: str,
    ) -> None:
        """Сердечко на товар чужой витрины — 404, строка не создаётся."""
        slug = f"fx-{unique_id[:8]}"
        _ = await _published_shop(shop_client, slug)
        other = await _published_shop(shop_client, f"fy-{unique_id[:8]}")
        foreign = await _product(shop_client, _id(other, "shop_id"), "Чужой")
        foreign_id = _id(foreign, "product_id")

        _ = await auth_customer(shop_public_client, slug)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/favorites",
            json={"product_id": foreign_id, "favorite": True},
        )
        assert resp.status_code == 404, resp.text
        assert (
            await ShopFavorite.find_by_product_and_customer(foreign_id, "x") is None
        )

    async def test_favorites_shelf_anonymous_empty(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Полка ``favorites`` в анонимном снапшоте — без id'шников."""
        slug = f"fsh-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = _id(shop, "shop_id")
        _ = await _product(shop_client, shop_id, "Латте")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/shelves",
            json={"kind": "favorites", "title": "Избранное"},
        )
        assert resp.status_code == 200, resp.text
        snap = await _snapshot(shop_public_client, slug)
        shelf = next(s for s in _rows(snap, "shelves") if s["kind"] == "favorites")
        assert _str_rows(shelf, "product_ids") == []
