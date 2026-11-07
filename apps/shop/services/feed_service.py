"""FeedService — витринная лента: полки и баннеры магазина.

Полки описывают композицию ленты (что показать и как), баннеры —
сторис-карточки верха. Источники полок: ручная выборка, зеркало
категории или вычисляемая секция (новинки/хиты/возвраты/апсейл) —
``resolve_shelf_products`` собирает id'шники для снапшота.
"""

from __future__ import annotations

from datetime import timedelta

from apps.shop.models import (
    ShopBackInStock,
    ShopBanner,
    ShopCategory,
    ShopOrder,
    ShopOrderItem,
    ShopOrderStatus,
    ShopProduct,
    ShopShelf,
)
from apps.shop.models.api import (
    ShopBannerCreateRequest,
    ShopBannerUpdateRequest,
    ShopOrderItemSelection,
    ShopPersonalResponse,
    ShopPersonalUsualItem,
    ShopShelfCreateRequest,
    ShopShelfUpdateRequest,
)
from apps.shop.models.common import new_id
from apps.shop.models.enums import (
    ShopShelfKind,
    ShopShelfLayout,
    ShopShelfPlacement,
)
from apps.shop.services.shop_service import ShopService
from core.errors.boundary import (
    PlatformConflictError,
    PlatformNotFoundError,
)
from core.types import JsonValue
from core.utils.time import utcnow

_HITS_WINDOW_DAYS = 30
_NEW_LIMIT = 8
_USUAL_ORDERS_LIMIT = 50
_USUAL_LIMIT = 10


