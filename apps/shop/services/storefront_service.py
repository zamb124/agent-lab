"""StorefrontService — публичный read-path витрин: Host → снапшот из Redis.

Анонимный трафик не ходит в PostgreSQL: снапшот ``shop:sf:{slug}``
пересобирается TaskIQ-задачей после каждой мутации каталога. Промах кэша —
одно чтение из БД и запись снапшота; отсутствующая витрина кэшируется
негативным маркером на короткий TTL против stampede по свободным slug'ам.
"""

from __future__ import annotations

import hashlib
import json

from apps.shop.config import ShopSettings
from apps.shop.models import (
    Shop,
    ShopCategory,
    ShopDomain,
    ShopDomainStatus,
    ShopProduct,
    ShopPromo,
    ShopStatus,
    ShopTable,
)
from apps.shop.models.badge_icons import BADGE_ICONS
from apps.shop.services.modifier_pricing import load_modifier_tree_by_sort_asc, min_price_minor
from apps.shop.services.shop_service import ShopService
from core.clients.redis_client import RedisClient
from core.models.identity_models import Company
from core.types import JsonObject, parse_json_object

_SNAPSHOT_KEY_PREFIX = "shop:sf:"
_TENANT_KEY_PREFIX = "shop:tenant:"
_NEGATIVE_MARKER = "none"
_ETAG_PREFIX = 'W/"shop-'


