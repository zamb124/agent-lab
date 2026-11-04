"""Публичная витрина: снапшот, ETag/304, host-рерайт, видимость по статусу."""

from __future__ import annotations

from typing import Any

from httpx2 import AsyncClient

from apps.shop.api.storefront_shell import accent_vars, contrast_ratio, hex_rgb
from tests.fixtures.shop import API_PREFIX, PUBLIC_PREFIX

_SHOPS = f"{API_PREFIX}/shops"


async def _published_shop(
    client: AsyncClient, slug: str
) -> dict[str, Any]:
    resp = await client.post(
        _SHOPS, json={"slug": slug, "name": f"Store {slug}", "kind": "cafe"}
    )
    assert resp.status_code == 200, resp.text
    shop = resp.json()
    resp = await client.post(f"{_SHOPS}/{shop['shop_id']}/publish")
    assert resp.status_code == 200, resp.text
    return shop


class TestStorefrontSnapshot:
    async def test_published_shop_served_anonymously(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"sf-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/products",
            json={"name": "Латте", "price_minor": 25000},
        )
        assert resp.status_code == 200
        snap = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert snap.status_code == 200, snap.text
        body = snap.json()
        assert body["slug"] == slug
        assert body["name"] == f"Store {slug}"

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
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/products",
            json={"name": "Скрытый", "price_minor": 100},
        )
        product = resp.json()
        await shop_client.patch(
            f"{_SHOPS}/{shop['shop_id']}/products/{product['shop_product_id']}",
            json={"is_available": False},
        )
        snap = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert snap.status_code == 200
        names = [p["name"] for p in snap.json()["products"]]
        assert "Скрытый" not in names

    async def test_categories_hierarchy_in_snapshot(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """Снапшот несёт parent_id категорий — витрина строит дерево разделов."""
        slug = f"hier-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/categories", json={"name": "Пицца"}
        )
        parent = resp.json()
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/categories",
            json={"name": "Классика", "parent_id": parent["shop_category_id"]},
        )
        child = resp.json()
        snap = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert snap.status_code == 200, snap.text
        cats = {c["id"]: c for c in snap.json()["categories"]}
        assert cats[parent["shop_category_id"]]["parent_id"] is None
        assert cats[child["shop_category_id"]]["parent_id"] == parent["shop_category_id"]

    async def test_badges_in_snapshot(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"bdg-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        resp = await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/products",
            json={"name": "Хитовая", "price_minor": 100, "badges": ["hit", "spicy"]},
        )
        assert resp.status_code == 200, resp.text
        snap = await shop_public_client.get(f"{PUBLIC_PREFIX}/storefront/{slug}")
        assert snap.status_code == 200
        product = next(p for p in snap.json()["products"] if p["name"] == "Хитовая")
        assert product["badges"] == ["hit", "spicy"]
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
        совпадению slug с именем поддомена. Tenant-ключ Redis (TTL ~сутки)
        переживает прогоны — чистим, иначе резолв вернёт slug прошлого запуска.
        """
        slug = f"co2-{unique_id[:8]}"
        await _published_shop(shop_client_company2, slug)
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
        await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/products",
            json={"name": "Борщ", "price_minor": 35000, "description": "Со сметаной"},
        )
        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/s/{slug}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert slug in resp.text
        assert resp.headers.get("etag")

    async def test_storefront_page_seo_jsonld(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """SEO-слой витрины: OG-теги, canonical и JSON-LD LocalBusiness с меню."""
        slug = f"seo-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/products",
            json={"name": "Борщ", "price_minor": 35000},
        )
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
        """Диплинк ?p=<product_id>: карточки несут data-pid, JS скроллит и подсвечивает."""
        slug = f"deep-{unique_id[:8]}"
        shop = await _published_shop(shop_client, slug)
        await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/products",
            json={"name": "Борщ", "price_minor": 35000},
        )
        html = await shop_public_client.get(f"{PUBLIC_PREFIX}/s/{slug}?p=x")
        assert html.status_code == 200
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
        assert "Сейчас закрыто" in html.text
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
        assert "--bg:#f5f4f2" in html.text
        assert "--accent:#3f8cff" in html.text
        assert "color-scheme:light" in html.text

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
        resp = await shop_client.post(
            f"{_SHOPS}/{shop_id}/products",
            json={"name": "Пицца", "price_minor": 50000},
        )
        assert resp.status_code == 200, resp.text
        product = resp.json()
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


class TestStorefrontThemeTokens:
    """Семантические токены витрины: палитры-пары, производные accent, контрасты."""

    async def test_semantic_tokens_emitted(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """HTML содержит полный набор токенов: семантика, тени, оверлей, color-scheme."""
        slug = f"tok-{unique_id[:8]}"
        await _published_shop(shop_client, slug)
        html = await shop_public_client.get(f"{PUBLIC_PREFIX}/s/{slug}")
        assert html.status_code == 200
        text = html.text
        for token in (
            "--on-accent:",
            "--afg:",
            "--overlay:",
            "--on-hero:",
            "--success:",
            "--warn:",
            "--shadow-sm:",
            "--shadow-lg:",
            "color-scheme:dark",
        ):
            assert token in text, token
        assert "--bg:#131110" in text
        assert "var(--on-hero)" in text
        assert "var(--on-accent)" in text

    async def test_amber_accent_gets_dark_on_accent(
        self, shop_public_client: AsyncClient, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """Светлый accent (#f2a33c) → тёмный текст на кнопках, а не белый."""
        slug = f"amb-{unique_id[:8]}"
        await _published_shop(shop_client, slug)
        html = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/s/{slug}?taccent=%23f2a33c"
        )
        assert html.status_code == 200
        assert "--accent:#f2a33c" in html.text
        assert "--on-accent:#1d1a16" in html.text

    async def test_dark_accent_stays_readable_in_dark_theme(
        self, shop_public_client: AsyncClient, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """Почти чёрный accent (#111827) в dark-теме: --afg осветляется до читаемого."""
        slug = f"drk-{unique_id[:8]}"
        await _published_shop(shop_client, slug)
        html = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/s/{slug}?taccent=%23111827"
        )
        assert html.status_code == 200
        root = html.text.split(":root{")[1].split("}")[0]
        assert "--afg:#111827" not in root
        assert "--afg:#84868a" in root

    async def test_light_theme_has_no_weak_hero_veil(
        self, shop_public_client: AsyncClient, shop_client: AsyncClient, unique_id: str
    ) -> None:
        """Убрана ослабленная вуаль hero для light — текст читаем в обеих темах."""
        slug = f"veil-{unique_id[:8]}"
        await _published_shop(shop_client, slug)
        html = await shop_public_client.get(f"{PUBLIC_PREFIX}/s/{slug}?tmode=light")
        assert html.status_code == 200
        assert "body.light .hero .veil" not in html.text


def test_accent_vars_contrast_guarantee() -> None:
    """Все 8 акцентов конструктора: --afg даёт контраст ≥4.5 на обоих фонах,
    --on-accent — ≥3 на самом accent."""
    accents = [
        "#e2553f", "#f2a33c", "#34c47c", "#3f8cff",
        "#9b5de5", "#ef476f", "#111827", "#0f766e",
    ]
    for accent in accents:
        rgb = hex_rgb(accent)
        vars_ = accent_vars(accent)
        assert contrast_ratio(rgb, hex_rgb(vars_["on_accent"])) >= 3.0, accent
        assert contrast_ratio(hex_rgb(vars_["afg_dark"]), (0x13, 0x11, 0x10)) >= 4.5, accent
        assert contrast_ratio(hex_rgb(vars_["afg_light"]), (0xF5, 0xF4, 0xF2)) >= 4.5, accent


def test_accent_vars_invalid_falls_back_to_default() -> None:
    """Мусорный accent не падает — токены считаются от дефолтного #e2553f."""
    assert accent_vars("not-a-color") == accent_vars("#e2553f")


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
