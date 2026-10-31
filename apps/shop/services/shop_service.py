"""ShopService — сценарии витрины: CRUD магазина, slug, публикация, домены."""

from __future__ import annotations

from apps.shop.config import ShopSettings
from apps.shop.models.badge_icons import BADGE_ICONS, DEFAULT_SHOP_BADGES
from apps.shop.models import (
    ModifierGroupKind,
    ModifierPriceMode,
    ModifierSelectionMode,
    Shop,
    ShopCategory,
    ShopDomain,
    ShopModifierGroup,
    ShopModifierOption,
    ShopProduct,
    ShopProductModifierGroup,
    ShopPromo,
    ShopStatus,
)
from apps.shop.models.api import (
    ShopBadge,
    ShopCategoryCreateRequest,
    ShopCategoryUpdateRequest,
    ShopCreateRequest,
    ShopModifierGroupCreateRequest,
    ShopModifierGroupUpdateRequest,
    ShopModifierOptionCreateRequest,
    ShopModifierOptionUpdateRequest,
    ShopProductCreateRequest,
    ShopProductsImportRequest,
    ShopProductUpdateRequest,
    ShopPromoCreateRequest,
    ShopPromoUpdateRequest,
    ShopUpdateRequest,
)
from apps.shop.models.common import DOMAIN_PATTERN, SLUG_PATTERN, new_id
from apps.shop.models.enums import PromoStacking
from core.errors.boundary import (
    PlatformBoundaryError,
    PlatformConflictError,
    PlatformNotFoundError,
)
from core.types import JsonValue
from core.utils.time import utcnow