class StorefrontService:
    """Публичная витрина: резолв арендатора по Host и отдача снапшота."""

    def __init__(
        self,
        settings: ShopSettings,
        redis: RedisClient,
        shop_service: ShopService,
    ) -> None:
        self._settings: ShopSettings = settings
        self._redis: RedisClient = redis
        self._shops: ShopService = shop_service

    async def resolve_shop_by_host(self, host: str) -> Shop | None:
        """Магазин по Host заголовка: slug-витрина или активный кастомный домен."""
        hostname = host.split(":")[0].strip().lower()
        if not hostname:
            return None
        slug = await self._resolve_slug(hostname)
        if slug is None:
            return None
        shop = await Shop.get_by_slug(slug)
        if shop is None or shop.status != ShopStatus.PUBLISHED:
            return None
        return shop

    async def check_order_rate_limit(self, client_key: str) -> bool:
        """Лимит заказов с одного IP: скользящее минутное окно в Redis."""
        limit = self._settings.order_rate_limit_per_minute
        if limit <= 0:
            return True
        key = f"shop:rl:order:{client_key}"
        count = await self._redis.eval(
            """
            local n = redis.call('INCR', KEYS[1])
            if n == 1 then redis.call('EXPIRE', KEYS[1], 60) end
            return n
            """,
            1,
            key,
        )
        return isinstance(count, int) and count <= limit

    async def get_snapshot(self, slug: str) -> JsonObject | None:
        """Снапшот витрины: Redis → БД → сборка; None если витрины нет."""
        key = f"{_SNAPSHOT_KEY_PREFIX}{slug}"
        cached = await self._redis.get(key)
        if cached is not None:
            if cached == _NEGATIVE_MARKER:
                return None
            return parse_json_object(cached, "storefront snapshot")
        shop = await Shop.get_by_slug(slug)
        if shop is None or shop.status != ShopStatus.PUBLISHED:
            _ = await self._redis.set(
                key, _NEGATIVE_MARKER, ttl=self._settings.storefront_negative_ttl_seconds
            )
            return None
        snapshot = await self.build_snapshot(shop)
        _ = await self._redis.set(
            key,
            json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
            ttl=self._settings.storefront_snapshot_ttl_seconds,
        )
        return snapshot

    async def build_snapshot(self, shop: Shop) -> JsonObject:
        """Полный снапшот витрины из PostgreSQL — вход кэша и ответа API."""
        categories = await ShopCategory.list_by_shop_by_sort_asc(shop.shop_id)
        products = await ShopProduct.list_available_by_shop_by_sort_asc(shop.shop_id)
        modifier_tree = await load_modifier_tree_by_sort_asc([p.shop_product_id for p in products])
        promos = await ShopPromo.list_active_by_shop_by_priority_desc(shop.shop_id)
        tables = await ShopTable.list_by_shop_by_created_asc(shop.shop_id)
        return {
            "slug": shop.slug,
            "name": shop.name,
            "description": shop.description,
            "kind": shop.kind.value,
            "logo_file_id": shop.logo_file_id,
            "cover_file_id": shop.cover_file_id,
            "phone": shop.phone,
            "city": shop.city,
            "address": shop.address,
            "working_hours": shop.working_hours,
            "timezone": shop.timezone,
            "delivery_enabled": shop.delivery_enabled,
            "pickup_enabled": shop.pickup_enabled,
            "onsite_enabled": shop.onsite_enabled,
            "tables": [
                {"id": t.shop_table_id, "label": t.label} for t in tables
            ],
            "delivery_fee_minor": shop.delivery_fee_minor,
            "min_order_minor": shop.min_order_minor,
            "currency": shop.currency,
            "theme": shop.theme,
            "badge_defs": {
                b["key"]: {"label": b["label"], "icon_path": BADGE_ICONS.get(b["icon"], "")}
                for b in shop.badges
            },
            "promos": [
                {
                    "id": promo.shop_promo_id,
                    "name": promo.name,
                    "condition": promo.condition,
                    "action": promo.action,
                }
                for promo in promos
            ],
            "modifier_nested_groups": {
                ag.group.shop_modifier_group_id: {
                    "id": ag.group.shop_modifier_group_id,
                    "name": ag.group.name,
                    "kind": ag.group.kind.value,
                    "selection_mode": ag.group.selection_mode.value,
                    "min_selected": ag.min_selected,
                    "max_selected": ag.max_selected,
                    "price_mode": ag.group.price_mode.value,
                    "options": [
                        {
                            "id": o.shop_modifier_option_id,
                            "name": o.name,
                            "price_minor": o.price_minor,
                            "is_default": o.is_default,
                            "max_per_option": o.max_per_option,
                            "nested_group_id": o.nested_group_id,
                        }
                        for o in ag.options
                        if o.is_available
                    ],
                }
                for ag in modifier_tree.get("__nested__", [])
            },
            "categories": [
                {
                    "id": c.shop_category_id,
                    "parent_id": c.parent_id,
                    "name": c.name,
                    "sort": c.sort,
                }
                for c in categories
                if c.is_active
            ],
            "products": [
                {
                    "id": p.shop_product_id,
                    "category_id": p.category_id,
                    "name": p.name,
                    "description": p.description,
                    "portion": p.portion,
                    "badges": list(p.badges),
                    "price_minor": p.price_minor,
                    "price_from_minor": min_price_minor(
                        p, modifier_tree.get(p.shop_product_id, [])
                    ),
                    "photo_file_id": p.photo_file_id,
                    "modifier_groups": [
                        {
                            "id": ag.group.shop_modifier_group_id,
                            "name": ag.group.name,
                            "kind": ag.group.kind.value,
                            "selection_mode": ag.group.selection_mode.value,
                            "min_selected": ag.min_selected,
                            "max_selected": ag.max_selected,
                            "price_mode": ag.group.price_mode.value,
                            "options": [
                                {
                                    "id": o.shop_modifier_option_id,
                                    "name": o.name,
                                    "price_minor": o.price_minor,
                                    "is_default": o.is_default,
                                    "max_per_option": o.max_per_option,
                                    "nested_group_id": o.nested_group_id,
                                }
                                for o in ag.options
                                if o.is_available
                            ],
                        }
                        for ag in modifier_tree.get(p.shop_product_id, [])
                    ],
                }
                for p in products
            ],
        }

    async def rebuild_snapshot(self, slug: str) -> JsonObject | None:
        """Принудительная пересборка снапшота — точка вызова TaskIQ-задачи."""
        shop = await Shop.get_by_slug(slug)
        key = f"{_SNAPSHOT_KEY_PREFIX}{slug}"
        if shop is None or shop.status != ShopStatus.PUBLISHED:
            _ = await self._redis.set(
                key, _NEGATIVE_MARKER, ttl=self._settings.storefront_negative_ttl_seconds
            )
            return None
        snapshot = await self.build_snapshot(shop)
        _ = await self._redis.set(
            key,
            json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
            ttl=self._settings.storefront_snapshot_ttl_seconds,
        )
        return snapshot

    async def invalidate_snapshot(self, shop_id: str) -> None:
        """Инвалидация после мутации каталога: следующий читатель соберёт заново."""
        shop = await Shop.get_by_id(shop_id)
        if shop is None:
            return
        _ = await self._redis.delete(f"{_SNAPSHOT_KEY_PREFIX}{shop.slug}")

    def snapshot_etag(self, snapshot: JsonObject) -> str:
        """ETag снапшота — условные запросы анонимных читателей."""
        digest = hashlib.sha256(
            json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()[:16]
        return f'{_ETAG_PREFIX}{digest}"'

    async def _resolve_slug(self, hostname: str) -> str | None:
        """Host → slug: tenant-ключ Redis, мис — БД (slug-суффикс или домен)."""
        key = f"{_TENANT_KEY_PREFIX}{hostname}"
        cached = await self._redis.get(key)
        if cached is not None:
            return None if cached == _NEGATIVE_MARKER else cached
        slug = await self._resolve_slug_db(hostname)
        _ = await self._redis.set(
            key,
            slug if slug is not None else _NEGATIVE_MARKER,
            ttl=self._settings.storefront_negative_ttl_seconds
            if slug is None
            else self._settings.storefront_snapshot_ttl_seconds,
        )
        return slug

    async def _resolve_slug_db(self, hostname: str) -> str | None:
        suffix = self._settings.storefront_domain_suffix
        if suffix and hostname.endswith(f".{suffix}"):
            candidate = hostname[: -(len(suffix) + 1)]
            if candidate and "." not in candidate:
                company = await Company.by_subdomain(candidate)
                if company is not None:
                    shop = await Shop.get_published_by_company_by_updated_desc(company.company_id)
                    return None if shop is None else shop.slug
                shop = await Shop.get_by_slug(candidate)
                if shop is not None:
                    return candidate
        domain = await ShopDomain.get_by_domain(hostname)
        if domain is not None and domain.status == ShopDomainStatus.ACTIVE:
            shop = await Shop.get_by_id(domain.shop_id)
            if shop is not None:
                return shop.slug
        return None
