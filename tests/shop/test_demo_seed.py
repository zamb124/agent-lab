"""Demo-сид витрин: шаблоны, идемпотентность, demo-маркировка.

Путь продовый: `ShopSeedService` через `shop_di`, реальные Postgres/S3 —
проверяется, что шаблоны разворачиваются в строки, фото заливаются
публичными файлами, повторный сид insert-only, а soft-deleted пример не
воскрешается. REST `/demos/seed` проверяется на throwaway-компании, чтобы
worker-задача не сеяла в `system`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from apps.shop.di import ShopDi
from apps.shop.models.banner import ShopBanner
from apps.shop.models.enums import ShopOrderStatus, ShopShelfKind, ShopStatus
from apps.shop.models.modifier_group import ShopModifierGroup
from apps.shop.models.modifier_option import ShopModifierOption
from apps.shop.models.order import ShopOrder
from apps.shop.models.order_feedback import ShopOrderFeedback
from apps.shop.models.order_item import ShopOrderItem
from apps.shop.models.product import ShopProduct
from apps.shop.models.promo import ShopPromo
from apps.shop.models.shelf import ShopShelf
from apps.shop.models.shop import Shop
from apps.shop.models.table import ShopTable
from apps.shop.realtime.company_operations import ShopScheduledResponse
from apps.shop.seed import DEMO_TEMPLATES
from apps.shop.services.seed_service import ShopSeedService
from core.authz.company_sync import sync_company_member_roles
from core.context import clear_context, set_context
from core.context.job_context import build_job_context
from core.models.identity_models import Company, User
from core.types import JsonObject, JsonValue
from core.utils.time import utcnow
from core.utils.tokens import get_token_service
from tests.fixtures.ai_provider_defaults import make_test_company

_ASSETS = (
    Path(__file__).resolve().parents[2] / "apps" / "shop" / "seed" / "assets"
)
_API_PREFIX = "/shop/api/v1"


class TestDemoTemplatesIntegrity:
    """Согласованность декларативных спек и файлового банка — без БД."""

    def test_templates_cover_required_kinds(self) -> None:
        keys = {tpl.key for tpl in DEMO_TEMPLATES}
        assert keys == {"cafe", "bakery", "pizza", "market"}

    def test_every_referenced_photo_exists(self) -> None:
        for tpl in DEMO_TEMPLATES:
            photos = {
                tpl.cover_photo,
                *(p.photo for p in tpl.products),
                *(b.photo for b in tpl.banners if b.photo),
                *(
                    o.photo
                    for g in tpl.modifier_groups
                    for o in g.options
                    if o.photo
                ),
            }
            for photo in photos:
                path = _ASSETS / tpl.key / photo
                assert path.is_file(), f"missing asset {tpl.key}/{photo}"
                assert path.stat().st_size > 10_000, f"tiny asset {tpl.key}/{photo}"

    def test_feed_specs_resolve(self) -> None:
        """Полки/баннеры ссылаются на существующие ключи продуктов и категорий."""
        for tpl in DEMO_TEMPLATES:
            product_keys = {p.key for p in tpl.products}
            category_keys = {c.key for c in tpl.categories}
            shelf_keys = {s.key for s in tpl.shelves}
            for shelf in tpl.shelves:
                if shelf.kind in (ShopShelfKind.MANUAL, ShopShelfKind.UPSELL):
                    for key in shelf.product_keys:
                        assert key in product_keys, f"{tpl.key}: shelf {key}"
                if shelf.kind is ShopShelfKind.CATEGORY:
                    assert shelf.category_key in category_keys
            for banner in tpl.banners:
                prefix, _, ref = banner.link.partition(":")
                if prefix == "product":
                    assert ref in product_keys, f"{tpl.key}: banner {banner.link}"
                if prefix == "category":
                    assert ref in category_keys
                if prefix == "shelf":
                    assert ref in shelf_keys

    def test_entity_keys_unique_per_template(self) -> None:
        for tpl in DEMO_TEMPLATES:
            keys = [
                *(c.key for c in tpl.categories),
                *(g.key for g in tpl.modifier_groups),
                *(p.key for p in tpl.products),
                *(p.key for p in tpl.promos),
                *(t.key for t in tpl.tables),
            ]
            assert len(keys) == len(set(keys)), f"dup keys in {tpl.key}"

    def test_order_item_refs_resolve(self) -> None:
        for tpl in DEMO_TEMPLATES:
            product_keys = {p.key for p in tpl.products}
            group_keys = {g.key for g in tpl.modifier_groups}
            option_keys = {
                (g.key, o.key) for g in tpl.modifier_groups for o in g.options
            }
            table_keys = {t.key for t in tpl.tables}
            for order in tpl.orders:
                for item in order.items:
                    assert item.product_key in product_keys
                    for group_key, option_key in item.selections:
                        assert group_key in group_keys
                        assert (group_key, option_key) in option_keys
                if order.table_key:
                    assert order.table_key in table_keys

    def test_feedback_only_on_done_orders(self) -> None:
        """Отзыв валиден только на завершённом заказе — как у покупателя."""
        for tpl in DEMO_TEMPLATES:
            for order in tpl.orders:
                if order.feedback is not None:
                    assert order.status is ShopOrderStatus.DONE, tpl.key
            assert any(
                order.feedback is not None for order in tpl.orders
            ), f"{tpl.key}: no seeded feedback"


SeedCtx = tuple[ShopSeedService, Company, User]


@pytest_asyncio.fixture
async def seed_company_ctx(
    shop_di: ShopDi, unique_id: str
) -> AsyncIterator[SeedCtx]:
    """Свежая компания + owner + FGA-гранты (как `_ensure_test_company_member`)."""
    suffix = unique_id[:8]
    company_id = f"seedco-{suffix}"
    user_id = f"seed_user_{suffix}"
    roles = ["owner", "admin"]
    company = make_test_company(
        company_id=company_id,
        name=f"Seed Co {suffix}",
        subdomain=f"seedco-{suffix}",
        owner_user_id=user_id,
        members={user_id: roles},
    )
    _ = await Company.set(company)
    user = User(
        user_id=user_id,
        name="Seed Owner",
        emails=[f"{user_id}@seed.local"],
        companies={company_id: roles},
        active_company_id=company_id,
    )
    _ = await User.set(user)
    await sync_company_member_roles(
        shop_di.authz_service,
        company_id=company_id,
        user_id=user_id,
        roles=roles,
    )
    ctx = build_job_context(
        company=company,
        user=user,
        host="seed-test.local",
        trace_id=f"seed-test:{suffix}",
        session_id=f"seed-test:{suffix}",
        channel="test",
    )
    _ = set_context(ctx)
    try:
        yield shop_di.seed_service, company, user
    finally:
        clear_context()


def _demo_shop_id(tpl_key: str, company_id: str) -> str:
    return f"demo:{tpl_key}:{company_id}"


def _templates(stats: JsonObject) -> dict[str, JsonValue]:
    templates = stats["templates"]
    assert isinstance(templates, dict)
    return templates


def _obj_list(snapshot: JsonObject, key: str) -> list[JsonObject]:
    raw = snapshot[key]
    assert isinstance(raw, list)
    items = [x for x in raw if isinstance(x, dict)]
    assert len(items) == len(raw)
    return items


def _str_list(value: JsonValue) -> list[str]:
    assert isinstance(value, list)
    items = [x for x in value if isinstance(x, str)]
    assert len(items) == len(value)
    return items


class TestDemoSeedService:
    async def test_seed_creates_all_templates(self, seed_company_ctx: SeedCtx) -> None:
        service, company, user = seed_company_ctx
        stats = await service.seed_company(
            company=company, owner_user_id=user.user_id
        )
        assert _templates(stats) == {
            tpl.key: "created" for tpl in DEMO_TEMPLATES
        }

        for tpl in DEMO_TEMPLATES:
            shop = await Shop.get_by_id_with_deleted(
                _demo_shop_id(tpl.key, company.company_id)
            )
            assert shop is not None, tpl.key
            assert shop.status is ShopStatus.DRAFT
            assert shop.demo_template == tpl.key
            assert shop.cover_file_id is not None
            assert shop.company_id == company.company_id
            assert shop.lat == tpl.lat and shop.lng == tpl.lng

            products = await ShopProduct.list_by_shop_by_sort_asc(shop.shop_id)
            assert len(products) == len(tpl.products)
            assert all(p.photo_file_id for p in products)

            promos = await ShopPromo.list_by_shop_by_sort_asc(shop.shop_id)
            assert len(promos) == len(tpl.promos)

            shelves = await ShopShelf.list_by_shop_by_sort_asc(shop.shop_id)
            assert len(shelves) == len(tpl.shelves)
            banners = await ShopBanner.list_by_shop_by_sort_asc(shop.shop_id)
            assert len(banners) == len(tpl.banners)
            for flag, enabled in tpl.features.items():
                assert shop.features.get(flag) == enabled, f"{tpl.key}: {flag}"
            for banner, spec in zip(banners, tpl.banners, strict=True):
                if spec.link.startswith("product:"):
                    assert banner.link.startswith("product:")
                    assert banner.link != spec.link, "key must resolve to real id"

            tables = await ShopTable.list_by_shop_by_created_asc(shop.shop_id)
            assert len(tables) == len(tpl.tables)

            orders = await ShopOrder.list_by_shop_by_created_desc(shop.shop_id)
            assert len(orders) == len(tpl.orders)
            feedback_expected = sum(
                1 for o in tpl.orders if o.feedback is not None
            )
            feedback_rows = [
                fb
                for order in orders
                if (
                    fb := await ShopOrderFeedback.find_by_order(
                        order.shop_order_id
                    )
                )
                is not None
            ]
            assert len(feedback_rows) == feedback_expected, tpl.key
            for order in orders:
                assert order.status_history, "order must show status timeline"
                items = await ShopOrderItem.list_by_order(order.shop_order_id)
                assert items, f"order {order.shop_order_id} has no items"

    async def test_nested_modifiers_present(self, seed_company_ctx: SeedCtx) -> None:
        service, company, user = seed_company_ctx
        _ = await service.seed_company(
            company=company, owner_user_id=user.user_id
        )
        shop_id = _demo_shop_id("pizza", company.company_id)
        groups = await ShopModifierGroup.list_by_shop_by_sort_asc(shop_id)
        assert groups
        nested_found = False
        for group in groups:
            options = await ShopModifierOption.list_by_group_by_sort_asc(
                group.shop_modifier_group_id
            )
            if any(o.nested_group_id is not None for o in options):
                nested_found = True
        assert nested_found, "pizza demo must show nested modifier groups"

    async def test_seeded_feed_content(
        self, seed_company_ctx: SeedCtx, shop_di: ShopDi
    ) -> None:
        """Новая витринная функциональность посеяна: КБЖУ, недоступные
        позиции, фото и дельты опций, полки резолвятся в снапшоте,
        баннеры ведут на реальные id."""
        service, company, user = seed_company_ctx
        _ = await service.seed_company(
            company=company, owner_user_id=user.user_id
        )
        for tpl in DEMO_TEMPLATES:
            shop = await Shop.get_by_id(_demo_shop_id(tpl.key, company.company_id))
            assert shop is not None

            products = await ShopProduct.list_by_shop_by_sort_asc(shop.shop_id)
            by_key = {
                p.shop_product_id.rsplit(":", 1)[-1]: p for p in products
            }
            for spec in tpl.products:
                product = by_key[spec.key]
                assert product.is_available is spec.is_available, spec.key
                assert product.nutrition == dict(spec.nutrition), spec.key
                assert all(
                    isinstance(v, (int, float))
                    for v in product.nutrition.values()
                )

            spec_options = {
                (g.key, o.key): o
                for g in tpl.modifier_groups
                for o in g.options
            }
            groups = await ShopModifierGroup.list_by_shop_by_sort_asc(shop.shop_id)
            group_key_by_id = {
                g.shop_modifier_group_id: g.shop_modifier_group_id.rsplit(":", 1)[-1]
                for g in groups
            }
            for group in groups:
                options = await ShopModifierOption.list_by_group_by_sort_asc(
                    group.shop_modifier_group_id
                )
                group_key = group_key_by_id[group.shop_modifier_group_id]
                for option in options:
                    opt_key = option.shop_modifier_option_id.rsplit(":", 1)[-1]
                    opt_key = opt_key.removeprefix(f"{group_key}_")
                    spec_opt = spec_options[(group_key, opt_key)]
                    assert option.nutrition_delta == dict(spec_opt.nutrition_delta)
                    assert option.max_per_option == spec_opt.max_per_option
                    if spec_opt.photo:
                        assert option.photo_file_id is not None, opt_key

            snapshot = await shop_di.storefront_service.build_snapshot(shop)
            snap_products = _obj_list(snapshot, "products")
            snap_product_ids = {
                str(p["id"]) for p in snap_products
            }
            assert snap_product_ids == {p.shop_product_id for p in products}
            snap_shelves = _obj_list(snapshot, "shelves")
            for shelf in snap_shelves:
                for pid in _str_list(shelf["product_ids"]):
                    assert pid in snap_product_ids, f"{tpl.key}: stale shelf ref"
            unavailable_ids = {
                p.shop_product_id for p in products if not p.is_available
            }
            comeback = [s for s in snap_shelves if s["kind"] == "comeback"]
            assert comeback, f"{tpl.key}: comeback shelf missing"
            comeback_ids = set(_str_list(comeback[0]["product_ids"]))
            assert comeback_ids <= unavailable_ids
            assert comeback_ids, f"{tpl.key}: comeback empty"
            favorites = [s for s in snap_shelves if s["kind"] == "favorites"]
            assert favorites, f"{tpl.key}: favorites shelf missing"
            for shelf in snap_shelves:
                if shelf["kind"] in {"usual", "favorites"}:
                    assert _str_list(shelf["product_ids"]) == [], (
                        f"{shelf['kind']} resolves per customer via /personal"
                    )
            snap_shelf_ids = {str(s["id"]) for s in snap_shelves}
            snap_cat_ids = {
                str(c["id"]) for c in _obj_list(snapshot, "categories")
            }
            snap_banners = _obj_list(snapshot, "banners")
            assert snap_banners, f"{tpl.key}: banners missing"
            for banner in snap_banners:
                assert banner["image_file_id"]
                link = str(banner["link"])
                prefix, _, ref = link.partition(":")
                if prefix == "product":
                    assert ref in snap_product_ids, link
                if prefix == "category":
                    assert ref in snap_cat_ids, link
                if prefix == "shelf":
                    assert ref in snap_shelf_ids, link
            rating = snapshot["rating"]
            assert isinstance(rating, dict)
            review_count = sum(1 for o in tpl.orders if o.feedback is not None)
            assert rating["count"] == review_count, tpl.key
            if review_count:
                assert rating["avg"] is not None
            chips_dict = snapshot["feedback_chips"]
            assert isinstance(chips_dict, dict)
            assert set(chips_dict) == {"pos", "neg"}, tpl.key

    async def test_seed_is_idempotent(self, seed_company_ctx: SeedCtx) -> None:
        service, company, user = seed_company_ctx
        first = await service.seed_company(
            company=company, owner_user_id=user.user_id
        )
        assert set(_templates(first).values()) == {"created"}
        second = await service.seed_company(
            company=company, owner_user_id=user.user_id
        )
        assert set(_templates(second).values()) == {"exists"}

    async def test_deleted_demo_is_not_resurrected(self, seed_company_ctx: SeedCtx) -> None:
        service, company, user = seed_company_ctx
        _ = await service.seed_company(
            company=company, owner_user_id=user.user_id
        )
        cafe_id = _demo_shop_id("cafe", company.company_id)
        cafe = await Shop.get_by_id(cafe_id)
        assert cafe is not None
        cafe.deleted_at = utcnow()
        _ = await cafe.save(update_fields=["deleted_at"])

        stats = await service.seed_company(
            company=company, owner_user_id=user.user_id
        )
        assert _templates(stats)["cafe"] == "deleted"
        cafe_after = await Shop.get_by_id_with_deleted(cafe_id)
        assert cafe_after is not None
        assert cafe_after.deleted_at is not None

    async def test_seed_touches_only_demo_shops(self, seed_company_ctx: SeedCtx) -> None:
        service, company, user = seed_company_ctx
        _ = await service.seed_company(
            company=company, owner_user_id=user.user_id
        )
        rows = await Shop.list_alive_by_company_by_updated_desc(
            company.company_id
        )
        assert len(rows) == len(DEMO_TEMPLATES)
        assert all(r.demo_template for r in rows)


class TestDemoSeedRoute:
    """REST `/demos/seed`: admin → scheduled, member/anon → denied."""

    @pytest.mark.timeout(180)
    async def test_admin_seed_scheduled(
        self, shop_app: FastAPI, shop_di: ShopDi, seed_company_ctx: SeedCtx
    ) -> None:
        _ = shop_di
        _, company, user = seed_company_ctx
        token = get_token_service().create_token(
            user.user_id, company_id=company.company_id
        )
        async with AsyncClient(
            transport=ASGITransport(app=shop_app),
            base_url="http://linnex.io",
            headers={
                "Host": "linnex.io",
                "Authorization": f"Bearer {token}",
            },
        ) as client:
            resp = await client.post(f"{_API_PREFIX}/demos/seed")
        assert resp.status_code == 200, resp.text
        body = ShopScheduledResponse.model_validate(resp.json())
        assert body.status == "scheduled"
        assert body.task_id

        # Worker очереди `shop` поднимает задачу и сеет в throwaway-компанию:
        # полный путь REST → op → enqueue → task → ShopSeedService.
        deadline = asyncio.get_running_loop().time() + 150.0
        seeded: list[Shop] = []
        while asyncio.get_running_loop().time() < deadline:
            rows = await Shop.list_alive_by_company_by_updated_desc(
                company.company_id
            )
            seeded = [r for r in rows if r.demo_template is not None]
            if len(seeded) == len(DEMO_TEMPLATES):
                break
            await asyncio.sleep(2.0)
        assert len(seeded) == len(DEMO_TEMPLATES), (
            f"seed task did not finish, got {[r.shop_id for r in seeded]}"
        )
        assert all(r.status is ShopStatus.DRAFT for r in seeded)

    async def test_member_seed_forbidden(
        self,
        shop_app: FastAPI,
        shop_di: ShopDi,
        auth_headers_company2_user2: dict[str, str],
    ) -> None:
        _ = shop_di
        async with AsyncClient(
            transport=ASGITransport(app=shop_app),
            base_url="http://linnex.io",
            headers={"Host": "linnex.io", **auth_headers_company2_user2},
        ) as client:
            resp = await client.post(f"{_API_PREFIX}/demos/seed")
        assert resp.status_code == 403, resp.text

    async def test_anonymous_seed_unauthorized(
        self, shop_public_client: AsyncClient
    ) -> None:
        resp = await shop_public_client.post(f"{_API_PREFIX}/demos/seed")
        assert resp.status_code in (401, 403), resp.text
