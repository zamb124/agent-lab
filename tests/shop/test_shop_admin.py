"""REST-тесты Shop Admin API: CRUD магазина, каталога, изоляция компаний.

`shop_client` — владелец `system`; `shop_client_company2` — чужая компания.
Продовый путь: реальный Postgres (platform_shop), настоящий AuthMiddleware.
"""

from __future__ import annotations

from typing import Any

from httpx2 import AsyncClient

from tests.fixtures.shop import (
    API_PREFIX,
    add_menu_item,
    make_active_menu_item,
    make_product,
    make_shop,
)

_SHOPS = f"{API_PREFIX}/shops"


async def _make_menu(client: AsyncClient, shop_id: str, name: str) -> dict[str, Any]:
    resp = await client.post(f"{_SHOPS}/{shop_id}/menus", json={"name": name})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _make_section(
    client: AsyncClient, shop_id: str, shop_menu_id: str, name: str, **overrides: Any
) -> dict[str, Any]:
    resp = await client.post(
        f"{_SHOPS}/{shop_id}/menus/{shop_menu_id}/sections", json={"name": name, **overrides}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _menus(client: AsyncClient, shop_id: str) -> list[dict[str, Any]]:
    resp = await client.get(f"{_SHOPS}/{shop_id}/menus")
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


class TestShopCrud:
    async def test_create_list_get_shop(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"test-{unique_id[:8]}"
        created = await make_shop(shop_client, slug)
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
        await make_shop(shop_client, slug)
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
        shop = await make_shop(shop_client, f"upd-{unique_id[:8]}")
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
        shop = await make_shop(shop_client, f"pub-{unique_id[:8]}")
        resp = await shop_client.post(f"{_SHOPS}/{shop['shop_id']}/publish")
        assert resp.status_code == 200
        assert resp.json()["status"] == "published"
        resp = await shop_client.post(f"{_SHOPS}/{shop['shop_id']}/suspend")
        assert resp.json()["status"] == "suspended"

    async def test_delete_shop_excluded_from_list(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        shop = await make_shop(shop_client, f"del-{unique_id[:8]}")
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
        shop = await make_shop(shop_client, f"iso-{unique_id[:8]}")
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
    async def test_product_crud(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """Блюдо каталога: выход measure/measure_unit, метки, patch и неизвестная метка."""
        shop = await make_shop(shop_client, f"prod-{unique_id[:8]}")
        product = await make_product(
            shop_client,
            shop["shop_id"],
            "Маргарита",
            55000,
            description="Томат, моцарелла, базилик",
            measure=450,
            badges=["hit", "vegan"],
        )
        assert (
            product["measure"],
            product["measure_unit"],
            product["badges"],
            product["is_available"],
            product["ai_unverified"],
        ) == (450, "g", ["hit", "vegan"], True, False)
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}/products/{product['shop_product_id']}",
            json={
                "price_minor": 59000,
                "is_available": False,
                "measure": 1,
                "measure_unit": "pcs",
                "badges": ["spicy"],
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert (
            body["price_minor"],
            body["measure"],
            body["measure_unit"],
            body["badges"],
            body["is_available"],
        ) == (59000, 1, "pcs", ["spicy"], False)
        listed = (await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/products")).json()["items"]
        assert [(p["shop_product_id"], p["measure_unit"]) for p in listed] == [
            (product["shop_product_id"], "pcs")
        ]
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
        shop = await make_shop(shop_client, f"bdgd-{unique_id[:8]}")
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
        product = await make_product(
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
        shop = await make_shop(shop_client, f"reo-{unique_id[:8]}")
        a = await make_product(shop_client, shop["shop_id"], "A", 100)
        b = await make_product(shop_client, shop["shop_id"], "B", 200)
        c = await make_product(shop_client, shop["shop_id"], "C", 300)
        other = await make_product(shop_client, shop["shop_id"], "Z", 400)
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

    async def test_product_in_menu_cannot_be_removed(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """Блюдо с позицией меню не удаляется (product_in_menu); удаление меню
        оставляет блюдо в каталоге, после чего блюдо удаляется."""
        shop = await make_shop(shop_client, f"pim-{unique_id[:8]}")
        product = await make_product(shop_client, shop["shop_id"], "Борщ", 35000)
        menu, _, _ = await make_active_menu_item(
            shop_client, shop["shop_id"], product["shop_product_id"]
        )
        url = f"{_SHOPS}/{shop['shop_id']}/products/{product['shop_product_id']}"
        resp = await shop_client.delete(url)
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "product_in_menu"
        resp = await shop_client.delete(f"{_SHOPS}/{shop['shop_id']}/menus/{menu['shop_menu_id']}")
        assert resp.status_code == 200, resp.text
        assert await _menus(shop_client, shop["shop_id"]) == []
        listed = (await shop_client.get(f"{_SHOPS}/{shop['shop_id']}/products")).json()["items"]
        assert [p["shop_product_id"] for p in listed] == [product["shop_product_id"]]
        resp = await shop_client.delete(url)
        assert resp.status_code == 200, resp.text

    async def test_catalog_isolation(
        self,
        shop_client: AsyncClient,
        shop_client_company2: AsyncClient,
        unique_id: str,
    ) -> None:
        shop = await make_shop(shop_client, f"ciso-{unique_id[:8]}")
        for url in (
            f"{_SHOPS}/{shop['shop_id']}/menus",
            f"{_SHOPS}/{shop['shop_id']}/products",
            f"{_SHOPS}/{shop['shop_id']}/orders",
        ):
            resp = await shop_client_company2.get(url)
            assert resp.status_code == 404, url


class TestMenus:
    async def test_menu_section_item_activate_list(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """Меню создаётся черновиком; раздел и позиция; activate; list отдаёт дерево."""
        shop = await make_shop(shop_client, f"menu-{unique_id[:8]}")
        shop_id = shop["shop_id"]
        product = await make_product(shop_client, shop_id, "Маргарита", 50000)
        menu = await _make_menu(shop_client, shop_id, "Основное")
        assert (menu["name"], menu["status"], menu["sections"], menu["items"]) == (
            "Основное",
            "draft",
            [],
            [],
        )
        menu_id = menu["shop_menu_id"]
        section = await _make_section(shop_client, shop_id, menu_id, "Пицца")
        assert (section["shop_menu_id"], section["name"], section["parent_id"]) == (
            menu_id,
            "Пицца",
            None,
        )
        item = await add_menu_item(
            shop_client,
            shop_id,
            menu_id,
            section["shop_menu_section_id"],
            product["shop_product_id"],
            price_minor_override=45000,
        )
        assert (
            item["shop_menu_id"],
            item["shop_menu_section_id"],
            item["shop_product_id"],
            item["price_minor_override"],
            item["effective_price_minor"],
            item["is_available"],
        ) == (menu_id, section["shop_menu_section_id"], product["shop_product_id"], 45000, 45000, True)
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/menus/{menu_id}/status", json={"status": "active"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "active"
        listed = await _menus(shop_client, shop_id)
        assert [(m["shop_menu_id"], m["status"]) for m in listed] == [(menu_id, "active")]
        assert [s["shop_menu_section_id"] for s in listed[0]["sections"]] == [
            section["shop_menu_section_id"]
        ]
        assert [i["shop_menu_item_id"] for i in listed[0]["items"]] == [item["shop_menu_item_id"]]

    async def test_activate_empty_menu_rejected(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        shop = await make_shop(shop_client, f"mempty-{unique_id[:8]}")
        menu = await _make_menu(shop_client, shop["shop_id"], "Пустое")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/menus/{menu['shop_menu_id']}/status",
            json={"status": "active"},
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "menu_empty"
        assert [m["status"] for m in await _menus(shop_client, shop["shop_id"])] == ["draft"]

    async def test_archived_menu_read_only_until_draft(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """Архив не редактируется и не активируется напрямую; restore → draft."""
        shop = await make_shop(shop_client, f"march-{unique_id[:8]}")
        shop_id = shop["shop_id"]
        product = await make_product(shop_client, shop_id, "Суп", 100)
        menu, _, _ = await make_active_menu_item(shop_client, shop_id, product["shop_product_id"])
        status_url = f"{_SHOPS}/{shop_id}/menus/{menu['shop_menu_id']}/status"
        resp = await shop_client.post(status_url, json={"status": "archived"})
        assert resp.status_code == 200, resp.text
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop_id}/menus/{menu['shop_menu_id']}", json={"name": "Новое"}
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "menu_status_invalid"
        resp = await shop_client.post(status_url, json={"status": "active"})
        assert resp.status_code == 409
        resp = await shop_client.post(status_url, json={"status": "draft"})
        assert resp.status_code == 200, resp.text
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop_id}/menus/{menu['shop_menu_id']}", json={"name": "Новое"}
        )
        assert resp.status_code == 200, resp.text
        assert (resp.json()["name"], resp.json()["status"]) == ("Новое", "draft")

    async def test_duplicate_product_in_menu_rejected(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        shop = await make_shop(shop_client, f"mdup-{unique_id[:8]}")
        shop_id = shop["shop_id"]
        product = await make_product(shop_client, shop_id, "Суп", 100)
        _, section, _ = await make_active_menu_item(shop_client, shop_id, product["shop_product_id"])
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/menus/{section['shop_menu_id']}/items",
            json={
                "shop_menu_section_id": section["shop_menu_section_id"],
                "shop_product_id": product["shop_product_id"],
            },
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "menu_item_duplicate"

    async def test_menus_reorder(self, shop_client: AsyncClient, unique_id: str) -> None:
        shop = await make_shop(shop_client, f"mreo-{unique_id[:8]}")
        shop_id = shop["shop_id"]
        a = await _make_menu(shop_client, shop_id, "A")
        b = await _make_menu(shop_client, shop_id, "B")
        c = await _make_menu(shop_client, shop_id, "C")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/menus/reorder",
            json={"shop_menu_ids": [c["shop_menu_id"], a["shop_menu_id"], b["shop_menu_id"]]},
        )
        assert resp.status_code == 200, resp.text
        assert [m["shop_menu_id"] for m in await _menus(shop_client, shop_id)] == [
            c["shop_menu_id"],
            a["shop_menu_id"],
            b["shop_menu_id"],
        ]
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/menus/reorder",
            json={"shop_menu_ids": [a["shop_menu_id"], "nonexistent"]},
        )
        assert resp.status_code == 404

    async def test_sections_reorder_tree(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """sections/reorder заменяет дерево целиком: родитель и sort по порядку обхода."""
        shop = await make_shop(shop_client, f"sreo-{unique_id[:8]}")
        shop_id = shop["shop_id"]
        menu = await _make_menu(shop_client, shop_id, "Меню")
        menu_id = menu["shop_menu_id"]
        hot = await _make_section(shop_client, shop_id, menu_id, "Горячее")
        drinks = await _make_section(shop_client, shop_id, menu_id, "Напитки")
        meat = await _make_section(shop_client, shop_id, menu_id, "Мясо")
        hot_id = hot["shop_menu_section_id"]
        drinks_id = drinks["shop_menu_section_id"]
        meat_id = meat["shop_menu_section_id"]
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/menus/{menu_id}/sections/reorder",
            json={
                "items": [
                    {"shop_menu_section_id": drinks_id, "parent_id": None},
                    {"shop_menu_section_id": hot_id, "parent_id": None},
                    {"shop_menu_section_id": meat_id, "parent_id": hot_id},
                ]
            },
        )
        assert resp.status_code == 200, resp.text
        listed = await _menus(shop_client, shop_id)
        tree = sorted(
            (s["shop_menu_section_id"], s["parent_id"], s["sort"]) for s in listed[0]["sections"]
        )
        assert tree == sorted([(drinks_id, None, 0), (hot_id, None, 1), (meat_id, hot_id, 0)])
        incomplete = await shop_client.post(
            f"{_SHOPS}/{shop_id}/menus/{menu_id}/sections/reorder",
            json={"items": [{"shop_menu_section_id": hot_id, "parent_id": None}]},
        )
        assert incomplete.status_code == 409
        assert incomplete.json()["error_code"] == "menu_sections_reorder_incomplete"
        cycle = await shop_client.post(
            f"{_SHOPS}/{shop_id}/menus/{menu_id}/sections/reorder",
            json={
                "items": [
                    {"shop_menu_section_id": drinks_id, "parent_id": None},
                    {"shop_menu_section_id": hot_id, "parent_id": meat_id},
                    {"shop_menu_section_id": meat_id, "parent_id": hot_id},
                ]
            },
        )
        assert cycle.status_code == 409
        assert cycle.json()["error_code"] == "menu_section_cycle"

    async def test_items_reorder_and_move(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """items/reorder переставляет позиции раздела; move переносит в конец другого раздела."""
        shop = await make_shop(shop_client, f"ireo-{unique_id[:8]}")
        shop_id = shop["shop_id"]
        menu = await _make_menu(shop_client, shop_id, "Меню")
        menu_id = menu["shop_menu_id"]
        pizza = await _make_section(shop_client, shop_id, menu_id, "Пицца")
        drinks = await _make_section(shop_client, shop_id, menu_id, "Напитки")
        pizza_id = pizza["shop_menu_section_id"]
        drinks_id = drinks["shop_menu_section_id"]
        items = []
        for name in ("A", "B", "C"):
            product = await make_product(shop_client, shop_id, name, 100)
            items.append(
                await add_menu_item(shop_client, shop_id, menu_id, pizza_id, product["shop_product_id"])
            )
        a, b, c = (i["shop_menu_item_id"] for i in items)
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/menu-items/reorder",
            json={"shop_menu_section_id": pizza_id, "shop_menu_item_ids": [c, a, b]},
        )
        assert resp.status_code == 200, resp.text

        def section_order(menu_body: dict[str, Any], section_id: str) -> list[str]:
            rows = [i for i in menu_body["items"] if i["shop_menu_section_id"] == section_id]
            return [i["shop_menu_item_id"] for i in sorted(rows, key=lambda i: i["sort"])]

        listed = await _menus(shop_client, shop_id)
        assert section_order(listed[0], pizza_id) == [c, a, b]
        moved = await shop_client.post(
            f"{_SHOPS}/{shop_id}/menu-items/{a}/move",
            json={"shop_menu_section_id": drinks_id},
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["shop_menu_section_id"] == drinks_id
        listed = await _menus(shop_client, shop_id)
        assert (section_order(listed[0], pizza_id), section_order(listed[0], drinks_id)) == (
            [c, b],
            [a],
        )
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/menu-items/reorder",
            json={"shop_menu_section_id": pizza_id, "shop_menu_item_ids": [a]},
        )
        assert resp.status_code == 404

    async def test_menus_isolation(
        self,
        shop_client: AsyncClient,
        shop_client_company2: AsyncClient,
        unique_id: str,
    ) -> None:
        """Меню чужой компании: список, создание, статус, раздел и позиция — 404."""
        shop = await make_shop(shop_client, f"miso-{unique_id[:8]}")
        shop_id = shop["shop_id"]
        product = await make_product(shop_client, shop_id, "Суп", 100)
        menu, section, item = await make_active_menu_item(
            shop_client, shop_id, product["shop_product_id"]
        )
        menu_id = menu["shop_menu_id"]
        for method, url, body in (
            ("get", f"{_SHOPS}/{shop_id}/menus", None),
            ("post", f"{_SHOPS}/{shop_id}/menus", {"name": "hack"}),
            ("patch", f"{_SHOPS}/{shop_id}/menus/{menu_id}", {"name": "hack"}),
            ("post", f"{_SHOPS}/{shop_id}/menus/{menu_id}/status", {"status": "draft"}),
            ("post", f"{_SHOPS}/{shop_id}/menus/{menu_id}/sections", {"name": "hack"}),
            (
                "patch",
                f"{_SHOPS}/{shop_id}/menu-sections/{section['shop_menu_section_id']}",
                {"name": "hack"},
            ),
            (
                "patch",
                f"{_SHOPS}/{shop_id}/menu-items/{item['shop_menu_item_id']}",
                {"is_available": False},
            ),
            ("delete", f"{_SHOPS}/{shop_id}/menus/{menu_id}", None),
        ):
            resp = await shop_client_company2.request(method, url, json=body)
            assert resp.status_code == 404, (method, url, resp.text)
        listed = await _menus(shop_client, shop_id)
        assert [(m["name"], m["status"]) for m in listed] == [("Меню", "active")]
        assert [i["is_available"] for i in listed[0]["items"]] == [True]
