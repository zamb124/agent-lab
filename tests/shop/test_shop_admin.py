"""REST-тесты Shop Admin API: CRUD магазина, каталога, изоляция компаний.

`shop_client` — владелец `system`; `shop_client_company2` — чужая компания.
Продовый путь: реальный Postgres (platform_shop), настоящий AuthMiddleware.
"""

from __future__ import annotations

from typing import Any

from httpx2 import AsyncClient

from tests.fixtures.shop import API_PREFIX

_SHOPS = f"{API_PREFIX}/shops"


async def _make_shop(
    client: AsyncClient, slug: str, **overrides: Any
) -> dict[str, Any]:
    payload = {"slug": slug, "name": f"Shop {slug}", "kind": "restaurant", **overrides}
    resp = await client.post(_SHOPS, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _make_category(client: AsyncClient, shop_id: str, name: str) -> dict[str, Any]:
    resp = await client.post(f"{_SHOPS}/{shop_id}/categories", json={"name": name})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _make_product(
    client: AsyncClient, shop_id: str, name: str, price: int, **overrides: Any
) -> dict[str, Any]:
    resp = await client.post(
        f"{_SHOPS}/{shop_id}/products",
        json={"name": name, "price_minor": price, **overrides},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestShopCrud:
    async def test_create_list_get_shop(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"test-{unique_id[:8]}"
        created = await _make_shop(shop_client, slug)
        assert created["slug"] == slug
        assert created["status"] == "draft"
        assert created["storefront_url"].startswith(f"https://{slug}.")
        listed = (await shop_client.get(_SHOPS)).json()
        assert any(s["shop_id"] == created["shop_id"] for s in listed["items"])
        got = (await shop_client.get(f"{_SHOPS}/{created['shop_id']}")).json()
        assert got["name"] == f"Shop {slug}"

    async def test_slug_conflict(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"dup-{unique_id[:8]}"
        await _make_shop(shop_client, slug)
        resp = await shop_client.post(
            _SHOPS, json={"slug": slug, "name": "Other"}
        )
        assert resp.status_code == 409

    async def test_slug_reserved_rejected(self, shop_client: AsyncClient) -> None:
        for slug in ("grafana", "www", "api", "shop"):
            resp = await shop_client.post(
                _SHOPS, json={"slug": slug, "name": "Bad"}
            )
            assert resp.status_code == 409, slug

    async def test_slug_invalid_rejected(self, shop_client: AsyncClient) -> None:
        for slug in ("AB", "UP Case", "up_case", "-lead", "trail-", "a" * 41, "с луг"):
            resp = await shop_client.post(
                _SHOPS, json={"slug": slug, "name": "Bad"}
            )
            assert resp.status_code in (409, 422), slug

    async def test_update_shop_fields(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        shop = await _make_shop(shop_client, f"upd-{unique_id[:8]}")
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}",
            json={
                "name": "Новое имя",
                "description": "Описание",
                "phone": "+79990001122",
                "city": "Москва",
                "delivery_fee_minor": 19900,
                "min_order_minor": 50000,
                "theme": {"accent_color": "#00ff88", "preset": "grid"},
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "Новое имя"
        assert body["delivery_fee_minor"] == 19900
        assert body["theme"]["accent_color"] == "#00ff88"

    async def test_publish_and_suspend(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        shop = await _make_shop(shop_client, f"pub-{unique_id[:8]}")
        resp = await shop_client.post(f"{_SHOPS}/{shop['shop_id']}/publish")
        assert resp.status_code == 200
        assert resp.json()["status"] == "published"
        resp = await shop_client.post(f"{_SHOPS}/{shop['shop_id']}/suspend")
        assert resp.json()["status"] == "suspended"

    async def test_delete_shop_excluded_from_list(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        shop = await _make_shop(shop_client, f"del-{unique_id[:8]}")
        resp = await shop_client.delete(f"{_SHOPS}/{shop['shop_id']}")
        assert resp.status_code == 200
        listed = (await shop_client.get(_SHOPS)).json()
        assert all(s["shop_id"] != shop["shop_id"] for s in listed["items"])
        resp = await shop_client.get(f"{_SHOPS}/{shop['shop_id']}")
        assert resp.status_code == 404


class TestTenantIsolation:
    async def test_company2_cannot_see_system_shops(
        self,
        shop_client: AsyncClient,
        shop_client_company2: AsyncClient,
        unique_id: str,
    ) -> None:
        shop = await _make_shop(shop_client, f"iso-{unique_id[:8]}")
        resp = await shop_client_company2.get(f"{_SHOPS}/{shop['shop_id']}")
        assert resp.status_code == 404
        listed = (await shop_client_company2.get(_SHOPS)).json()
        assert all(s["shop_id"] != shop["shop_id"] for s in listed["items"])
        for method, url in (
            ("patch", f"{_SHOPS}/{shop['shop_id']}"),
            ("delete", f"{_SHOPS}/{shop['shop_id']}"),
            ("post", f"{_SHOPS}/{shop['shop_id']}/publish"),
        ):
            resp = await shop_client_company2.request(
                method, url, json={"name": "hack"} if method == "patch" else None
            )
            assert resp.status_code == 404, method

    async def test_anonymous_cannot_use_admin_api(
        self, shop_public_client: AsyncClient
    ) -> None:
        resp = await shop_public_client.get(_SHOPS)
        assert resp.status_code in (401, 403, 302)


class TestCatalog:
    async def test_category_crud_and_sort(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        shop = await _make_shop(shop_client, f"cat-{unique_id[:8]}")
        first = await _make_category(shop_client, shop["shop_id"], "Пицца")
        second = await _make_category(shop_client, shop["shop_id"], "Напитки")
        assert second["sort"] > first["sort"]
        listed = (
            await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/categories")
        ).json()
        assert [c["name"] for c in listed["items"]] == ["Пицца", "Напитки"]
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}/categories/{first['shop_category_id']}",
            json={"name": "Пицца итальянская", "is_active": False},
        )
        assert resp.json()["is_active"] is False
        resp = await shop_client.delete(
            f"{_SHOPS}/{shop['shop_id']}/categories/{first['shop_category_id']}"
        )
        assert resp.status_code == 200

    async def test_product_crud(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        shop = await _make_shop(shop_client, f"prod-{unique_id[:8]}")
        cat = await _make_category(shop_client, shop["shop_id"], "Пицца")
        product = await _make_product(
            shop_client,
            shop["shop_id"],
            "Маргарита",
            55000,
            category_id=cat["shop_category_id"],
            description="Томат, моцарелла, базилик",
            portion="450 г",
            badges=["hit", "vegan"],
        )
        assert product["category_id"] == cat["shop_category_id"]
        assert product["portion"] == "450 г"
        assert product["badges"] == ["hit", "vegan"]
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}/products/{product['shop_product_id']}",
            json={
                "price_minor": 59000,
                "is_available": False,
                "portion": "32 см",
                "badges": ["spicy"],
            },
        )
        body = resp.json()
        assert body["price_minor"] == 59000
        assert body["portion"] == "32 см"
        assert body["badges"] == ["spicy"]
        assert body["is_available"] is False
        bad = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}/products/{product['shop_product_id']}",
            json={"badges": ["bogus"]},
        )
        assert bad.status_code == 404

    async def test_custom_badges_dictionary(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """Собственный набор меток: новая метка через shop/update, применение
        к товару, удаление используемой метки запрещено конфликтом."""
        shop = await _make_shop(shop_client, f"bdgd-{unique_id[:8]}")
        defaults = [b["key"] for b in shop["badges"]]
        assert defaults == ["hit", "new", "spicy", "vegan", "chef"]
        assert shop["badges"][0]["icon_path"].startswith("M")
        def wire(badges: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return [{"key": b["key"], "label": b["label"], "icon": b["icon"]} for b in badges]

        custom = wire(shop["badges"]) + [{"label": "Без лактозы", "icon": "eco"}]
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}", json={"badges": custom}
        )
        assert resp.status_code == 200, resp.text
        updated = resp.json()["badges"]
        assert updated[-1]["label"] == "Без лактозы"
        lactose_free = updated[-1]["key"]
        product = await _make_product(
            shop_client, shop["shop_id"], "Салат", 30000, badges=[lactose_free]
        )
        assert product["badges"] == [lactose_free]
        conflict = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}",
            json={"badges": [b for b in custom if b["label"] != "Без лактозы"]},
        )
        assert conflict.status_code == 409
        resp = await shop_client.delete(
            f"{_SHOPS}/{shop['shop_id']}/products/{product['shop_product_id']}"
        )
        assert resp.status_code == 200

    async def test_products_reorder_within_list(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """products/reorder переставляет позиции: ids получают сорт. значения
        в новом порядке, посторонние товары не затрагиваются."""
        shop = await _make_shop(shop_client, f"reo-{unique_id[:8]}")
        cat = await _make_category(shop_client, shop["shop_id"], "Пицца")
        other_cat = await _make_category(shop_client, shop["shop_id"], "Напитки")
        a = await _make_product(shop_client, shop["shop_id"], "A", 100, category_id=cat["shop_category_id"])
        b = await _make_product(shop_client, shop["shop_id"], "B", 200, category_id=cat["shop_category_id"])
        c = await _make_product(shop_client, shop["shop_id"], "C", 300, category_id=cat["shop_category_id"])
        other = await _make_product(shop_client, shop["shop_id"], "Z", 400, category_id=other_cat["shop_category_id"])
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/products/reorder",
            json={"product_ids": [c["shop_product_id"], a["shop_product_id"], b["shop_product_id"]]},
        )
        assert resp.status_code == 200, resp.text
        listed = (await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/products")).json()["items"]
        ids = [p["shop_product_id"] for p in listed]
        assert ids.index(c["shop_product_id"]) < ids.index(a["shop_product_id"]) < ids.index(b["shop_product_id"])
        sorts = {p["shop_product_id"]: p["sort"] for p in listed}
        assert sorts[other["shop_product_id"]] == other["sort"]
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/products/reorder",
            json={"product_ids": [a["shop_product_id"], "nonexistent"]},
        )
        assert resp.status_code == 404

    async def test_categories_reorder(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """categories/reorder переставляет категории — порядок табов витрины."""
        shop = await _make_shop(shop_client, f"creo-{unique_id[:8]}")
        a = await _make_category(shop_client, shop["shop_id"], "A")
        b = await _make_category(shop_client, shop["shop_id"], "B")
        c = await _make_category(shop_client, shop["shop_id"], "C")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/categories/reorder",
            json={"category_ids": [c["shop_category_id"], a["shop_category_id"], b["shop_category_id"]]},
        )
        assert resp.status_code == 200, resp.text
        listed = (await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/categories")).json()["items"]
        assert [x["shop_category_id"] for x in listed] == [
            c["shop_category_id"],
            a["shop_category_id"],
            b["shop_category_id"],
        ]
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/categories/reorder",
            json={"category_ids": [a["shop_category_id"], "nonexistent"]},
        )
        assert resp.status_code == 404

    async def test_product_foreign_category_rejected(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        shop_a = await _make_shop(shop_client, f"a-{unique_id[:8]}")
        shop_b = await _make_shop(shop_client, f"b-{unique_id[:8]}")
        cat_b = await _make_category(shop_client, shop_b["shop_id"], "Чужая")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_a['shop_id']}/products",
            json={
                "name": "X",
                "price_minor": 100,
                "category_id": cat_b["shop_category_id"],
            },
        )
        assert resp.status_code == 404

    async def test_catalog_isolation(
        self,
        shop_client: AsyncClient,
        shop_client_company2: AsyncClient,
        unique_id: str,
    ) -> None:
        shop = await _make_shop(shop_client, f"ciso-{unique_id[:8]}")
        for url in (
            f"{_SHOPS}/{shop['shop_id']}/categories",
            f"{_SHOPS}/{shop['shop_id']}/products",
            f"{_SHOPS}/{shop['shop_id']}/orders",
        ):
            resp = await shop_client_company2.get(url)
            assert resp.status_code == 404, url

    async def test_products_import_bulk(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """Импорт списка блюд одной командой: сортировка, категория, итоговый список."""
        shop = await _make_shop(shop_client, f"imp-{unique_id[:8]}")
        category = await _make_category(shop_client, shop["shop_id"], "Горячее")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/products/import",
            json={
                "category_id": category["shop_category_id"],
                "items": [
                    {"name": "Борщ", "price_minor": 35000, "description": "Со сметаной"},
                    {"name": "Пюре с котлетой", "price_minor": 42000},
                    {"name": "Компот", "price_minor": 12000},
                ],
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["created"] == 3

        listed = await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/products")
        assert listed.status_code == 200
        items = listed.json()["items"]
        assert len(items) == 3
        assert [p["name"] for p in items] == [
            "Борщ",
            "Пюре с котлетой",
            "Компот",
        ]
        assert all(p["category_id"] == category["shop_category_id"] for p in items)
        assert items[0]["description"] == "Со сметаной"
        assert [p["sort"] for p in items] == sorted(p["sort"] for p in items)

    async def test_products_import_foreign_category_rejected(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        shop_a = await _make_shop(shop_client, f"impa-{unique_id[:8]}")
        shop_b = await _make_shop(shop_client, f"impb-{unique_id[:8]}")
        cat_b = await _make_category(shop_client, shop_b["shop_id"], "Чужая")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_a['shop_id']}/products/import",
            json={
                "category_id": cat_b["shop_category_id"],
                "items": [{"name": "X", "price_minor": 100}],
            },
        )
        assert resp.status_code == 404

    async def test_products_import_empty_rejected(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        shop = await _make_shop(shop_client, f"impe-{unique_id[:8]}")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/products/import",
            json={"items": []},
        )
        assert resp.status_code == 422