class FeedService:
    """Полки и баннеры витринной ленты магазина."""

    def __init__(self, shop_service: ShopService) -> None:
        self._shops: ShopService = shop_service

    # --- Полки ---

    async def list_shelves(self, company_id: str, shop_id: str) -> list[ShopShelf]:
        _ = await self._shops.get_shop(company_id, shop_id)
        return await ShopShelf.list_by_shop_by_sort_asc(shop_id)

    async def create_shelf(
        self, company_id: str, shop_id: str, payload: ShopShelfCreateRequest
    ) -> ShopShelf:
        _ = await self._shops.get_shop(company_id, shop_id)
        kind = ShopShelfKind(payload.kind)
        await self._validate_shelf_source(shop_id, kind, payload.product_ids, payload.category_id)
        now = utcnow()
        shelf = ShopShelf(
            shop_shelf_id=new_id("shopshelf"),
            shop_id=shop_id,
            kind=kind,
            layout=ShopShelfLayout(payload.layout),
            placement=ShopShelfPlacement(payload.placement),
            title=payload.title,
            subtitle=payload.subtitle,
            product_ids=list(payload.product_ids),
            category_id=payload.category_id,
            limit=payload.limit,
            sort=await ShopShelf.next_sort_by_sort_desc(shop_id),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        return await ShopShelf.create(shelf)

    async def update_shelf(
        self,
        company_id: str,
        shop_id: str,
        shelf_id: str,
        payload: ShopShelfUpdateRequest,
    ) -> ShopShelf:
        _ = await self._shops.get_shop(company_id, shop_id)
        shelf = await ShopShelf.get_by_id(shelf_id)
        if shelf is None or shelf.shop_id != shop_id:
            raise PlatformNotFoundError("Shelf not found", error_code="shelf_not_found")
        patch: dict[str, JsonValue] = payload.model_dump(exclude_unset=True)
        if isinstance(patch.get("layout"), str):
            patch["layout"] = ShopShelfLayout(patch["layout"])
        if isinstance(patch.get("placement"), str):
            patch["placement"] = ShopShelfPlacement(patch["placement"])
        product_ids = list(payload.product_ids) if payload.product_ids is not None else list(shelf.product_ids)
        category_id = payload.category_id if "category_id" in patch else shelf.category_id
        await self._validate_shelf_source(shop_id, shelf.kind, product_ids, category_id)
        for field, value in patch.items():
            setattr(shelf, field, value)
        shelf.updated_at = utcnow()
        _ = await shelf.save()
        return shelf

    async def reorder_shelves(
        self, company_id: str, shop_id: str, shelf_ids: list[str]
    ) -> None:
        _ = await self._shops.get_shop(company_id, shop_id)
        shelves = await ShopShelf.list_by_shop_by_sort_asc(shop_id)
        by_id = {s.shop_shelf_id: s for s in shelves}
        if len(set(shelf_ids)) != len(shelf_ids) or set(shelf_ids) != set(by_id):
            raise PlatformConflictError(
                "Reorder must include every shelf exactly once",
                error_code="shelves_reorder_incomplete",
            )
        now = utcnow()
        for sort, shelf_id in enumerate(shelf_ids):
            shelf = by_id[shelf_id]
            if shelf.sort != sort:
                shelf.sort = sort
                shelf.updated_at = now
                _ = await shelf.save()

    async def delete_shelf(self, company_id: str, shop_id: str, shelf_id: str) -> None:
        _ = await self._shops.get_shop(company_id, shop_id)
        shelf = await ShopShelf.get_by_id(shelf_id)
        if shelf is None or shelf.shop_id != shop_id:
            raise PlatformNotFoundError("Shelf not found", error_code="shelf_not_found")
        _ = await shelf.delete()

    async def _validate_shelf_source(
        self,
        shop_id: str,
        kind: ShopShelfKind,
        product_ids: list[str],
        category_id: str | None,
    ) -> None:
        """Источник полки обязан существовать: товары — у manual/upsell,
        категория — у category. Вычисляемые полки источника не требуют."""
        if kind in (ShopShelfKind.MANUAL, ShopShelfKind.UPSELL):
            products = await ShopProduct.list_many_by_ids(product_ids)
            existing = {p.shop_product_id for p in products if p.shop_id == shop_id}
            missing = [pid for pid in product_ids if pid not in existing]
            if missing:
                raise PlatformNotFoundError(
                    "Product not found", error_code="product_not_found"
                )
        if kind == ShopShelfKind.CATEGORY:
            if not category_id:
                raise PlatformConflictError(
                    "category_id is required for category shelf",
                    error_code="shelf_category_required",
                )
            category = await ShopCategory.get_by_id(category_id)
            if category is None or category.shop_id != shop_id:
                raise PlatformNotFoundError(
                    "Category not found", error_code="category_not_found"
                )

    async def resolve_shelf_products(self, shop_id: str, shelf: ShopShelf) -> list[str]:
        """Идентификаторы товаров полки для снапшота — источник по ``kind``.

        ``usual`` — персональная: снапшот анонимный, id'шники резолвит
        endpoint ``/personal``; здесь полка возвращает пустой набор и
        рендерится только после авторизации.
        """
        if shelf.kind == ShopShelfKind.MANUAL or shelf.kind == ShopShelfKind.UPSELL:
            return list(shelf.product_ids)[: shelf.limit]
        if shelf.kind == ShopShelfKind.CATEGORY:
            products = await ShopProduct.list_by_category_by_sort_asc(
                shop_id, shelf.category_id
            )
            return [p.shop_product_id for p in products][: shelf.limit]
        if shelf.kind == ShopShelfKind.NEW:
            products = await ShopProduct.list_available_by_shop_by_sort_asc(shop_id)
            fresh = sorted(products, key=lambda p: p.created_at, reverse=True)
            return [p.shop_product_id for p in fresh[: shelf.limit]]
        if shelf.kind == ShopShelfKind.HITS:
            return await self._hits_product_ids(shop_id, shelf.limit)
        if shelf.kind == ShopShelfKind.COMEBACK:
            products = await ShopProduct.list_by_shop_by_sort_asc(shop_id)
            back = [p for p in products if not p.is_available]
            return [p.shop_product_id for p in back[: shelf.limit]]
        if shelf.kind == ShopShelfKind.USUAL:
            return []
        return []

    async def _hits_product_ids(self, shop_id: str, limit: int) -> list[str]:
        """Хиты — топ product_id по числу проданных позиций за 30 дней.

        Агрегируется в снапшоте (per rebuild, не на запрос): заказы
        не-cancelled магазина → сумма ``qty`` по ``product_id``.
        """
        since = utcnow() - timedelta(days=_HITS_WINDOW_DAYS)
        orders = await ShopOrder.objects.filter(
            shop_id=shop_id, created_at__gte=since
        ).all()
        live = [o for o in orders if o.status != ShopOrderStatus.CANCELLED]
        if not live:
            return []
        items = await ShopOrderItem.list_many_by_order_ids(
            [o.shop_order_id for o in live]
        )
        totals: dict[str, int] = {}
        for item in items:
            totals[item.product_id] = totals.get(item.product_id, 0) + item.qty
        return [
            pid
            for pid, _ in sorted(totals.items(), key=lambda kv: -kv[1])[:limit]
        ]

    # --- Баннеры ---

    async def list_banners(self, company_id: str, shop_id: str) -> list[ShopBanner]:
        _ = await self._shops.get_shop(company_id, shop_id)
        return await ShopBanner.list_by_shop_by_sort_asc(shop_id)

    async def create_banner(
        self, company_id: str, shop_id: str, payload: ShopBannerCreateRequest
    ) -> ShopBanner:
        _ = await self._shops.get_shop(company_id, shop_id)
        self._validate_banner_link(payload.link)
        now = utcnow()
        banner = ShopBanner(
            shop_banner_id=new_id("shopbanner"),
            shop_id=shop_id,
            title=payload.title,
            subtitle=payload.subtitle,
            image_file_id=payload.image_file_id,
            link=payload.link,
            window=dict(payload.window),
            sort=await ShopBanner.next_sort_by_sort_desc(shop_id),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        return await ShopBanner.create(banner)

    async def update_banner(
        self,
        company_id: str,
        shop_id: str,
        banner_id: str,
        payload: ShopBannerUpdateRequest,
    ) -> ShopBanner:
        _ = await self._shops.get_shop(company_id, shop_id)
        banner = await ShopBanner.get_by_id(banner_id)
        if banner is None or banner.shop_id != shop_id:
            raise PlatformNotFoundError("Banner not found", error_code="banner_not_found")
        if payload.link is not None:
            self._validate_banner_link(payload.link)
        patch: dict[str, JsonValue] = payload.model_dump(exclude_unset=True)
        for field, value in patch.items():
            setattr(banner, field, value)
        banner.updated_at = utcnow()
        _ = await banner.save()
        return banner

    async def reorder_banners(
        self, company_id: str, shop_id: str, banner_ids: list[str]
    ) -> None:
        _ = await self._shops.get_shop(company_id, shop_id)
        banners = await ShopBanner.list_by_shop_by_sort_asc(shop_id)
        by_id = {b.shop_banner_id: b for b in banners}
        if len(set(banner_ids)) != len(banner_ids) or set(banner_ids) != set(by_id):
            raise PlatformConflictError(
                "Reorder must include every banner exactly once",
                error_code="banners_reorder_incomplete",
            )
        now = utcnow()
        for sort, banner_id in enumerate(banner_ids):
            banner = by_id[banner_id]
            if banner.sort != sort:
                banner.sort = sort
                banner.updated_at = now
                _ = await banner.save()

    async def delete_banner(self, company_id: str, shop_id: str, banner_id: str) -> ShopBanner:
        _ = await self._shops.get_shop(company_id, shop_id)
        banner = await ShopBanner.get_by_id(banner_id)
        if banner is None or banner.shop_id != shop_id:
            raise PlatformNotFoundError("Banner not found", error_code="banner_not_found")
        _ = await banner.delete()
        return banner

    @staticmethod
    def _validate_banner_link(link: str) -> None:
        """Deeplink баннера: ``product:``/``category:``/``shelf:``/``url:`` или пусто."""
        if not link:
            return
        prefix, sep, _ = link.partition(":")
        if not sep or prefix not in ("product", "category", "shelf", "url"):
            raise PlatformConflictError(
                "Banner link must start with product:/category:/shelf:/url:",
                error_code="banner_link_invalid",
            )

    # --- «Сообщить о появлении» ---

    async def subscribe_back_in_stock(
        self, shop_id: str, product_id: str, customer_id: str
    ) -> bool:
        """Подписка покупателя на возврат товара; False — товар доступен.

        Товар ищется по ``shop_id`` опубликованной витрины: чужой и
        доступный к заказу товар подписки не принимает.
        """
        product = await ShopProduct.get_by_id(product_id)
        if product is None or product.shop_id != shop_id:
            raise PlatformNotFoundError("Product not found", error_code="product_not_found")
        if product.is_available:
            return False
        existing = await ShopBackInStock.find_by_product_and_customer(
            product_id, customer_id
        )
        if existing is not None:
            return True
        _ = await ShopBackInStock.create(
            ShopBackInStock(
                shop_back_in_stock_id=new_id("shopbis"),
                product_id=product_id,
                customer_id=customer_id,
                created_at=utcnow(),
            )
        )
        return True

    async def pending_back_in_stock(self, product_id: str) -> list[ShopBackInStock]:
        return await ShopBackInStock.list_pending_by_product(product_id)

    # --- Персонализация покупателя (/personal) ---

    async def personal(self, shop_id: str, customer_id: str) -> ShopPersonalResponse:
        """«Как всегда» и подписки покупателя конкретной витрины.

        ``usual`` — топ товаров по сумме штук в неотменённых заказах
        витрины; ``selections`` повторяет выбор модификаторов из
        последнего заказа с этой позицией. ``back_in_stock_ids`` —
        активные подписки «сообщить о появлении» этого магазина.
        """
        orders = await ShopOrder.list_by_customer_shop_by_created_desc(
            customer_id, shop_id, limit=_USUAL_ORDERS_LIMIT
        )
        live = [o for o in orders if o.status != ShopOrderStatus.CANCELLED]
        order_index = {o.shop_order_id: idx for idx, o in enumerate(live)}
        counts: dict[str, int] = {}
        latest: dict[str, ShopOrderItem] = {}
        if live:
            items = await ShopOrderItem.list_many_by_order_ids(
                [o.shop_order_id for o in live]
            )
            for item in items:
                counts[item.product_id] = counts.get(item.product_id, 0) + item.qty
                prev = latest.get(item.product_id)
                if prev is None or order_index[item.order_id] < order_index[prev.order_id]:
                    latest[item.product_id] = item
        shelves = await ShopShelf.list_by_shop_by_sort_asc(shop_id)
        limit = next(
            (
                s.limit
                for s in shelves
                if s.kind is ShopShelfKind.USUAL and s.is_active
            ),
            _USUAL_LIMIT,
        )
        top = sorted(
            counts.items(),
            key=lambda kv: (-kv[1], order_index[latest[kv[0]].order_id]),
        )[:limit]
        products = await ShopProduct.list_many_by_ids([pid for pid, _ in top])
        existing = {p.shop_product_id for p in products if p.shop_id == shop_id}
        usual: list[ShopPersonalUsualItem] = []
        for pid, count in top:
            if pid not in existing:
                continue
            selections: list[ShopOrderItemSelection] = []
            for m in latest[pid].modifiers:
                option_id = m.get("option_id")
                qty = m.get("qty", 1)
                if isinstance(option_id, str) and isinstance(qty, int | float):
                    selections.append(
                        ShopOrderItemSelection(option_id=option_id, qty=int(qty))
                    )
            usual.append(
                ShopPersonalUsualItem(
                    product_id=pid, count=count, selections=selections
                )
            )
        subs = await ShopBackInStock.list_by_customer(customer_id)
        sub_product_ids = [s.product_id for s in subs]
        sub_products = (
            await ShopProduct.list_many_by_ids(sub_product_ids) if sub_product_ids else []
        )
        own = {p.shop_product_id for p in sub_products if p.shop_id == shop_id}
        return ShopPersonalResponse(
            favorite_ids=[],
            usual=usual,
            back_in_stock_ids=[pid for pid in sub_product_ids if pid in own],
        )