class ShopService:
    """Владелец магазина и его каталога: сценарии tenant'а ``Company``."""

    def __init__(self, settings: ShopSettings) -> None:
        self._settings: ShopSettings = settings

    async def list_shops(self, company_id: str) -> list[Shop]:
        return await Shop.list_alive_by_company_by_updated_desc(company_id)

    async def create_shop(self, company_id: str, user_id: str, payload: ShopCreateRequest) -> Shop:
        slug = self._validate_slug(payload.slug)
        if await Shop.slug_exists(slug):
            raise PlatformConflictError(
                f"Slug {slug} is already taken", error_code="shop_slug_taken"
            )
        now = utcnow()
        shop = Shop(
            shop_id=new_id("shop"),
            company_id=company_id,
            slug=slug,
            kind=payload.kind,
            name=payload.name,
            badges=[dict(b) for b in DEFAULT_SHOP_BADGES],
            created_by_user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        return await Shop.create(shop)

    async def get_shop(self, company_id: str, shop_id: str) -> Shop:
        shop = await Shop.get_by_id(shop_id)
        if shop is None or shop.company_id != company_id:
            raise PlatformNotFoundError("Shop not found", error_code="shop_not_found")
        return shop

    async def update_shop(self, company_id: str, shop_id: str, payload: ShopUpdateRequest) -> Shop:
        shop = await self.get_shop(company_id, shop_id)
        patch: dict[str, JsonValue] = payload.model_dump(exclude_unset=True)
        _ = patch.pop("shop_id", None)
        if "badges" in patch:
            _ = patch.pop("badges")
            shop.badges = self._normalize_badges(payload.badges or [])
            await self._check_badge_references(shop)
        for field, value in patch.items():
            setattr(shop, field, value)
        shop.updated_at = utcnow()
        _ = await shop.save()
        return shop

    @staticmethod
    def _normalize_badges(badges: list[ShopBadge]) -> list[dict[str, str]]:
        """Приводит набор меток к канону: уникальные ключи, иконка из каталога.

        Пустой ``key`` получает автогенерацию ``badge_N``.
        """
        normalized: list[dict[str, str]] = []
        seen: set[str] = set()
        for badge in badges:
            label = badge.label.strip()
            icon = badge.icon
            if icon not in BADGE_ICONS or not label:
                raise PlatformNotFoundError("Badge icon not found", error_code="badge_icon_not_found")
            key = badge.key
            if not key:
                n = len(seen) + 1
                while f"badge_{n}" in seen:
                    n += 1
                key = f"badge_{n}"
            if key in seen:
                raise PlatformConflictError("Badge key is duplicated", error_code="badge_key_duplicated")
            seen.add(key)
            normalized.append({"key": key, "label": label, "icon": icon})
        return normalized

    async def _check_badge_references(self, shop: Shop) -> None:
        keys = {b["key"] for b in shop.badges}
        products = await ShopProduct.objects.filter(shop_id=shop.shop_id).all()
        orphans = [p.name for p in products if any(b not in keys for b in p.badges)]
        if orphans:
            raise PlatformConflictError(
                f"Badges still referenced by products: {', '.join(orphans[:3])}",
                error_code="badge_in_use",
            )

    async def publish_shop(self, company_id: str, shop_id: str) -> Shop:
        """Публикация: витрина появляется в снапшотах и агрегаторе."""
        shop = await self.get_shop(company_id, shop_id)
        if shop.status == ShopStatus.PUBLISHED:
            return shop
        if not shop.name:
            raise PlatformConflictError(
                "Shop name is required before publishing",
                error_code="shop_incomplete",
            )
        shop.status = ShopStatus.PUBLISHED
        shop.published_at = utcnow()
        shop.updated_at = utcnow()
        _ = await shop.save()
        return shop

    async def suspend_shop(self, company_id: str, shop_id: str) -> Shop:
        shop = await self.get_shop(company_id, shop_id)
        shop.status = ShopStatus.SUSPENDED
        shop.updated_at = utcnow()
        _ = await shop.save()
        return shop

    async def delete_shop(self, company_id: str, shop_id: str) -> Shop:
        shop = await self.get_shop(company_id, shop_id)
        shop.deleted_at = utcnow()
        shop.status = ShopStatus.DRAFT
        shop.updated_at = utcnow()
        _ = await shop.save()
        return shop

    # --- Каталог ---

    async def list_categories(self, company_id: str, shop_id: str) -> list[ShopCategory]:
        _ = await self.get_shop(company_id, shop_id)
        return await ShopCategory.list_by_shop_by_sort_asc(shop_id)

    async def create_category(
        self, company_id: str, shop_id: str, payload: ShopCategoryCreateRequest
    ) -> ShopCategory:
        _ = await self.get_shop(company_id, shop_id)
        now = utcnow()
        category = ShopCategory(
            shop_category_id=new_id("shopcat"),
            shop_id=shop_id,
            name=payload.name,
            sort=await ShopCategory.next_sort_by_sort_desc(shop_id),
            created_at=now,
            updated_at=now,
        )
        return await ShopCategory.create(category)

    async def update_category(
        self, company_id: str, shop_id: str, category_id: str, payload: ShopCategoryUpdateRequest
    ) -> ShopCategory:
        _ = await self.get_shop(company_id, shop_id)
        category = await ShopCategory.get_by_id(category_id)
        if category is None or category.shop_id != shop_id:
            raise PlatformNotFoundError("Category not found", error_code="category_not_found")
        patch: dict[str, JsonValue] = payload.model_dump(exclude_unset=True)
        _ = patch.pop("shop_id", None)
        _ = patch.pop("shop_category_id", None)
        for field, value in patch.items():
            setattr(category, field, value)
        category.updated_at = utcnow()
        _ = await category.save()
        return category

    async def reorder_categories(
        self, company_id: str, shop_id: str, category_ids: list[str]
    ) -> None:
        """Перестановка категорий меню: ids получают отсортированные
        sort-значения в новом порядке."""
        _ = await self.get_shop(company_id, shop_id)
        categories = await ShopCategory.list_by_shop_by_sort_asc(shop_id)
        by_id = {c.shop_category_id: c for c in categories}
        if any(cid not in by_id for cid in category_ids):
            raise PlatformNotFoundError("Category not found", error_code="category_not_found")
        ordered = [by_id[cid] for cid in category_ids]
        sorts = sorted(c.sort for c in ordered)
        for category, sort in zip(ordered, sorts, strict=True):
            if category.sort != sort:
                category.sort = sort
                category.updated_at = utcnow()
                _ = await category.save()

    async def delete_category(self, company_id: str, shop_id: str, category_id: str) -> None:
        _ = await self.get_shop(company_id, shop_id)
        category = await ShopCategory.get_by_id(category_id)
        if category is None or category.shop_id != shop_id:
            raise PlatformNotFoundError("Category not found", error_code="category_not_found")
        _ = await category.delete()

    async def list_products(self, company_id: str, shop_id: str) -> list[ShopProduct]:
        _ = await self.get_shop(company_id, shop_id)
        return await ShopProduct.list_by_shop_by_sort_asc(shop_id)

    async def create_product(
        self, company_id: str, shop_id: str, payload: ShopProductCreateRequest
    ) -> ShopProduct:
        shop = await self.get_shop(company_id, shop_id)
        if payload.category_id is not None:
            category = await ShopCategory.get_by_id(payload.category_id)
            if category is None or category.shop_id != shop_id:
                raise PlatformNotFoundError("Category not found", error_code="category_not_found")
        now = utcnow()
        product = ShopProduct(
            shop_product_id=new_id("shopprod"),
            shop_id=shop_id,
            category_id=payload.category_id,
            name=payload.name,
            description=payload.description,
            portion=payload.portion,
            badges=self._validate_product_badges(shop, payload.badges),
            price_minor=payload.price_minor,
            photo_file_id=payload.photo_file_id,
            sort=await ShopProduct.next_sort_by_sort_desc(shop_id, payload.category_id),
            created_at=now,
            updated_at=now,
        )
        return await ShopProduct.create(product)

    async def import_products(
        self, company_id: str, shop_id: str, payload: ShopProductsImportRequest
    ) -> int:
        """Пакетное создание товаров одной командой — импорт меню из текста."""
        _ = await self.get_shop(company_id, shop_id)
        if payload.category_id is not None:
            category = await ShopCategory.get_by_id(payload.category_id)
            if category is None or category.shop_id != shop_id:
                raise PlatformNotFoundError("Category not found", error_code="category_not_found")
        now = utcnow()
        base_sort = await ShopProduct.next_sort_by_sort_desc(shop_id, payload.category_id)
        products = [
            ShopProduct(
                shop_product_id=new_id("shopprod"),
                shop_id=shop_id,
                category_id=payload.category_id,
                name=item.name,
                description=item.description,
                portion=item.portion,
                price_minor=item.price_minor,
                photo_file_id=None,
                sort=base_sort + index,
                created_at=now,
                updated_at=now,
            )
            for index, item in enumerate(payload.items)
        ]
        created = await ShopProduct.objects.bulk_create(products)
        return len(created)

    async def update_product(
        self, company_id: str, shop_id: str, product_id: str, payload: ShopProductUpdateRequest
    ) -> ShopProduct:
        shop = await self.get_shop(company_id, shop_id)
        product = await ShopProduct.get_by_id(product_id)
        if product is None or product.shop_id != shop_id:
            raise PlatformNotFoundError("Product not found", error_code="product_not_found")
        patch: dict[str, JsonValue] = payload.model_dump(exclude_unset=True)
        _ = patch.pop("shop_id", None)
        _ = patch.pop("shop_product_id", None)
        if "badges" in patch:
            patch["badges"] = self._validate_product_badges(shop, payload.badges or [])
        category_patch = patch.get("category_id")
        if category_patch is not None:
            if not isinstance(category_patch, str):
                raise PlatformBoundaryError(
                    "category_id must be a string", error_code="product_invalid"
                )
            category = await ShopCategory.get_by_id(category_patch)
            if category is None or category.shop_id != shop_id:
                raise PlatformNotFoundError("Category not found", error_code="category_not_found")
        for field, value in patch.items():
            setattr(product, field, value)
        product.updated_at = utcnow()
        _ = await product.save()
        return product

    @staticmethod
    def _validate_product_badges(shop: Shop, badges: list[str]) -> list[str]:
        """Ключи меток позиции должны существовать в наборе магазина."""
        keys = {b["key"] for b in shop.badges}
        if any(b not in keys for b in badges):
            raise PlatformNotFoundError("Badge not found", error_code="badge_not_found")
        return list(badges)

    async def reorder_products(self, company_id: str, shop_id: str, product_ids: list[str]) -> None:
        """Перестановка позиций внутри списка: ids получают отсортированные
        sort-значения в новом порядке — позиции вне списка не трогаем."""
        _ = await self.get_shop(company_id, shop_id)
        products = await ShopProduct.list_by_shop_by_sort_asc(shop_id)
        by_id = {p.shop_product_id: p for p in products}
        if any(pid not in by_id for pid in product_ids):
            raise PlatformNotFoundError("Product not found", error_code="product_not_found")
        ordered = [by_id[pid] for pid in product_ids]
        sorts = sorted(p.sort for p in ordered)
        for product, sort in zip(ordered, sorts, strict=True):
            if product.sort != sort:
                product.sort = sort
                product.updated_at = utcnow()
                _ = await product.save()

    async def delete_product(self, company_id: str, shop_id: str, product_id: str) -> None:
        _ = await self.get_shop(company_id, shop_id)
        product = await ShopProduct.get_by_id(product_id)
        if product is None or product.shop_id != shop_id:
            raise PlatformNotFoundError("Product not found", error_code="product_not_found")
        _ = await product.delete()

    # --- Модификаторы ---

    async def _get_modifier_group(self, shop_id: str, group_id: str) -> ShopModifierGroup:
        group = await ShopModifierGroup.get_by_id(group_id)
        if group is None or group.shop_id != shop_id:
            raise PlatformNotFoundError(
                "Modifier group not found", error_code="modifier_group_not_found"
            )
        return group

    async def _get_modifier_option(self, shop_id: str, option_id: str) -> ShopModifierOption:
        option = await ShopModifierOption.get_by_id(option_id)
        if option is None:
            raise PlatformNotFoundError(
                "Modifier option not found", error_code="modifier_not_found"
            )
        _ = await self._get_modifier_group(shop_id, option.group_id)
        return option

    async def list_modifier_groups_by_sort_asc(
        self, company_id: str, shop_id: str
    ) -> list[tuple[ShopModifierGroup, list[ShopModifierOption], list[str]]]:
        _ = await self.get_shop(company_id, shop_id)
        groups = await ShopModifierGroup.list_by_shop_by_sort_asc(shop_id)
        if not groups:
            return []
        group_ids = [g.shop_modifier_group_id for g in groups]
        options = (
            await ShopModifierOption.objects.filter(group_id__in=group_ids).order_by("sort").all()
        )
        by_group: dict[str, list[ShopModifierOption]] = {}
        for o in options:
            by_group.setdefault(o.group_id, []).append(o)
        links = await ShopProductModifierGroup.list_by_groups(group_ids)
        products_by_group: dict[str, list[str]] = {}
        for link in links:
            products_by_group.setdefault(link.group_id, []).append(link.product_id)
        return [
            (
                g,
                by_group.get(g.shop_modifier_group_id, []),
                products_by_group.get(g.shop_modifier_group_id, []),
            )
            for g in groups
        ]

    async def create_modifier_group(
        self, company_id: str, shop_id: str, payload: ShopModifierGroupCreateRequest
    ) -> ShopModifierGroup:
        _ = await self.get_shop(company_id, shop_id)
        now = utcnow()
        group = ShopModifierGroup(
            shop_modifier_group_id=new_id("shopmodgrp"),
            shop_id=shop_id,
            name=payload.name,
            description=payload.description,
            kind=ModifierGroupKind(payload.kind),
            selection_mode=ModifierSelectionMode(payload.selection_mode),
            min_selected=payload.min_selected,
            max_selected=payload.max_selected,
            price_mode=ModifierPriceMode(payload.price_mode),
            created_at=now,
            updated_at=now,
        )
        return await ShopModifierGroup.create(group)

    async def update_modifier_group(
        self,
        company_id: str,
        shop_id: str,
        group_id: str,
        payload: ShopModifierGroupUpdateRequest,
    ) -> ShopModifierGroup:
        _ = await self.get_shop(company_id, shop_id)
        group = await self._get_modifier_group(shop_id, group_id)
        patch: dict[str, JsonValue] = payload.model_dump(exclude_unset=True)
        _ = patch.pop("shop_id", None)
        _ = patch.pop("shop_modifier_group_id", None)
        if "selection_mode" in patch and patch["selection_mode"] is not None:
            patch["selection_mode"] = ModifierSelectionMode(patch["selection_mode"])
        for field, value in patch.items():
            setattr(group, field, value)
        group.updated_at = utcnow()
        _ = await group.save()
        return group

    async def delete_modifier_group(self, company_id: str, shop_id: str, group_id: str) -> None:
        _ = await self.get_shop(company_id, shop_id)
        group = await self._get_modifier_group(shop_id, group_id)
        links = await ShopProductModifierGroup.objects.filter(group_id=group_id).all()
        for link in links:
            _ = await link.delete()
        options = await ShopModifierOption.list_by_group_by_sort_asc(group_id)
        for option in options:
            _ = await option.delete()
        _ = await group.delete()

    async def create_modifier_option(
        self,
        company_id: str,
        shop_id: str,
        group_id: str,
        payload: ShopModifierOptionCreateRequest,
    ) -> ShopModifierOption:
        _ = await self.get_shop(company_id, shop_id)
        _ = await self._get_modifier_group(shop_id, group_id)
        if payload.nested_group_id:
            _ = await self._get_modifier_group(shop_id, payload.nested_group_id)
            if payload.nested_group_id == group_id:
                raise PlatformConflictError(
                    "Group cannot nest itself", error_code="modifiers_invalid"
                )
        existing = await ShopModifierOption.list_by_group_by_sort_asc(group_id)
        now = utcnow()
        option = ShopModifierOption(
            shop_modifier_option_id=new_id("shopmodopt"),
            group_id=group_id,
            name=payload.name,
            price_minor=payload.price_minor,
            is_default=payload.is_default,
            max_per_option=payload.max_per_option,
            nested_group_id=payload.nested_group_id,
            external_id=payload.external_id,
            sort=(max((o.sort for o in existing), default=-1) + 1),
            created_at=now,
            updated_at=now,
        )
        return await ShopModifierOption.create(option)

    async def update_modifier_option(
        self,
        company_id: str,
        shop_id: str,
        option_id: str,
        payload: ShopModifierOptionUpdateRequest,
    ) -> ShopModifierOption:
        _ = await self.get_shop(company_id, shop_id)
        option = await self._get_modifier_option(shop_id, option_id)
        patch: dict[str, JsonValue] = payload.model_dump(exclude_unset=True)
        _ = patch.pop("shop_id", None)
        _ = patch.pop("shop_modifier_option_id", None)
        for field, value in patch.items():
            setattr(option, field, value)
        option.updated_at = utcnow()
        _ = await option.save()
        return option

    async def delete_modifier_option(self, company_id: str, shop_id: str, option_id: str) -> None:
        _ = await self.get_shop(company_id, shop_id)
        option = await self._get_modifier_option(shop_id, option_id)
        _ = await option.delete()

    async def attach_modifier_group(
        self,
        company_id: str,
        shop_id: str,
        product_id: str,
        group_id: str,
        min_selected: int | None,
        max_selected: int | None,
    ) -> None:
        _ = await self.get_shop(company_id, shop_id)
        product = await ShopProduct.get_by_id(product_id)
        if product is None or product.shop_id != shop_id:
            raise PlatformNotFoundError("Product not found", error_code="product_not_found")
        _ = await self._get_modifier_group(shop_id, group_id)
        existing = await ShopProductModifierGroup.get_link(product_id, group_id)
        if existing is not None:
            existing.min_selected = min_selected
            existing.max_selected = max_selected
            _ = await existing.save()
            return
        links = await ShopProductModifierGroup.list_by_product_by_sort_asc(product_id)
        _ = await ShopProductModifierGroup.create(
            ShopProductModifierGroup(
                product_id=product_id,
                group_id=group_id,
                sort=(max((link.sort for link in links), default=-1) + 1),
                min_selected=min_selected,
                max_selected=max_selected,
            )
        )

    async def detach_modifier_group(
        self,
        company_id: str,
        shop_id: str,
        product_id: str,
        group_id: str,
    ) -> None:
        _ = await self.get_shop(company_id, shop_id)
        link = await ShopProductModifierGroup.get_link(product_id, group_id)
        if link is None:
            raise PlatformNotFoundError(
                "Modifier group is not attached",
                error_code="modifier_link_not_found",
            )
        _ = await self._get_modifier_group(shop_id, group_id)
        _ = await link.delete()

    # --- Акции ---

    async def _get_promo(self, shop_id: str, promo_id: str) -> ShopPromo:
        promo = await ShopPromo.get_by_id(promo_id)
        if promo is None or promo.shop_id != shop_id:
            raise PlatformNotFoundError("Promo not found", error_code="promo_not_found")
        return promo

    async def list_promos_by_sort_asc(self, company_id: str, shop_id: str) -> list[ShopPromo]:
        _ = await self.get_shop(company_id, shop_id)
        return await ShopPromo.list_by_shop_by_sort_asc(shop_id)

    async def create_promo(
        self, company_id: str, shop_id: str, payload: ShopPromoCreateRequest
    ) -> ShopPromo:
        _ = await self.get_shop(company_id, shop_id)
        now = utcnow()
        sort = payload.sort
        if sort is None:
            sort = await ShopPromo.next_sort(shop_id)
        promo = ShopPromo(
            shop_promo_id=new_id("shoppromo"),
            shop_id=shop_id,
            name=payload.name,
            is_active=payload.is_active,
            sort=sort,
            priority=payload.priority,
            stacking=PromoStacking(payload.stacking),
            window=payload.window,
            condition=payload.condition,
            action=payload.action,
            created_at=now,
            updated_at=now,
        )
        return await ShopPromo.create(promo)

    async def update_promo(
        self,
        company_id: str,
        shop_id: str,
        promo_id: str,
        payload: ShopPromoUpdateRequest,
    ) -> ShopPromo:
        _ = await self.get_shop(company_id, shop_id)
        promo = await self._get_promo(shop_id, promo_id)
        patch: dict[str, JsonValue] = payload.model_dump(exclude_unset=True)
        _ = patch.pop("shop_id", None)
        _ = patch.pop("shop_promo_id", None)
        if "stacking" in patch and patch["stacking"] is not None:
            patch["stacking"] = PromoStacking(patch["stacking"])
        for field, value in patch.items():
            setattr(promo, field, value)
        promo.updated_at = utcnow()
        _ = await promo.save()
        return promo

    async def delete_promo(self, company_id: str, shop_id: str, promo_id: str) -> None:
        _ = await self.get_shop(company_id, shop_id)
        promo = await self._get_promo(shop_id, promo_id)
        _ = await promo.delete()

    # --- Домены ---

    async def add_domain(self, company_id: str, shop_id: str, domain: str) -> ShopDomain:
        shop = await self.get_shop(company_id, shop_id)
        normalized = domain.strip().lower()
        if not DOMAIN_PATTERN.match(normalized):
            raise PlatformConflictError("Invalid domain name", error_code="domain_invalid")
        if normalized.endswith(self._settings.storefront_domain_suffix):
            raise PlatformConflictError(
                "Platform subdomains are connected automatically by slug",
                error_code="domain_platform_owned",
            )
        existing = await ShopDomain.get_by_domain(normalized)
        if existing is not None:
            raise PlatformConflictError("Domain is already connected", error_code="domain_taken")
        existing_for_shop = await ShopDomain.get_by_shop(shop.shop_id)
        if existing_for_shop is not None:
            raise PlatformConflictError(
                "Shop already has a domain — disconnect the current one first",
                error_code="domain_limit",
            )
        now = utcnow()
        record = ShopDomain(
            shop_domain_id=new_id("shopdom"),
            shop_id=shop.shop_id,
            company_id=company_id,
            domain=normalized,
            created_at=now,
            updated_at=now,
        )
        return await ShopDomain.create(record)

    async def remove_domain(self, company_id: str, shop_id: str, domain_id: str) -> None:
        _ = await self.get_shop(company_id, shop_id)
        record = await ShopDomain.objects.filter(shop_domain_id=domain_id).get_or_none()
        if record is None or record.shop_id != shop_id:
            raise PlatformNotFoundError("Domain not found", error_code="domain_not_found")
        _ = await record.delete()

    # --- Внутреннее ---

    def _validate_slug(self, slug: str) -> str:
        normalized = slug.strip().lower()
        if not SLUG_PATTERN.match(normalized):
            raise PlatformConflictError(
                "Slug: lowercase letters, digits and dashes, 3-40 characters",
                error_code="slug_invalid",
            )
        if normalized in self._settings.reserved_slugs:
            raise PlatformConflictError(
                "This slug is reserved by the platform", error_code="slug_reserved"
            )
        return normalized
