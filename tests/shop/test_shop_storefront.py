"""Публичная витрина: снапшот, ETag/304, host-рерайт, видимость по статусу."""

from __future__ import annotations

from typing import Any

from httpx2 import AsyncClient

from tests.fixtures.shop import (
    API_PREFIX,
    PUBLIC_PREFIX,
    make_active_menu_item,
    make_product,
    make_shop,
    publish_shop,
)

_SHOPS = f"{API_PREFIX}/shops"


async def _published_shop(
    client: AsyncClient, slug: str
) -> dict[str, Any]:
    shop = await make_shop(client, slug, name=f"Store {slug}", kind="cafe")
    return await publish_shop(client, shop["shop_id"])


async def _menu_product(
    client: AsyncClient, shop_id: str, name: str, price_minor: int, **overrides: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Блюдо каталога позицией собственного активного меню: product, item."""
    product = await make_product(client, shop_id, name, price_minor, **overrides)
    _, _, item = await make_active_menu_item(
        client, shop_id, product["shop_product_id"], menu_name=f"Меню {name}"
    )
    return product, item


class TestStorefrontSnapshot:
    async def test_published_shop_served_anonymously(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Снапшот: активное меню → раздел → позиция; id позиции — shop_menu_item_id."""
        slug = f"sf-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        product = await make_product(
            shop_client, shop["shop_id"], "Латте", 25000, measure=300, measure_unit="ml"
        )
        menu, section, item = await make_active_menu_item(
            shop_client, shop["shop_id"], product["shop_product_id"], section_name="Кофе"
        )
        snap = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert snap.status_code == 200, snap.text
        body = snap.json()
        assert (body["slug"], body["name"]) == (slug, f"Store {slug}")
        assert body["menus"] == [{"id": menu["shop_menu_id"], "name": "Меню"}]
        assert [(s["id"], s["menu_id"], s["name"]) for s in body["sections"]] == [
            (section["shop_menu_section_id"], menu["shop_menu_id"], "Кофе")
        ]
        assert [
            (i["id"], i["product_id"], i["section_id"], i["name"], i["price_minor"], i["measure"], i["measure_unit"])
            for i in body["items"]
        ] == [
            (
                item["shop_menu_item_id"],
                product["shop_product_id"],
                section["shop_menu_section_id"],
                "Латте",
                25000,
                300,
                "ml",
            )
        ]

    async def test_catalog_product_without_active_menu_not_in_snapshot(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Каталог без меню и позиции черновика меню на витрину не попадают."""
        slug = f"nomenu-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        await make_product(shop_client, shop["shop_id"], "Только каталог", 100)
        _, item = await _menu_product(shop_client, shop["shop_id"], "Черновое", 200)
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/menus/{item['shop_menu_id']}/status",
            json={"status": "draft"},
        )
        assert resp.status_code == 200, resp.text
        snap = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert snap.status_code == 200, snap.text
        body = snap.json()
        assert (body["menus"], body["sections"], body["items"]) == ([], [], [])

    async def test_menu_item_price_override_in_snapshot(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Цена позиции на витрине — override позиции, иначе цена каталога."""
        slug = f"ovr-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        _, item = await _menu_product(shop_client, shop["shop_id"], "Суп", 30000)
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}/menu-items/{item['shop_menu_item_id']}",
            json={"price_minor_override": 27000},
        )
        assert resp.status_code == 200, resp.text
        snap = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert snap.status_code == 200, snap.text
        assert [(i["id"], i["price_minor"]) for i in snap.json()["items"]] == [
            (item["shop_menu_item_id"], 27000)
        ]

    async def test_etag_and_304(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"etag-{unique_id[:8]}"
        await _published_shop(shop_client, slug)
        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert resp.status_code == 200
        etag = resp.headers.get("etag")
        assert etag
        cached = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/{slug}", headers={"If-None-Match": etag}
        )
        assert cached.status_code == 304
        assert not cached.content

    async def test_draft_and_missing_slug_404(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        draft_slug = f"draft-{unique_id[:8]}"
        resp = await shop_client.post(
            _SHOPS, json={"slug": draft_slug, "name": "Draft"}
        )
        assert resp.status_code == 200
        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{draft_slug}")
        assert resp.status_code == 404
        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/storefront/never-{unique_id[:8]}"
        )
        assert resp.status_code == 404

    async def test_suspended_shop_hidden(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"susp-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        assert (
            await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        ).status_code == 200
        await shop_client.post(f"{_SHOPS}/{shop['shop_id']}/suspend")
        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert resp.status_code == 404

    async def test_unavailable_product_not_in_snapshot(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"hide-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        product, _ = await _menu_product(shop_client, shop["shop_id"], "Скрытый", 100)
        await _menu_product(shop_client, shop["shop_id"], "Видимый", 200)
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}/products/{product['shop_product_id']}",
            json={"is_available": False},
        )
        assert resp.status_code == 200, resp.text
        snap = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert snap.status_code == 200
        assert [i["name"] for i in snap.json()["items"]] == ["Видимый"]

    async def test_menu_sections_hierarchy_in_snapshot(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Снапшот несёт parent_id разделов активного меню — витрина строит дерево."""
        slug = f"hier-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        product = (
            await shop_client.post(
                f"{_SHOPS}/{shop['shop_id']}/products",
                json={"name": "Маргарита", "price_minor": 50000},
            )
        ).json()
        menu = (
            await shop_client.post(
                f"{_SHOPS}/{shop['shop_id']}/menus", json={"name": "Основное"}
            )
        ).json()
        parent = (
            await shop_client.post(
                f"{_SHOPS}/{shop['shop_id']}/menus/{menu['shop_menu_id']}/sections",
                json={"name": "Пицца"},
            )
        ).json()
        child = (
            await shop_client.post(
                f"{_SHOPS}/{shop['shop_id']}/menus/{menu['shop_menu_id']}/sections",
                json={"name": "Классика", "parent_id": parent["shop_menu_section_id"]},
            )
        ).json()
        add = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/menus/{menu['shop_menu_id']}/items",
            json={
                "shop_menu_section_id": child["shop_menu_section_id"],
                "shop_product_id": product["shop_product_id"],
            },
        )
        assert add.status_code == 200, add.text
        status = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/menus/{menu['shop_menu_id']}/status",
            json={"status": "active"},
        )
        assert status.status_code == 200, status.text
        snap = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert snap.status_code == 200, snap.text
        sections = {s["id"]: s for s in snap.json()["sections"]}
        assert sections[parent["shop_menu_section_id"]]["parent_id"] is None
        assert (
            sections[child["shop_menu_section_id"]]["parent_id"]
            == parent["shop_menu_section_id"]
        )

    async def test_badges_in_snapshot(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"bdg-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        await _menu_product(
            shop_client, shop["shop_id"], "Хитовая", 100, badges=["hit", "spicy"]
        )
        snap = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert snap.status_code == 200
        item = next(i for i in snap.json()["items"] if i["name"] == "Хитовая")
        assert item["badges"] == ["hit", "spicy"]
        defs = snap.json()["badge_defs"]
        assert defs["hit"]["label"] == "Хит"
        assert defs["hit"]["icon_path"].startswith("M")


class TestHostMiddleware:
    async def test_slug_host_root_rewrites_to_storefront(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """GET / на <slug>.linnex.io отдаёт HTML-витрину, а не SPA."""
        slug = f"host-{unique_id[:8]}"
        await _published_shop(shop_client, slug)
        from httpx2 import ASGITransport

        from apps.shop.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url=f"http://{slug}.linnex.io",
            headers={"Host": f"{slug}.linnex.io"},
        ) as client:
            resp = await client.get("/")
            assert resp.status_code == 200, resp.text[:200]
            assert "text/html" in resp.headers.get("content-type", "")
            assert f"Store {slug}" in resp.text

    async def test_platform_host_root_not_rewritten(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """Платформенный хост не превращается в витрину."""
        await _published_shop(shop_client, f"nois-{unique_id[:8]}")
        from httpx2 import ASGITransport

        from apps.shop.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://linnex.io",
            headers={"Host": "linnex.io"},
        ) as client:
            resp = await client.get("/")
            assert resp.status_code != 200 or "text/html" not in resp.headers.get(
                "content-type", ""
            ) or "snapshot" not in resp.text[:5000]

    async def test_company_subdomain_root_shows_company_shop(
        self, shop_client_company2: AsyncClient, shop_di, unique_id: str
    ) -> None:
        """GET / на <company>.linnex.io — published-витрина этой компании.

        Резолв по ``Company.subdomain`` → ``Shop.company_id``, а не по
        совпадению slug с именем поддомена.
        """
        slug = f"co2-{unique_id[:8]}"
        await _published_shop(shop_client_company2, slug)
        # Host→slug кэшируется в Redis; сбрасываем ключ, иначе предыдущий
        # published shop company2 останется на company2.linnex.io до TTL.
        _ = await shop_di.redis_client.delete("shop:tenant:company2.linnex.io")
        from httpx2 import ASGITransport

        from apps.shop.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://company2.linnex.io",
            headers={"Host": "company2.linnex.io"},
        ) as client:
            resp = await client.get("/")
            assert resp.status_code == 200, resp.text[:200]
            assert "text/html" in resp.headers.get("content-type", "")
            assert f"Store {slug}" in resp.text

    async def test_unknown_subdomain_root_404(
        self, shop_di, unique_id: str
    ) -> None:
        """GET / на поддомене без компании и магазина — 404 (frontend покажет auth-wall)."""
        _ = shop_di
        from httpx2 import ASGITransport

        from apps.shop.main import app

        host = f"noshop-{unique_id[:8]}.linnex.io"
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url=f"http://{host}",
            headers={"Host": host},
        ) as client:
            resp = await client.get("/")
            assert resp.status_code == 404, resp.text[:200]

    async def test_market_path_on_any_platform_host(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """GET /market — страница агрегатора на apex и поддоменах компаний."""
        slug = f"mkt-{unique_id[:8]}"
        await _published_shop(shop_client, slug)
        from httpx2 import ASGITransport

        from apps.shop.main import app

        for host in ("linnex.io", "company2.linnex.io"):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url=f"http://{host}",
                headers={"Host": host},
            ) as client:
                resp = await client.get("/market")
                assert resp.status_code == 200, host
                assert "text/html" in resp.headers.get("content-type", "")
                assert "aggregate/search" in resp.text


class TestStorefrontPage:
    async def test_storefront_page_renders_menu(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"page-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        await _menu_product(
            shop_client, shop["shop_id"], "Борщ", 35000, description="Со сметаной"
        )
        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/s/{slug}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert slug in resp.text
        assert "Борщ" in resp.text and "Со сметаной" in resp.text
        assert resp.headers.get("etag")

    async def test_storefront_page_seo_jsonld(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """SEO-слой витрины: OG-теги, canonical и JSON-LD LocalBusiness с меню."""
        slug = f"seo-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        await _menu_product(shop_client, shop["shop_id"], "Борщ", 35000)
        html = await shop_public_client.get(f"{PUBLIC_PREFIX}/s/{slug}")
        assert html.status_code == 200
        assert 'property="og:title"' in html.text
        assert 'rel="canonical"' in html.text
        assert "application/ld+json" in html.text
        assert "CafeOrCoffeeShop" in html.text
        assert "hasMenu" in html.text and "Борщ" in html.text

    async def test_storefront_deeplink_marks_product(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Диплинк ?p=<shop_menu_item_id>: карточки несут data-pid позиции, JS скроллит и подсвечивает."""
        slug = f"deep-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        _, item = await _menu_product(shop_client, shop["shop_id"], "Борщ", 35000)
        html = await shop_public_client.get(f"{PUBLIC_PREFIX}/s/{slug}?p={item['shop_menu_item_id']}")
        assert html.status_code == 200
        assert item["shop_menu_item_id"] in html.text
        assert 'data-pid="' in html.text
        assert "flashRing" in html.text
        assert "get('p')" in html.text
        assert "localStorage" in html.text and "shopcart:" in html.text

    async def test_theme_preview_params_override_snapshot(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """?tmode=/?tpreset=/?taccent= — мгновенный предпросмотр темы конструктора."""
        slug = f"prev-{unique_id[:8]}"
        await _published_shop(shop_client, slug)
        html = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/s/{slug}?tmode=light&taccent=%233f8cff"
        )
        assert html.status_code == 200
        assert 'body class="light"' in html.text
        assert "--accent:#3f8cff" in html.text
        saved = await shop_public_client.get(f"{PUBLIC_PREFIX}/s/{slug}")
        assert "--accent:#3f8cff" not in saved.text

    async def test_working_hours_in_snapshot(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Часы работы и timezone попадают в публичный снапшот витрины."""
        slug = f"wh-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}",
            json={"working_hours": {"0": "09:00-22:00", "6": "11:00-18:00"}},
        )
        assert resp.status_code == 200, resp.text
        snap = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert snap.status_code == 200
        body = snap.json()
        assert body["working_hours"] == {"0": "09:00-22:00", "6": "11:00-18:00"}
        assert body["timezone"]
        html = await shop_public_client.get(f"{PUBLIC_PREFIX}/s/{slug}")
        assert "hoursBadge" in html.text
        assert "предзаказ" in html.text
        assert "menuSearch" in html.text
        assert "msearch" in html.text

    async def test_light_theme_renders_light_palette(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """theme.mode=light → body.light и светлая палитра в HTML витрины."""
        slug = f"light-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}",
            json={"theme": {"preset": "menu", "accent_color": "#3f8cff", "mode": "light"}},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["theme"]["mode"] == "light"
        html = await shop_public_client.get(f"{PUBLIC_PREFIX}/s/{slug}")
        assert html.status_code == 200
        assert 'body class="light"' in html.text
        assert "--bg:#f7f4ee" in html.text
        assert "--accent:#3f8cff" in html.text

    async def test_theme_mode_invalid_rejected(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """Невалидный theme.mode отклоняется схемой — fail-closed."""
        slug = f"badmode-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}",
            json={"theme": {"mode": "neon"}},
        )
        assert resp.status_code in (400, 422), resp.text

    async def test_modifier_tree_renders_customize_sheet(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Продукт с модификаторами: дерево в снапшоте, sheet и selections в HTML."""
        slug = f"modpage-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        shop_id = shop["shop_id"]
        product, _ = await _menu_product(shop_client, shop_id, "Пицца", 50000)
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/modifier-groups",
            json={"name": "Размер", "selection_mode": "single", "min_selected": 1, "price_mode": "absolute"},
        )
        assert resp.status_code == 200, resp.text
        group = resp.json()
        gid = group["shop_modifier_group_id"]
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/modifier-groups/{gid}/options",
            json={"name": "40 см", "price_minor": 65000, "is_default": True},
        )
        assert resp.status_code == 200, resp.text
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/products/{product['shop_product_id']}/modifier-groups/{gid}",
            json={},
        )
        assert resp.status_code == 200, resp.text

        html = await shop_public_client.get(f"{PUBLIC_PREFIX}/s/{slug}")
        assert html.status_code == 200
        assert "csheet" in html.text
        assert "customize(" in html.text
        assert "selections" in html.text
        assert "Размер" in html.text
        assert "40 см" in html.text
        assert "modifier_groups" in html.text


