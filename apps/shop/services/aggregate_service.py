"""AggregateService — публичный агрегатор: поиск товаров по всем витринам.

Индекс — прямой запрос по ``shop_products`` опубликованных магазинов с
pg_trgm-индексами по name/description; пересборка задачи актуализирует
снапшоты витрин. MVP-стратегия чтения: ``ILIKE``+trigram similarity по
индексу — полного скана таблицы нет.
"""

from __future__ import annotations

from apps.shop.models import Shop, ShopProduct, ShopStatus
from apps.shop.services.storefront_service import StorefrontService
from core.pagination import OffsetPage


class AggregateService:
    """Агрегатор: каталог published-витрин и поиск по товарам."""

    def __init__(self, storefront: StorefrontService) -> None:
        self._storefront = storefront

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
        """Поиск товара по всем published-витринам: name/description + pg_trgm."""
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
        rows = await ShopProduct.objects.filter(
            shop_id__in=shop_ids,
            is_available=True,
            name__icontains=needle,
        ).offset(offset).limit(limit).all()
        total = await ShopProduct.objects.filter(
            shop_id__in=shop_ids,
            is_available=True,
            name__icontains=needle,
        ).count()
        items = [
            {
                "product_id": p.shop_product_id,
                "name": p.name,
                "description": p.description,
                "price_minor": p.price_minor,
                "photo_file_id": p.photo_file_id,
                "shop_slug": by_shop[p.shop_id].slug,
                "shop_name": by_shop[p.shop_id].name,
                "shop_kind": by_shop[p.shop_id].kind.value,
                "shop_city": by_shop[p.shop_id].city,
                "currency": by_shop[p.shop_id].currency,
            }
            for p in rows
            if p.shop_id in by_shop
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
