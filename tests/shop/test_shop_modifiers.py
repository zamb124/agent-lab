"""Модификаторы shop: CRUD групп/опций, attach к товару, цена и валидация в заказе.

Продовый путь: реальный Postgres + Redis, REST-зеркала команд.
"""

from __future__ import annotations

from typing import Any

from httpx2 import AsyncClient

from tests.fixtures.shop import API_PREFIX, PUBLIC_PREFIX

_SHOPS = f"{API_PREFIX}/shops"


async def _shop_with_product(
    client: AsyncClient, slug: str, price: int = 50000
) -> tuple[dict[str, Any], dict[str, Any]]:
    resp = await client.post(
        _SHOPS, json={"slug": slug, "name": f"Shop {slug}", "kind": "restaurant", "lat": 55.7512, "lng": 37.6184}
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


async def _make_group(
    client: AsyncClient, shop_id: str, name: str, **overrides: Any
) -> dict[str, Any]:
    resp = await client.post(
        f"{_SHOPS}/{shop_id}/modifier-groups", json={"name": name, **overrides}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _make_option(
    client: AsyncClient, shop_id: str, group_id: str, name: str, **overrides: Any
) -> dict[str, Any]:
    resp = await client.post(
        f"{_SHOPS}/{shop_id}/modifier-groups/{group_id}/options",
        json={"name": name, **overrides},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _attach(
    client: AsyncClient, shop_id: str, product_id: str, group_id: str, **body: Any
) -> None:
    resp = await client.post(
        f"{_SHOPS}/{shop_id}/products/{product_id}/modifier-groups/{group_id}",
        json=body,
    )
    assert resp.status_code == 200, resp.text


def _order_body(product_id: str, selections: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    return {
        "items": [{"product_id": product_id, "qty": 1, "selections": selections}],
        "customer_name": "Иван",
        "delivery_type": "pickup",
        **kw,
    }


class TestModifierAdmin:
    async def test_group_option_crud_and_attach(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        shop, product = await _shop_with_product(
            shop_client, f"mod-{unique_id[:8]}"
        )
        shop_id = shop["shop_id"]
        group = await _make_group(
            shop_client, shop_id, "Добавки", selection_mode="multi", max_selected=5
        )
        gid = group["shop_modifier_group_id"]
        assert group["price_mode"] == "delta"
        option = await _make_option(
            shop_client, shop_id, gid, "Сыр", price_minor=5000, max_per_option=3
        )
        assert option["price_minor"] == 5000
        await _attach(shop_client, shop_id, product["shop_product_id"], gid)
        listing = await shop_client.get(f"{_SHOPS}/{shop_id}/modifier-groups")
        assert listing.status_code == 200
        g = listing.json()["groups"][0]
        assert g["name"] == "Добавки"
        assert g["options"][0]["name"] == "Сыр"
        assert g["product_ids"] == [product["shop_product_id"]]
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop_id}/modifier-groups/{gid}", json={"min_selected": 1}
        )
        assert resp.status_code == 200
        assert resp.json()["min_selected"] == 1
        resp = await shop_client.delete(
            f"{_SHOPS}/{shop_id}/products/{product['shop_product_id']}/modifier-groups/{gid}"
        )
        assert resp.status_code == 200
        listing = await shop_client.get(f"{_SHOPS}/{shop_id}/modifier-groups")
        assert listing.json()["groups"][0]["product_ids"] == []

    async def test_isolation_other_company(
        self, shop_client: AsyncClient, shop_client_company2: AsyncClient, unique_id: str
    ) -> None:
        shop, _ = await _shop_with_product(shop_client, f"iso-{unique_id[:8]}")
        resp = await shop_client_company2.get(
            f"{_SHOPS}/{shop['shop_id']}/modifier-groups"
        )
        assert resp.status_code == 404


class TestModifierPricing:
    async def test_delta_addons_in_order(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"dp-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug, price=50000)
        shop_id = shop["shop_id"]
        group = await _make_group(shop_client, shop_id, "Добавки")
        gid = group["shop_modifier_group_id"]
        cheese = await _make_option(
            shop_client, shop_id, gid, "Сыр", price_minor=5000, max_per_option=5
        )
        bacon = await _make_option(shop_client, shop_id, gid, "Бекон", price_minor=7000)
        await _attach(shop_client, shop_id, product["shop_product_id"], gid)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(
                product["shop_product_id"],
                [
                    {"option_id": cheese["shop_modifier_option_id"], "qty": 2},
                    {"option_id": bacon["shop_modifier_option_id"], "qty": 1},
                ],
            ),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["total_minor"] == 50000 + 5000 * 2 + 7000

    async def test_required_group_missing_rejected(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"req-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug)
        shop_id = shop["shop_id"]
        group = await _make_group(
            shop_client, shop_id, "Размер", selection_mode="single", min_selected=1
        )
        gid = group["shop_modifier_group_id"]
        await _make_option(shop_client, shop_id, gid, "Большая", price_minor=10000)
        await _attach(shop_client, shop_id, product["shop_product_id"], gid)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(product["shop_product_id"], []),
        )
        assert resp.status_code == 409

    async def test_absolute_variant_replaces_base(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"abs-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug, price=50000)
        shop_id = shop["shop_id"]
        size = await _make_group(
            shop_client,
            shop_id,
            "Размер",
            selection_mode="single",
            min_selected=1,
            price_mode="absolute",
        )
        sgid = size["shop_modifier_group_id"]
        small = await _make_option(
            shop_client, shop_id, sgid, "Маленькая", price_minor=35000
        )
        addons = await _make_group(shop_client, shop_id, "Добавки")
        agid = addons["shop_modifier_group_id"]
        cheese = await _make_option(shop_client, shop_id, agid, "Сыр", price_minor=5000)
        await _attach(shop_client, shop_id, product["shop_product_id"], sgid)
        await _attach(shop_client, shop_id, product["shop_product_id"], agid)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(
                product["shop_product_id"],
                [
                    {"option_id": small["shop_modifier_option_id"], "qty": 1},
                    {"option_id": cheese["shop_modifier_option_id"], "qty": 1},
                ],
            ),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["total_minor"] == 35000 + 5000

    async def test_per_option_qty_limit(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"lim-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug)
        shop_id = shop["shop_id"]
        group = await _make_group(shop_client, shop_id, "Добавки", max_selected=10)
        gid = group["shop_modifier_group_id"]
        opt = await _make_option(
            shop_client, shop_id, gid, "Сыр", price_minor=5000, max_per_option=2
        )
        await _attach(shop_client, shop_id, product["shop_product_id"], gid)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(
                product["shop_product_id"],
                [{"option_id": opt["shop_modifier_option_id"], "qty": 3}],
            ),
        )
        assert resp.status_code == 409

    async def test_single_group_rejects_two_options(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"sg-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug)
        shop_id = shop["shop_id"]
        group = await _make_group(
            shop_client, shop_id, "Соус", selection_mode="single", max_selected=1
        )
        gid = group["shop_modifier_group_id"]
        a = await _make_option(shop_client, shop_id, gid, "Чесночный")
        b = await _make_option(shop_client, shop_id, gid, "Томатный")
        await _attach(shop_client, shop_id, product["shop_product_id"], gid)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(
                product["shop_product_id"],
                [
                    {"option_id": a["shop_modifier_option_id"], "qty": 1},
                    {"option_id": b["shop_modifier_option_id"], "qty": 1},
                ],
            ),
        )
        assert resp.status_code == 409

    async def test_unavailable_and_unknown_option(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"un-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug)
        shop_id = shop["shop_id"]
        group = await _make_group(shop_client, shop_id, "Добавки")
        gid = group["shop_modifier_group_id"]
        opt = await _make_option(shop_client, shop_id, gid, "Сыр", price_minor=5000)
        await _attach(shop_client, shop_id, product["shop_product_id"], gid)
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop_id}/modifier-options/{opt['shop_modifier_option_id']}",
            json={"is_available": False},
        )
        assert resp.status_code == 200
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(
                product["shop_product_id"],
                [{"option_id": opt["shop_modifier_option_id"], "qty": 1}],
            ),
        )
        assert resp.status_code == 409
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(
                product["shop_product_id"],
                [{"option_id": "shopmodopt_missing", "qty": 1}],
            ),
        )
        assert resp.status_code == 404

    async def test_nested_group_requires_parent(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"nest-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug, price=50000)
        shop_id = shop["shop_id"]
        size = await _make_group(
            shop_client, shop_id, "Размер", selection_mode="single", min_selected=1
        )
        sgid = size["shop_modifier_group_id"]
        nested = await _make_group(
            shop_client, shop_id, "Топпинги XL", max_selected=4
        )
        ngid = nested["shop_modifier_group_id"]
        big = await _make_option(
            shop_client, shop_id, sgid, "Большая",
            price_minor=10000, nested_group_id=ngid,
        )
        small = await _make_option(shop_client, shop_id, sgid, "Маленькая")
        nopt = await _make_option(shop_client, shop_id, ngid, "Доп. сыр", price_minor=3000)
        await _attach(shop_client, shop_id, product["shop_product_id"], sgid)
        # Nested-опция без родительского выбора — отказ.
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(
                product["shop_product_id"],
                [
                    {"option_id": small["shop_modifier_option_id"], "qty": 1},
                    {"option_id": nopt["shop_modifier_option_id"], "qty": 1},
                ],
            ),
        )
        assert resp.status_code == 409
        # С «Большой» — nested активна и цена складывается.
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(
                product["shop_product_id"],
                [
                    {"option_id": big["shop_modifier_option_id"], "qty": 1},
                    {"option_id": nopt["shop_modifier_option_id"], "qty": 1},
                ],
            ),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["total_minor"] == 50000 + 10000 + 3000


class TestModifierSnapshot:
    async def test_snapshot_contains_modifier_tree(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"snap-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug, price=50000)
        shop_id = shop["shop_id"]
        size = await _make_group(
            shop_client,
            shop_id,
            "Размер",
            selection_mode="single",
            min_selected=1,
            price_mode="absolute",
        )
        sgid = size["shop_modifier_group_id"]
        await _make_option(shop_client, shop_id, sgid, "Маленькая", price_minor=35000)
        await _make_option(shop_client, shop_id, sgid, "Большая", price_minor=55000)
        addons = await _make_group(shop_client, shop_id, "Добавки")
        agid = addons["shop_modifier_group_id"]
        await _make_option(shop_client, shop_id, agid, "Сыр", price_minor=5000)
        hidden = await _make_option(shop_client, shop_id, agid, "Секрет", price_minor=1)
        await shop_client.patch(
            f"{_SHOPS}/{shop_id}/modifier-options/{hidden['shop_modifier_option_id']}",
            json={"is_available": False},
        )
        await _attach(shop_client, shop_id, product["shop_product_id"], sgid)
        await _attach(shop_client, shop_id, product["shop_product_id"], agid)
        snap = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert snap.status_code == 200, snap.text
        p = snap.json()["products"][0]
        assert p["price_from_minor"] == 35000
        groups = {g["name"]: g for g in p["modifier_groups"]}
        assert set(groups) == {"Размер", "Добавки"}
        assert groups["Размер"]["price_mode"] == "absolute"
        names = {o["name"] for o in groups["Добавки"]["options"]}
        assert names == {"Сыр"}
        assert snap.json()["modifier_nested_groups"] == {}

    async def test_order_item_snapshot_has_modifiers(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"ois-{unique_id[:8]}"
        shop, product = await _shop_with_product(shop_client, slug)
        shop_id = shop["shop_id"]
        group = await _make_group(shop_client, shop_id, "Добавки")
        gid = group["shop_modifier_group_id"]
        cheese = await _make_option(
            shop_client, shop_id, gid, "Сыр", price_minor=5000, max_per_option=5
        )
        await _attach(shop_client, shop_id, product["shop_product_id"], gid)
        resp = await shop_public_client.post(
            f"{PUBLIC_PREFIX}/storefront/{slug}/orders",
            json=_order_body(
                product["shop_product_id"],
                [{"option_id": cheese["shop_modifier_option_id"], "qty": 2}],
            ),
        )
        assert resp.status_code == 200, resp.text
        orders = await shop_client.get(
            f"{_SHOPS}/{shop_id}/orders",
        )
        assert orders.status_code == 200, orders.text
        items = orders.json()["items"]
        assert items
        item = items[0]["items"][0]
        assert item["price_minor"] == 50000 + 5000 * 2
        assert item["modifiers"] == [
            {
                "group_id": gid,
                "group_name": "Добавки",
                "option_id": cheese["shop_modifier_option_id"],
                "option_name": "Сыр",
                "price_minor": 5000,
                "qty": 2,
            }
        ]


class TestAiSuggestOptions:
    async def test_suggest_options_flow_branch(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """AI-предложение опций идёт через ветку suggest_options системного flow ``shop``.

        Под MockLLM flow возвращает схему-заглушку ``{"options": []}`` → сервис
        отвечает честным ``ai_empty_result``; 200 с items — на живом провайдере.
        """
        shop, _ = await _shop_with_product(shop_client, f"ais-{unique_id[:8]}")
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/ai/suggest-options",
            json={"product_name": "Пицца Маргарита", "group_name": "Добавки"},
        )
        if resp.status_code == 200:
            items = resp.json()["items"]
            assert items
            assert all("name" in i and "price_minor" in i for i in items)
        else:
            assert resp.status_code == 404, resp.text
            assert resp.json()["error_code"] == "ai_empty_result"

    async def test_suggest_options_requires_shop(
        self, shop_client: AsyncClient
    ) -> None:
        resp = await shop_client.post(
            f"{_SHOPS}/shop_missing/ai/suggest-options",
            json={"product_name": "x"},
        )
        assert resp.status_code in (404, 400)
