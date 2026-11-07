"""AggregateService — публичный агрегатор: поиск товаров по всем витринам.

Индекс — прямой запрос по ``shop_products`` опубликованных магазинов с
pg_trgm-индексами по name/description; пересборка задачи актуализирует
снапшоты витрин. Стратегия чтения: ILIKE-подстрока или триграммное
совпадение ``%`` (устойчиво к опечаткам), ранжирование по
``word_similarity`` — индекс используется и для фильтра, и для ILIKE.
"""

from __future__ import annotations

from oxyde import execute_raw

from apps.shop.models import Shop, ShopStatus
from apps.shop.models.badge_icons import BADGE_ICONS
from apps.shop.services.storefront_service import StorefrontService
from core.clients.geo_client import GeoClient
from core.clients.service_client import ServiceClient, ServiceClientError
from core.models.identity_models import SYSTEM_COMPANY_ID
from core.pagination import OffsetPage
from core.types import JsonObject, JsonValue

_SEARCH_WHERE = """
    FROM shop_products
    WHERE is_available
      AND shop_id IN ({in_clause})
      AND (
          name ILIKE $2 ESCAPE '\\'
          OR COALESCE(description, '') ILIKE $2 ESCAPE '\\'
          OR name % $1::text
          OR name <% $1::text
          OR COALESCE(description, '') % $1::text
          OR COALESCE(description, '') <% $1::text
      )
"""

_SEARCH_SELECT = (
    """
    SELECT shop_id, shop_product_id, name, description, portion, badges, price_minor, photo_file_id,
           GREATEST(
               word_similarity($1::text, name),
               word_similarity($1::text, COALESCE(description, '')) * 0.5
           ) AS score
    """
    + _SEARCH_WHERE
    + """
    ORDER BY score DESC, name ASC
    LIMIT {limit_param} OFFSET {offset_param}
"""
)

_SEARCH_COUNT = "SELECT count(*) AS total " + _SEARCH_WHERE


def _like_pattern(needle: str) -> str:
    """ILIKE-паттерн подстроки: экранирует ``%``/``_``/``\\`` в запросе."""
    escaped = (
        needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    return f"%{escaped}%"


def _badge_keys(row: dict[str, JsonValue]) -> list[str]:
    """Колонка ``badges`` — JSON-массив строк; прочие формы отбрасываются."""
    value = row.get("badges")
    if not isinstance(value, list):
        return []
    return [key for key in value if isinstance(key, str)]


class AggregateService:
    """Агрегатор: каталог published-витрин и поиск по товарам."""

    def __init__(
        self, storefront: StorefrontService, service_client: ServiceClient
    ) -> None:
        self._storefront: StorefrontService = storefront
        self._service_client: ServiceClient = service_client

    async def address_suggest(
        self, query: str, *, lat: float | None = None, lng: float | None = None
    ) -> JsonObject:
        """Автокомплит адреса на /market: geo-справочник без зоны.

        Агрегатор кросс-компанийный — GeoClient идёт от system-компании.
        Деградация: geo недоступен → пустой список, страница откатывается
        на `/aggregate/geocode` (Enter без выбора подсказки).
        """
        try:
            hits = await GeoClient(
                http=self._service_client, company_id=SYSTEM_COMPANY_ID
            ).suggest(q=query, lat=lat, lng=lng, limit=8)
        except ServiceClientError:
            return {"items": [], "geo_unavailable": True}
        return {
            "items": [
                {
                    "display_name": h.display_name,
                    "lat": h.lat,
                    "lng": h.lng,
                    "city": h.city,
                    "street": h.street,
                    "housenumber": h.housenumber,
                }
                for h in hits.items
            ]
        }

    async def list_shops(self, *, city: str | None = None) -> list[Shop]:
        shops = await Shop.list_published()
        if city is not None:
            needle = city.strip().lower()
            shops = [s for s in shops if s.city.strip().lower() == needle]
        return shops

    async def search_products(
        self,
        query: str,
        *,
        kind: str | None = None,
        city: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> OffsetPage[dict[str, object]]:
        """Поиск товара по всем published-витринам: name/description + pg_trgm.

        Подстрока ILIKE ловит точные вхождения, оператор ``%`` — опечатки;
        результат ранжируется по ``word_similarity`` (имя весомее описания).
        """
        needle = query.strip()
        if not needle:
            return OffsetPage(items=[], total=0, limit=limit, offset=offset)
        shops = await self.list_shops(city=city)
        if kind is not None:
            shops = [s for s in shops if s.kind.value == kind]
        shop_ids = [s.shop_id for s in shops]
        if not shop_ids:
            return OffsetPage(items=[], total=0, limit=limit, offset=offset)
        by_shop = {s.shop_id: s for s in shops}
        like = _like_pattern(needle)
        in_clause = ", ".join(f"${i + 3}" for i in range(len(shop_ids)))
        tail = len(shop_ids) + 3
        rows = await execute_raw(
            _SEARCH_SELECT.format(
                in_clause=in_clause,
                limit_param=f"${tail}",
                offset_param=f"${tail + 1}",
            ),
            [needle, like, *shop_ids, limit, offset],
            using="shop",
        )
        count_rows = await execute_raw(
            _SEARCH_COUNT.format(in_clause=in_clause),
            [needle, like, *shop_ids],
            using="shop",
        )
        total: int = count_rows[0]["total"] if count_rows else 0
        badge_defs = {
            sid: {
                b["key"]: {"label": b["label"], "icon_path": BADGE_ICONS.get(b["icon"], "")}
                for b in s.badges
            }
            for sid, s in by_shop.items()
        }
        items: list[dict[str, object]] = [
            {
                "product_id": row["shop_product_id"],
                "name": row["name"],
                "description": row["description"],
                "portion": row["portion"],
                "badges": [
                    badge_defs[row["shop_id"]][key]
                    for key in _badge_keys(row)
                    if key in badge_defs[row["shop_id"]]
                ],
                "price_minor": row["price_minor"],
                "photo_file_id": row["photo_file_id"],
                "shop_slug": by_shop[row["shop_id"]].slug,
                "shop_name": by_shop[row["shop_id"]].name,
                "shop_kind": by_shop[row["shop_id"]].kind.value,
                "shop_city": by_shop[row["shop_id"]].city,
                "currency": by_shop[row["shop_id"]].currency,
            }
            for row in rows
            if row["shop_id"] in by_shop
        ]
        return OffsetPage(items=items, total=total, limit=limit, offset=offset)

    async def rebuild(self, shop_id: str | None) -> int:
        """Пересборка поискового слоя: прогрев снапшотов витрин. Идемпотентно."""
        if shop_id is not None:
            shop = await Shop.get_by_id(shop_id)
            shops = [shop] if shop is not None and shop.status == ShopStatus.PUBLISHED else []
        else:
            shops = await Shop.list_published()
        rebuilt = 0
        for shop in shops:
            if await self._storefront.rebuild_snapshot(shop.slug) is not None:
                rebuilt += 1
        return rebuilt
