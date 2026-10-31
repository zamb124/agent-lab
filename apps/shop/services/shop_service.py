"""ShopService — сценарии витрины: CRUD магазина, slug, публикация, домены."""

from __future__ import annotations

from apps.shop.config import ShopSettings
from apps.shop.models import (
    Shop,
    ShopCategory,
    ShopDomain,
    ShopProduct,
    ShopStatus,
)
from apps.shop.models.api import (
    ShopCategoryCreateRequest,
    ShopCategoryUpdateRequest,
    ShopCreateRequest,
    ShopProductCreateRequest,
    ShopProductUpdateRequest,
    ShopUpdateRequest,
)
from apps.shop.models.common import DOMAIN_PATTERN, SLUG_PATTERN, new_id
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.utils.time import utcnow


class ShopService:
    """Владелец магазина и его каталога: сценарии tenant'а ``Company``."""

    def __init__(self, settings: ShopSettings) -> None:
        self._settings = settings

    async def list_shops(self, company_id: str) -> list[Shop]:
        return await Shop.list_alive_by_company(company_id)

    async def create_shop(
        self, company_id: str, user_id: str, payload: ShopCreateRequest
    ) -> Shop:
        slug = self._validate_slug(payload.slug)
        if await Shop.slug_exists(slug):
            raise PlatformConflictError(
                f"Адрес {slug} уже занят", error_code="shop_slug_taken"
            )
        now = utcnow()
        shop = Shop(
            shop_id=new_id("shop"),
            company_id=company_id,
            slug=slug,
            kind=payload.kind,
            name=payload.name,
            created_by_user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        return await Shop.create(shop)

    async def get_shop(self, company_id: str, shop_id: str) -> Shop:
        shop = await Shop.get_by_id(shop_id)
        if shop is None or shop.company_id != company_id:
            raise PlatformNotFoundError("Магазин не найден", error_code="shop_not_found")
        return shop

    async def update_shop(
        self, company_id: str, shop_id: str, payload: ShopUpdateRequest
    ) -> Shop:
        shop = await self.get_shop(company_id, shop_id)
        patch = payload.model_dump(exclude_unset=True)
        patch.pop("shop_id", None)
        for field, value in patch.items():
            setattr(shop, field, value)
        shop.updated_at = utcnow()
        await shop.save()
        return shop

    async def publish_shop(self, company_id: str, shop_id: str) -> Shop:
        """Публикация: витрина появляется в снапшотах и агрегаторе."""
        shop = await self.get_shop(company_id, shop_id)
        if shop.status == ShopStatus.PUBLISHED:
            return shop
        if not shop.name:
            raise PlatformConflictError(
                "Заполните название магазина перед публикацией",
                error_code="shop_incomplete",
            )
        shop.status = ShopStatus.PUBLISHED
        shop.published_at = utcnow()
        shop.updated_at = utcnow()
        await shop.save()
        return shop

    async def suspend_shop(self, company_id: str, shop_id: str) -> Shop:
        shop = await self.get_shop(company_id, shop_id)
        shop.status = ShopStatus.SUSPENDED
        shop.updated_at = utcnow()
        await shop.save()
        return shop

    async def delete_shop(self, company_id: str, shop_id: str) -> Shop:
        shop = await self.get_shop(company_id, shop_id)
        shop.deleted_at = utcnow()
        shop.status = ShopStatus.DRAFT
        shop.updated_at = utcnow()
        await shop.save()
        return shop

    # --- Каталог ---

    async def list_categories(self, company_id: str, shop_id: str) -> list[ShopCategory]:
        await self.get_shop(company_id, shop_id)
        return await ShopCategory.list_by_shop(shop_id)

    async def create_category(
        self, company_id: str, shop_id: str, payload: ShopCategoryCreateRequest
    ) -> ShopCategory:
        await self.get_shop(company_id, shop_id)
        now = utcnow()
        category = ShopCategory(
            shop_category_id=new_id("shopcat"),
            shop_id=shop_id,
            name=payload.name,
            sort=await ShopCategory.next_sort(shop_id),
            created_at=now,
            updated_at=now,
        )
        return await ShopCategory.create(category)

    async def update_category(
        self, company_id: str, shop_id: str, category_id: str, payload: ShopCategoryUpdateRequest
    ) -> ShopCategory:
        await self.get_shop(company_id, shop_id)
        category = await ShopCategory.get_by_id(category_id)
        if category is None or category.shop_id != shop_id:
            raise PlatformNotFoundError("Категория не найдена", error_code="category_not_found")
        patch = payload.model_dump(exclude_unset=True)
        patch.pop("shop_id", None)
        patch.pop("shop_category_id", None)
        for field, value in patch.items():
            setattr(category, field, value)
        category.updated_at = utcnow()
        await category.save()
        return category

    async def delete_category(
        self, company_id: str, shop_id: str, category_id: str
    ) -> None:
        await self.get_shop(company_id, shop_id)
        category = await ShopCategory.get_by_id(category_id)
        if category is None or category.shop_id != shop_id:
            raise PlatformNotFoundError("Категория не найдена", error_code="category_not_found")
        await category.delete()

    async def list_products(self, company_id: str, shop_id: str) -> list[ShopProduct]:
        await self.get_shop(company_id, shop_id)
        return await ShopProduct.list_by_shop(shop_id)

    async def create_product(
        self, company_id: str, shop_id: str, payload: ShopProductCreateRequest
    ) -> ShopProduct:
        await self.get_shop(company_id, shop_id)
        if payload.category_id is not None:
            category = await ShopCategory.get_by_id(payload.category_id)
            if category is None or category.shop_id != shop_id:
                raise PlatformNotFoundError(
                    "Категория не найдена", error_code="category_not_found"
                )
        now = utcnow()
        product = ShopProduct(
            shop_product_id=new_id("shopprod"),
            shop_id=shop_id,
            category_id=payload.category_id,
            name=payload.name,
            description=payload.description,
            price_minor=payload.price_minor,
            photo_file_id=payload.photo_file_id,
            sort=await ShopProduct.next_sort(shop_id, payload.category_id),
            created_at=now,
            updated_at=now,
        )
        return await ShopProduct.create(product)

    async def update_product(
        self, company_id: str, shop_id: str, product_id: str, payload: ShopProductUpdateRequest
    ) -> ShopProduct:
        await self.get_shop(company_id, shop_id)
        product = await ShopProduct.get_by_id(product_id)
        if product is None or product.shop_id != shop_id:
            raise PlatformNotFoundError("Товар не найден", error_code="product_not_found")
        patch = payload.model_dump(exclude_unset=True)
        patch.pop("shop_id", None)
        patch.pop("shop_product_id", None)
        if "category_id" in patch and patch["category_id"] is not None:
            category = await ShopCategory.get_by_id(patch["category_id"])
            if category is None or category.shop_id != shop_id:
                raise PlatformNotFoundError(
                    "Категория не найдена", error_code="category_not_found"
                )
        for field, value in patch.items():
            setattr(product, field, value)
        product.updated_at = utcnow()
        await product.save()
        return product

    async def delete_product(
        self, company_id: str, shop_id: str, product_id: str
    ) -> None:
        await self.get_shop(company_id, shop_id)
        product = await ShopProduct.get_by_id(product_id)
        if product is None or product.shop_id != shop_id:
            raise PlatformNotFoundError("Товар не найден", error_code="product_not_found")
        await product.delete()

    # --- Домены ---

    async def add_domain(
        self, company_id: str, shop_id: str, domain: str
    ) -> ShopDomain:
        shop = await self.get_shop(company_id, shop_id)
        normalized = domain.strip().lower()
        if not DOMAIN_PATTERN.match(normalized):
            raise PlatformConflictError(
                "Некорректное имя домена", error_code="domain_invalid"
            )
        if normalized.endswith(self._settings.storefront_domain_suffix):
            raise PlatformConflictError(
                "Поддомены платформы подключаются автоматически по slug",
                error_code="domain_platform_owned",
            )
        existing = await ShopDomain.get_by_domain(normalized)
        if existing is not None:
            raise PlatformConflictError(
                "Домен уже подключён", error_code="domain_taken"
            )
        existing_for_shop = await ShopDomain.get_by_shop(shop.shop_id)
        if existing_for_shop is not None:
            raise PlatformConflictError(
                "У магазина уже есть домен — сначала отключите текущий",
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

    async def remove_domain(
        self, company_id: str, shop_id: str, domain_id: str
    ) -> None:
        await self.get_shop(company_id, shop_id)
        record = await ShopDomain.objects.filter(shop_domain_id=domain_id).get_or_none()
        if record is None or record.shop_id != shop_id:
            raise PlatformNotFoundError("Домен не найден", error_code="domain_not_found")
        await record.delete()

    # --- Внутреннее ---

    def _validate_slug(self, slug: str) -> str:
        normalized = slug.strip().lower()
        if not SLUG_PATTERN.match(normalized):
            raise PlatformConflictError(
                "Slug: строчные латинские буквы, цифры и дефис, 3–40 символов",
                error_code="slug_invalid",
            )
        if normalized in self._settings.reserved_slugs:
            raise PlatformConflictError(
                "Этот адрес зарезервирован платформой", error_code="slug_reserved"
            )
        return normalized
