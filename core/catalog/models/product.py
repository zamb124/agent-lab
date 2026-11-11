"""Мастер-карточка товара (catalog_products) — единый продукт компании.

Одна строка = один ``product_id``, на который ссылаются фасеты
сервисов (``stock_products``, ``shop_products``), леджер склада и
заказы витрины. Здесь живут только общие атрибуты: имя, описание,
галерея, SKU, базовая ЕИ, вес/объём базовой единицы. Сервисный
контент поверх этих полей — ``catalog_product_overrides``; сервисные
политики — в фасетных таблицах владельцев.

``uom_id`` иммутабельна: смена базовой ЕИ под живым леджером
перетолковала бы историю количеств. ``is_archived`` глушит товар
везде (витрины убирают его из снапшотов, склад не даёт новых
документов), история и ссылки продолжают читаться.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, Q, execute_raw

from core.models.platform_model import PlatformModel
from core.pagination import CursorPage, decode_cursor, encode_cursor
from core.types import (
    JsonValue,
    SqlParameterValue,
    parse_json_object,
    require_json_object,
)

QTY_DB = "NUMERIC(20,6)"


class CatalogProduct(PlatformModel):
    """Единый товар компании. Таблица ``catalog_products`` (shared)."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "catalog_products"
        indexes: list[Index] = [
            Index(["company_id", "sku"], unique=True, where="sku IS NOT NULL"),
            Index(["company_id", "product_id"]),
        ]

    product_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=100)
    sku: str | None = DbField(default=None, max_length=128)
    name: str = DbField(max_length=300)
    description: str = DbField(default="", db_type="TEXT")
    image_file_ids: list[str] = DbField(default_factory=list, db_type="JSONB")
    """Упорядоченная галерея: ``[0]`` — обложка."""
    uom_id: str = DbField(max_length=64)
    weight: Decimal | None = DbField(default=None, db_type=QTY_DB)
    """Вес базовой ЕИ (кг)."""
    volume: Decimal | None = DbField(default=None, db_type=QTY_DB)
    """Объём базовой ЕИ — по конвенции каталога."""
    is_archived: bool = DbField(default=False)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def by_id(cls, company_id: str, product_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=company_id, product_id=product_id
        ).get_or_none()

    @classmethod
    async def found_in_company_by_ids(
        cls, company_id: str, product_ids: list[str]
    ) -> dict[str, Self]:
        """Найденные товары компании по id. Пустой список — {}. Отсутствующие id не входят."""
        if not product_ids:
            return {}
        rows = await cls.objects.filter(
            company_id=company_id, product_id__in=product_ids
        ).all()
        return {row.product_id: row for row in rows}

    @classmethod
    async def by_sku(cls, company_id: str, sku: str) -> Self | None:
        return await cls.objects.filter(company_id=company_id, sku=sku).get_or_none()

    @classmethod
    async def list_ids_by_text_icontains(
        cls, company_id: str, text: str
    ) -> list[str]:
        """Id товаров компании, чьи ``name``/``sku`` содержат ``text``. Пустой text — []."""
        if text == "":
            return []
        rows = await cls.objects.filter(company_id=company_id).filter(
            Q(name__icontains=text) | Q(sku__icontains=text)
        ).all()
        return [row.product_id for row in rows]

    @classmethod
    async def list_page_by_created_desc(
        cls,
        company_id: str,
        *,
        query: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
        cursor: str | None = None,
    ) -> CursorPage[CatalogProduct]:
        """Keyset-страница ``(created_at, product_id) DESC`` + текстовый фильтр.

        ``query`` — подстрока по name/sku (ILIKE → pg_trgm GIN).
        Курсор — opaque по ``(created_at, product_id)``; ``None`` — первая
        страница, невалидный — ``ValueError``.
        """
        params: list[SqlParameterValue] = [company_id]
        where = ["company_id = $1"]

        def add(value: SqlParameterValue) -> str:
            params.append(value)
            return f"${len(params)}"

        if not include_archived:
            where.append("NOT is_archived")
        if query:
            like = add(f"%{query}%")
            where.append(f"(name ILIKE {like} OR sku ILIKE {like})")
        if cursor is not None:
            cursor_ts, cursor_id = decode_cursor(cursor)
            ts_param = add(cursor_ts)
            id_param = add(cursor_id)
            where.append(
                f"(created_at, product_id) < ({ts_param}::timestamptz, {id_param})"
            )
        limit_param = add(limit + 1)
        fetched = await execute_raw(
            "SELECT row_to_json(catalog_products) AS item "
            + "FROM catalog_products WHERE "
            + " AND ".join(where)
            + f" ORDER BY created_at DESC, product_id DESC LIMIT {limit_param}",
            params,
            using="shared",
        )
        parsed = [_catalog_product_from_row(row) for row in fetched]
        has_more = len(parsed) > limit
        page = parsed[:limit]
        next_cursor: str | None = None
        if has_more and len(page) > 0:
            last = page[-1]
            next_cursor = encode_cursor(last.created_at, last.product_id)
        return CursorPage[CatalogProduct](items=page, next_cursor=next_cursor, has_more=has_more)

    @classmethod
    async def suggest_by_text_by_score_desc(
        cls, company_id: str, text: str, *, limit: int
    ) -> list[CatalogProduct]:
        """Кандидаты дедупа по имени/SKU: подстрока или триграммное совпадение.

        Ранжирование ``word_similarity`` — опечатки выше случайных
        вхождений; фильтр накрыт GIN-индексом ``name``.
        """
        needle = text.strip()
        if not needle:
            return []
        like = (
            needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        rows = await execute_raw(
            "SELECT row_to_json(t) AS item FROM ("
            + " SELECT catalog_products.*,"
            + " GREATEST("
            + "  word_similarity($2::text, name),"
            + "  word_similarity($2::text, COALESCE(sku, ''))"
            + " ) AS score"
            + " FROM catalog_products"
            + " WHERE company_id = $1 AND NOT is_archived"
            + "   AND (name ILIKE $3 ESCAPE '\\'"
            + "        OR sku ILIKE $3 ESCAPE '\\'"
            + "        OR name % $2::text)"
            + " ORDER BY score DESC, name ASC"
            + " LIMIT $4"
            + ") t",
            [company_id, needle, f"%{like}%", limit],
            using="shared",
        )
        return [_catalog_product_from_row(row) for row in rows]


def _catalog_product_from_row(row: JsonValue) -> CatalogProduct:
    """Строка ``row_to_json(...)`` → CatalogProduct."""
    parsed = require_json_object(row, "catalog_product")
    raw_item = parsed["item"]
    if isinstance(raw_item, str):
        payload = parse_json_object(raw_item, "catalog_product")
    else:
        payload = require_json_object(raw_item, "catalog_product")
    return CatalogProduct.model_validate(payload)
