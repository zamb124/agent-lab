"""Публичная витрина: снапшот, ETag/304, host-рерайт, видимость по статусу."""

from __future__ import annotations

from typing import Any

from httpx2 import AsyncClient

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
