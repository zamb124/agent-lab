"""Инфраструктурные контракты shop: очередь, миграции, маршруты, события."""

from __future__ import annotations

from httpx2 import AsyncClient

from tests.fixtures.shop import API_PREFIX, PUBLIC_PREFIX

_SHOPS = f"{API_PREFIX}/shops"


class TestWorkerTopology:
    def test_shop_queue_registered(self) -> None:
        from apps.worker_manifest import all_queues, wire_worker

        assert "shop" in all_queues()
        broker = wire_worker("shop")
        assert broker.queue_name == "shop"

    def test_shop_task_specs_declared(self) -> None:
        from apps.shop.tasks.task_names import (
            SHOP_AI_DESCRIBE_BATCH,
            SHOP_NOTIFY_ORDER,
            SHOP_PROVISION_DOMAIN,
            SHOP_REBUILD_AGGREGATE,
            SHOP_REBUILD_STOREFRONT,
            SHOP_RECONCILE_DOMAINS_TICK,
        )

        for spec in (
            SHOP_AI_DESCRIBE_BATCH,
            SHOP_REBUILD_STOREFRONT,
            SHOP_NOTIFY_ORDER,
            SHOP_PROVISION_DOMAIN,
            SHOP_RECONCILE_DOMAINS_TICK,
            SHOP_REBUILD_AGGREGATE,
        ):
            assert spec.queue == "shop"
        assert SHOP_RECONCILE_DOMAINS_TICK.scheduled is True

    def test_worker_app_builds(self) -> None:
        """worker_app собирается: wire_worker(shop) + build_worker без startup-хуков."""
        import apps.shop.worker as worker_module

        assert worker_module.worker_app is not None


class TestMigrationRegistry:
    def test_shop_in_migration_manifest(self) -> None:
        from core.db.migration_manifest import (
            expected_migration_registry_names,
            get_migration_service_names,
        )

        assert "shop" in get_migration_service_names()
        assert "shop" in expected_migration_registry_names()

    def test_shop_url_key_resolves(self) -> None:
        from core.config import get_settings
        from core.db.migration_manifest import database_url_for_migration_key

        url = database_url_for_migration_key(get_settings().database, "shop_url")
        assert url and "platform_shop" in url


class TestEventRegistry:
    def test_shop_events_registered(self) -> None:
        import apps.shop.events  # noqa: F401 — side-effect регистрации
        from apps.shop.events import (
            SHOP_CATALOG_CHANGED,
            SHOP_ORDER_CREATED,
            SHOP_SHOP_PUBLISHED,
        )

        assert SHOP_SHOP_PUBLISHED == "shop/shop/published"
        assert SHOP_ORDER_CREATED == "shop/order/created"
        assert SHOP_CATALOG_CHANGED == "shop/catalog/changed"


class TestAggregate:
    async def test_search_across_shops(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        for i, suffix in enumerate(("one", "two")):
            slug = f"agg{i}-{unique_id[:6]}"
            resp = await shop_client.post(
                _SHOPS, json={"slug": slug, "name": f"Rest {suffix}", "kind": "restaurant"}
            )
            shop = resp.json()
            await shop_client.post(f"{_SHOPS}/{shop['shop_id']}/publish")
            await shop_client.post(
                f"{_SHOPS}/{shop['shop_id']}/products",
                json={"name": f"Суши сет {suffix}", "price_minor": 1000 * (i + 1)},
            )
        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/aggregate/search", params={"q": "Суши сет"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        slugs = {item["shop_slug"] for item in body["items"]}
        assert len(slugs) >= 2
        assert body["total"] >= 2
        first = body["items"][0]
        assert first["shop_name"].startswith("Rest ")

    async def test_aggregate_shops_listed(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"list-{unique_id[:8]}"
        resp = await shop_client.post(
            _SHOPS, json={"slug": slug, "name": "Listed", "kind": "bakery"}
        )
        await shop_client.post(f"{_SHOPS}/{resp.json()['shop_id']}/publish")
        resp = await shop_public_client.get(f"{PUBLIC_PREFIX}/aggregate/shops")
        assert resp.status_code == 200
        assert any(s["slug"] == slug for s in resp.json()["items"])

    async def test_search_excludes_draft_shops(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        slug = f"nosea-{unique_id[:8]}"
        resp = await shop_client.post(
            _SHOPS, json={"slug": slug, "name": "DraftRest"}
        )
        shop = resp.json()
        await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/products",
            json={"name": f"УникПродукт{unique_id[:6]}", "price_minor": 100},
        )
        resp = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/aggregate/search",
            params={"q": f"УникПродукт{unique_id[:6]}"},
        )
        assert resp.status_code == 200
        assert all(
            item["shop_slug"] != slug for item in resp.json()["items"]
        )

    async def test_search_matches_description_and_typos(
        self, shop_client: AsyncClient, shop_public_client: AsyncClient, unique_id: str
    ) -> None:
        """pg_trgm-поиск: совпадение по описанию и устойчивость к опечатке."""
        slug = f"trgm-{unique_id[:8]}"
        resp = await shop_client.post(
            _SHOPS, json={"slug": slug, "name": "TrgmRest", "kind": "restaurant"}
        )
        shop = resp.json()
        await shop_client.post(f"{_SHOPS}/{shop['shop_id']}/publish")
        marker = unique_id[:6]
        await shop_client.post(
            f"{_SHOPS}/{shop['shop_id']}/products",
            json={
                "name": f"Суп дня {marker}",
                "price_minor": 100,
                "description": f"с пампушками {marker} и сметаной",
            },
        )
        by_desc = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/aggregate/search",
            params={"q": f"пампушками {marker}"},
        )
        assert by_desc.status_code == 200
        assert any(i["shop_slug"] == slug for i in by_desc.json()["items"])
        by_typo = await shop_public_client.get(
            f"{PUBLIC_PREFIX}/aggregate/search",
            params={"q": f"пампушкамы {marker}"},
        )
        assert any(i["shop_slug"] == slug for i in by_typo.json()["items"])
