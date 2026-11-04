"""Таблица shop_products — блюдо каталога заведения."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, execute_raw

from apps.shop.models.enums import ShopAllergen, ShopMeasureUnit
from apps.shop.models.nutrition import ShopNutrition
from core.models.platform_model import PlatformModel
from core.types import require_json_object


class ShopProduct(PlatformModel):
    """Позиция каталога заведения. Таблица ``shop_products``.

    Поиск агрегатора идёт по ``name`` + ``description`` (pg_trgm GIN-индексы
    создаются миграцией). ``price_minor`` — минорные единицы ``Shop.currency``.
    Похожие названия — ``find_similar_by_name_by_score_desc`` по GIN ``name``.
    """

    __database_alias__: ClassVar[str | None] = "shop"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "shop_products"
        indexes: list[Index] = [
            Index(["shop_id", "sort"]),
            Index(["shop_id", "is_available"]),
        ]

    shop_product_id: str = DbField(db_pk=True, max_length=64)
    shop_id: str = DbField(max_length=64)
    name: str = DbField(max_length=300)
    description: str = DbField(default="", db_type="TEXT")
    measure: int | None = DbField(default=None, ge=0)
    measure_unit: ShopMeasureUnit = DbField(default=ShopMeasureUnit.G)
    ingredients: list[str] = DbField(default_factory=list, db_type="JSONB")
    nutrition: ShopNutrition | None = DbField(default=None, db_type="JSONB")
    allergens: list[ShopAllergen] = DbField(default_factory=list, db_type="JSONB")
    badges: list[str] = DbField(default_factory=list, db_type="JSONB")
    price_minor: int = DbField(ge=0)
    photo_file_id: str | None = DbField(default=None, max_length=64)
    is_available: bool = DbField(default=True)
    ai_unverified: bool = DbField(default=False)
    similar_shop_product_id: str | None = DbField(default=None, max_length=64)
    sort: int = DbField(default=0)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def get_by_id(cls, shop_product_id: str) -> Self | None:
        return await cls.objects.filter(shop_product_id=shop_product_id).get_or_none()

    @classmethod
    async def list_by_shop_by_sort_asc(cls, shop_id: str) -> list[Self]:
        """Товары заведения по sort ASC. Предела нет."""
        return await cls.objects.filter(shop_id=shop_id).order_by("sort").all()

    @classmethod
    async def list_available_by_shop_by_sort_asc(cls, shop_id: str) -> list[Self]:
        """Доступные к заказу товары каталога."""
        return (
            await cls.objects.filter(shop_id=shop_id, is_available=True)
            .order_by("sort")
            .all()
        )

    @classmethod
    async def list_many_by_ids(cls, product_ids: list[str]) -> list[Self]:
        if not product_ids:
            return []
        return await cls.objects.filter(shop_product_id__in=product_ids).all()

    @classmethod
    async def list_incomplete_by_shop_by_sort_asc(cls, shop_id: str) -> list[Self]:
        """Блюда без фото или без КБЖУ — вход массового enrich."""
        rows = await cls.list_by_shop_by_sort_asc(shop_id)
        return [
            row
            for row in rows
            if row.photo_file_id is None or row.nutrition is None or not row.ingredients
        ]

    @classmethod
    async def create(cls, product: Self) -> Self:
        return await cls.objects.create(instance=product)

    @classmethod
    async def next_sort_by_sort_desc(cls, shop_id: str) -> int:
        row = await cls.objects.filter(shop_id=shop_id).order_by("-sort").first()
        return row.sort + 1 if row is not None else 0

    @classmethod
    async def list_by_similar_unordered(cls, similar_shop_product_id: str) -> list[Self]:
        """Блюда с пометкой «похоже на» ``similar_shop_product_id``. Порядка и предела нет."""
        return await cls.objects.filter(
            similar_shop_product_id=similar_shop_product_id
        ).all()

    @classmethod
    async def find_similar_by_name_by_score_desc(
        cls,
        shop_id: str,
        name: str,
        *,
        exclude_shop_product_id: str | None = None,
        threshold: float,
        limit: int = 5,
    ) -> list[tuple[Self, float]]:
        """Блюда с ``similarity(name, query) >= threshold``, убывание score."""
        needle = name.strip()
        if not needle:
            return []
        exclude_clause = ""
        params: list[str | float | int] = [shop_id, needle, threshold, limit]
        if exclude_shop_product_id is not None:
            exclude_clause = "AND shop_product_id <> $5"
            params.append(exclude_shop_product_id)
        rows = await execute_raw(
            f"""
            SELECT shop_product_id, similarity(name, $2::text) AS score
            FROM shop_products
            WHERE shop_id = $1
              AND similarity(name, $2::text) >= $3
              {exclude_clause}
            ORDER BY score DESC, shop_product_id ASC
            LIMIT $4
            """,
            params,
            using="shop",
        )
        if not rows:
            return []
        scores: dict[str, float] = {}
        for row in rows:
            parsed = require_json_object(row, "shop_product_similarity")
            row_product_id = parsed["shop_product_id"]
            row_score = parsed["score"]
            if not isinstance(row_product_id, str) or not isinstance(row_score, float):
                raise RuntimeError(f"shop_product_similarity row has invalid shape: {parsed}")
            scores[row_product_id] = row_score
        ids = list(scores)
        found = await cls.list_many_by_ids(ids)
        by_id = {p.shop_product_id: p for p in found}
        return [(by_id[pid], scores[pid]) for pid in ids if pid in by_id]