class TestStorefrontDesktopLayout:
    """Десктопный контракт витрины (>=1024px): сайдбар, сетка, drawer, модалка.

    CSS-инварианты проверяются по HTML — вычисленная геометрия (ширины,
    колонки, позиции) покрыта браузерным слоем tests/ui/e2e.
    """

    async def test_desktop_breakpoint_and_container_rules(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Desktop-слой: брейкпоинт 1024px, wrap 1240px, сайдбар 230px, full-bleed hero."""
        slug = f"desk-{unique_id[:8]}"
        await _published_shop(shop_client, slug)
        html = await shop_public_client.get(f"{PUBLIC_PREFIX}/s/{slug}")
        assert html.status_code == 200
        text = html.text
        assert "@media(min-width:1024px)" in text
        assert "max-width:1240px" in text
        assert "grid-template-columns:230px minmax(0,1fr)" in text
        assert "margin:0 calc(50% - 50vw)" in text
        assert "overflow-x:clip" in text

    async def test_desktop_preset_gating_and_data_attribute(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """body[data-preset] гейтит раскладку: menu/compact в 2 колонки, grid — auto-fill."""
        slug = f"dpre-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        html = await shop_public_client.get(f"{PUBLIC_PREFIX}/s/{slug}")
        assert html.status_code == 200
        assert 'data-preset="menu"' in html.text
        assert "body[data-preset=menu] .mchunk,body[data-preset=compact] .mchunk" in html.text
        assert "body[data-preset=grid] .grid" in html.text
        resp = await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}", json={"theme": {"preset": "grid"}}
        )
        assert resp.status_code == 200, resp.text
        html = await shop_public_client.get(f"{PUBLIC_PREFIX}/s/{slug}")
        assert 'data-preset="grid"' in html.text

    async def test_desktop_drawer_modal_and_sidebar_rules(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Корзина — правый drawer с прижатой кнопкой, товар — центр-модалка, flat без сайдбара."""
        slug = f"dux-{unique_id[:8]}"
        await _published_shop(shop_client, slug)
        html = await shop_public_client.get(f"{PUBLIC_PREFIX}/s/{slug}")
        assert html.status_code == 200
        text = html.text
        assert "#sheet .panel{" in text and "right:0" in text
        assert "#sheet .panel .big{margin-top:auto}" in text
        assert "#csheet.show{display:grid;place-items:center}" in text
        assert "#app.flat .tabs{display:none}" in text
        assert "matchMedia('(min-width:1024px)')" in text

    async def test_mobile_rules_preserved(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Мобильная база осталась: wrap 720px до брейкпоинта и мелкий брейкпоинт 520px."""
        slug = f"mob-{unique_id[:8]}"
        await _published_shop(shop_client, slug)
        html = await shop_public_client.get(f"{PUBLIC_PREFIX}/s/{slug}")
        assert html.status_code == 200
        assert ".wrap{max-width:720px" in html.text
        assert "@media(max-width:520px)" in html.text


class TestMarketPage:
    async def test_market_page_lists_only_published(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Анонимная страница агрегатора: published в снапшоте, draft — нет."""
        slug = f"mkt-{unique_id[:8]}"
        await _published_shop(shop_client, slug)
        resp = await shop_client.post(
            _SHOPS, json={"slug": f"mktd-{unique_id[:8]}", "name": "Черновик"}
        )
        assert resp.status_code == 200
        html = await shop_public_client.get(f"{PUBLIC_PREFIX}/market")
        assert html.status_code == 200
        assert "text/html" in html.headers["content-type"]
        assert "<title>" in html.text and 'name="description"' in html.text
        assert slug in html.text
        assert "Черновик" not in html.text
        assert "aggregate/search" in html.text
        assert "kindChips" in html.text and "cityChips" in html.text
        assert "&kind=" in html.text and "&city=" in html.text
        assert "application/ld+json" in html.text
        assert "CollectionPage" in html.text and "ItemList" in html.text
        assert 'rel="canonical"' in html.text
        assert "?p=" in html.text
        assert "loadMore" in html.text and "offset=" in html.text

    async def test_market_page_escapes_script_breakout(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Имя с `</script>` не вырывается из inline-JSON — fail-closed против XSS."""
        slug = f"xss-{unique_id[:8]}"
        resp = await shop_client.post(
            _SHOPS,
            json={"slug": slug, "name": 'A</script><script>alert(1)</script>', "kind": "cafe"},
        )
        assert resp.status_code == 200, resp.text
        await shop_client.post(f"{_SHOPS}/{resp.json()['shop_id']}/publish")
        html = await shop_public_client.get(f"{PUBLIC_PREFIX}/market")
        assert html.status_code == 200
        assert "A</script>" not in html.text
        assert "<\\/script>" in html.text

    async def test_aggregator_host_root_rewrites_to_market(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """GET / на shop.linnex.io отдаёт страницу агрегатора, а не витрину."""
        slug = f"agg-{unique_id[:8]}"
        await _published_shop(shop_client, slug)
        from httpx2 import ASGITransport

        from apps.shop.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://shop.linnex.io",
            headers={"Host": "shop.linnex.io"},
        ) as client:
            resp = await client.get("/")
            assert resp.status_code == 200, resp.text[:200]
            assert "text/html" in resp.headers.get("content-type", "")
            assert "aggregate/search" in resp.text
            assert slug in resp.text

    async def test_robots_and_sitemap_on_suffix_hosts(
        self, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """/robots.txt и /sitemap.xml резолвятся на slug- и агрегаторном хостах."""
        slug = f"seo-{unique_id[:8]}"
        await _published_shop(shop_client, slug)
        from httpx2 import ASGITransport

        from apps.shop.main import app

        for host in (f"{slug}.linnex.io", "shop.linnex.io"):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url=f"http://{host}",
                headers={"Host": host},
            ) as client:
                robots = await client.get("/robots.txt")
                assert robots.status_code == 200, host
                assert "Sitemap:" in robots.text and host in robots.text
                sitemap = await client.get("/sitemap.xml")
                assert sitemap.status_code == 200, host
                assert f"{slug}.linnex.io" in sitemap.text
