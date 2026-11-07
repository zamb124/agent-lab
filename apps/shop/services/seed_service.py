"""Сервис демо-сида: разворачивает эталонные витрины ``DEMO_TEMPLATES``.

Вызывается задачей ``shop_seed_demo_company`` (очередь ``shop``) при
инициализации новой компании и командой досева ``shop/demos/seed``.
Идемпотентен: PK всех сущностей детерминированы, витрина-шаблон
пропускается, если строка ``demo:{tpl}:{company_id}`` существует —
живая или soft-deleted (решение владельца удалить пример уважается).
Правки владельца внутри уже посеянной витрины не затираются: сид
только INSERT, ничего не обновляет.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from pathlib import Path

from oxyde.exceptions import UniqueViolationError

from apps.shop.config import ShopSettings
from apps.shop.events import SHOP_SHOP_CREATED, publish_shop_event
from apps.shop.models.banner import ShopBanner
from apps.shop.models.category import ShopCategory
from apps.shop.models.common import SLUG_PATTERN
from apps.shop.models.enums import (
    ModifierPriceMode,
    ShopDeliveryType,
    ShopOrderStatus,
    ShopStatus,
)
from apps.shop.models.loyalty import ShopLoyaltyProgram
from apps.shop.models.modifier_group import ShopModifierGroup
from apps.shop.models.modifier_option import ShopModifierOption
from apps.shop.models.order import ShopOrder
from apps.shop.models.order_feedback import ShopOrderFeedback
from apps.shop.models.order_item import ShopOrderItem
from apps.shop.models.product import ShopProduct
from apps.shop.models.product_modifier_group import ShopProductModifierGroup
from apps.shop.models.promo import ShopPromo
from apps.shop.models.shelf import ShopShelf
from apps.shop.models.shop import Shop
from apps.shop.models.table import ShopTable
from apps.shop.seed import DEMO_TEMPLATES
from apps.shop.seed.spec import (
    DemoCategorySpec,
    DemoModifierGroupSpec,
    DemoOrderSpec,
    DemoProductSpec,
    DemoShopSpec,
)
from core.files.create_spec import (
    FileCreateSpec,
    FilePostCreate,
    FileSourceKind,
    FileSourceRef,
)
from core.files.retention import FileRetentionKind, FileRetentionSpec
from core.files.service import FilesService
from core.logging import get_logger
from core.models.identity_models import Company
from core.types import JsonObject, JsonValue
from core.utils.time import utcnow

logger = get_logger(__name__)

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "seed" / "assets"

# Цепочка статусов до конечного: индекс статуса = сколько записей
# status_history сверх ``new@created_at`` (длина history_minutes в спеке).
_ORDER_CHAIN: dict[ShopDeliveryType, tuple[ShopOrderStatus, ...]] = {
    ShopDeliveryType.DELIVERY: (
        ShopOrderStatus.NEW,
        ShopOrderStatus.ACCEPTED,
        ShopOrderStatus.PREPARING,
        ShopOrderStatus.DELIVERING,
        ShopOrderStatus.DONE,
    ),
    ShopDeliveryType.PICKUP: (
        ShopOrderStatus.NEW,
        ShopOrderStatus.ACCEPTED,
        ShopOrderStatus.PREPARING,
        ShopOrderStatus.DONE,
    ),
    ShopDeliveryType.ONSITE: (
        ShopOrderStatus.NEW,
        ShopOrderStatus.ACCEPTED,
        ShopOrderStatus.PREPARING,
        ShopOrderStatus.DONE,
    ),
}


def _sha(value: str, length: int) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:length]


def _child_id(tpl_key: str, h16: str, etype: str, key: str) -> str:
    """Детерминированный PK дочерней сущности шаблона (≤ 64 символов)."""
    return f"demo:{tpl_key}:{h16}:{etype}:{key}"


def _as_str(value: JsonValue) -> str:
    """Ссылка в JSONB-спеке промо — всегда str; иное — сломанная спека."""
    if not isinstance(value, str):
        raise ValueError(f"seed spec ref must be str, got {type(value).__name__}")
    return value


class ShopSeedService:
    """Разворачивает ``DemoShopSpec`` в строки каталога магазина."""

    def __init__(self, settings: ShopSettings, files_service: FilesService) -> None:
        self._settings: ShopSettings = settings
        self._files_service: FilesService = files_service

    async def seed_company(self, *, company: Company, owner_user_id: str) -> JsonObject:
        """Сеет все ``DEMO_TEMPLATES`` компании; возвращает статистику по шаблонам."""
        results: dict[str, str] = {}
        for tpl in DEMO_TEMPLATES:
            results[tpl.key] = await self._seed_template(company, tpl, owner_user_id)
        logger.info(
            "shop.seed.company_done",
            company_id=company.company_id,
            results=results,
        )
        return {"templates": results}

    async def _seed_template(
        self, company: Company, tpl: DemoShopSpec, owner_user_id: str
    ) -> str:
        shop_id = f"demo:{tpl.key}:{company.company_id}"
        existing = await Shop.get_by_id_with_deleted(shop_id)
        if existing is not None:
            return "exists" if existing.deleted_at is None else "deleted"

        cid = company.company_id
        h16 = _sha(cid, 16)
        slug = await self._pick_slug(tpl, company)
        now = utcnow()
        cover_file_id = await self._upload_photo(
            shop_id=shop_id, product_id=None, tpl_key=tpl.key, photo=tpl.cover_photo
        )
        shop = Shop(
            shop_id=shop_id,
            company_id=cid,
            slug=slug,
            kind=tpl.kind,
            name=tpl.name,
            description=tpl.description,
            cover_file_id=cover_file_id,
            phone=tpl.phone,
            city=tpl.city,
            address=tpl.address,
            lat=tpl.lat,
            lng=tpl.lng,
            timezone=tpl.timezone,
            working_hours=dict(tpl.working_hours),
            delivery_enabled=tpl.delivery_enabled,
            pickup_enabled=tpl.pickup_enabled,
            onsite_enabled=tpl.onsite_enabled,
            delivery_zone=dict(tpl.delivery_zone),
            delivery_fee_minor=tpl.delivery_fee_minor,
            min_order_minor=tpl.min_order_minor,
            prep_minutes=tpl.prep_minutes,
            courier_mode=tpl.courier_mode,
            theme=dict(tpl.theme),
            features=dict(tpl.features),
            badges=[dict(b) for b in tpl.badges],
            demo_template=tpl.key,
            created_by_user_id=owner_user_id,
            created_at=now,
            updated_at=now,
        )
        try:
            _ = await Shop.create(shop)
        except UniqueViolationError:
            return "exists"
        await publish_shop_event(
            SHOP_SHOP_CREATED, shop_id, slug, ShopStatus.DRAFT, cid
        )

        cat_ids = await self._seed_categories(shop_id, tpl.key, h16, tpl.categories)
        group_ids, option_ids = await self._seed_modifiers(shop_id, h16, tpl)
        prod_ids = await self._seed_products(shop_id, h16, tpl, cat_ids)
        await self._attach_modifiers(shop_id, tpl, prod_ids, group_ids)
        await self._seed_promos(shop_id, h16, tpl, prod_ids, cat_ids)
        table_ids = await self._seed_tables(shop_id, h16, tpl)
        shelf_ids = await self._seed_shelves(shop_id, h16, tpl, prod_ids, cat_ids)
        await self._seed_banners(shop_id, h16, tpl, prod_ids, cat_ids, shelf_ids)
        await self._seed_orders(
            shop_id, h16, tpl, prod_ids, group_ids, option_ids, table_ids
        )
        await self._seed_loyalty(tpl.key, h16, shop_id, tpl)
        return "created"

    async def _pick_slug(self, tpl: DemoShopSpec, company: Company) -> str:
        cid = company.company_id
        h8 = _sha(cid, 8)
        candidates: list[str] = []
        subdomain = (company.subdomain or "").strip().lower()
        if subdomain:
            candidates.append(f"{subdomain}-{tpl.key}"[:40].strip("-"))
        candidates.append(f"{tpl.key}-{h8}")
        candidates.extend(f"{tpl.key}-{h8}-{i}" for i in range(2, 11))
        for slug in candidates:
            if not SLUG_PATTERN.match(slug):
                continue
            if slug in self._settings.reserved_slugs:
                continue
            if not await Shop.slug_exists(slug):
                return slug
        raise ValueError(
            f"seed: no free slug for template {tpl.key!r} in company {cid!r}"
        )

    async def _upload_photo(
        self, *, shop_id: str, product_id: str | None, tpl_key: str, photo: str
    ) -> str:
        path = _ASSETS_DIR / tpl_key / photo
        data = path.read_bytes()  # FileNotFoundError — спека и ассеты рассинхронны
        spec = FileCreateSpec(
            source_kind=FileSourceKind.SHOP_PRODUCT,
            source_ref=FileSourceRef(shop_id=shop_id, shop_product_id=product_id),
            retention=FileRetentionSpec(kind=FileRetentionKind.SHOP_PRODUCT),
            post_create=FilePostCreate(is_public=True),
            metadata={"seed_template": tpl_key, "seed_photo": photo},
        )
        record = await self._files_service.create(
            spec, data, original_name=photo, content_type="image/jpeg"
        )
        return record.file_id

    async def _seed_categories(
        self, shop_id: str, tpl_key: str, h16: str, specs: tuple[DemoCategorySpec, ...]
    ) -> dict[str, str]:
        ids: dict[str, str] = {}
        now = utcnow()

        async def walk(
            nodes: tuple[DemoCategorySpec, ...], parent_id: str | None
        ) -> None:
            for sort, spec in enumerate(nodes):
                cat_id = _child_id(tpl_key, h16, "ct", spec.key)
                if await ShopCategory.get_by_id(cat_id) is None:
                    _ = await ShopCategory.create(
                        ShopCategory(
                            shop_category_id=cat_id,
                            shop_id=shop_id,
                            parent_id=parent_id,
                            name=spec.name,
                            sort=sort,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                ids[spec.key] = cat_id
                await walk(spec.children, cat_id)

        await walk(specs, None)
        return ids

    async def _seed_modifiers(
        self, shop_id: str, h16: str, tpl: DemoShopSpec
    ) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
        """Группы → опции (nested_group_id резолвится по ключу группы)."""
        now = utcnow()
        group_ids: dict[str, str] = {}
        for sort, spec in enumerate(tpl.modifier_groups):
            group_id = _child_id(tpl.key, h16, "mg", spec.key)
            group_ids[spec.key] = group_id
            if await ShopModifierGroup.get_by_id(group_id) is not None:
                continue
            _ = await ShopModifierGroup.create(
                ShopModifierGroup(
                    shop_modifier_group_id=group_id,
                    shop_id=shop_id,
                    name=spec.name,
                    kind=spec.kind,
                    selection_mode=spec.selection_mode,
                    min_selected=spec.min_selected,
                    max_selected=spec.max_selected,
                    price_mode=spec.price_mode,
                    sort=sort,
                    created_at=now,
                    updated_at=now,
                )
            )

        option_ids: dict[tuple[str, str], str] = {}
        for spec in tpl.modifier_groups:
            group_id = group_ids[spec.key]
            for sort, opt in enumerate(spec.options):
                option_id = _child_id(tpl.key, h16, "mo", f"{spec.key}_{opt.key}")
                option_ids[(spec.key, opt.key)] = option_id
                if await ShopModifierOption.get_by_id(option_id) is not None:
                    continue
                nested_id = (
                    group_ids[opt.nested_group_key]
                    if opt.nested_group_key is not None
                    else None
                )
                photo_file_id = (
                    await self._upload_photo(
                        shop_id=shop_id,
                        product_id=None,
                        tpl_key=tpl.key,
                        photo=opt.photo,
                    )
                    if opt.photo
                    else None
                )
                _ = await ShopModifierOption.create(
                    ShopModifierOption(
                        shop_modifier_option_id=option_id,
                        group_id=group_id,
                        name=opt.name,
                        price_minor=opt.price_minor,
                        photo_file_id=photo_file_id,
                        nutrition_delta=dict(opt.nutrition_delta),
                        is_default=opt.is_default,
                        max_per_option=opt.max_per_option,
                        nested_group_id=nested_id,
                        sort=sort,
                        created_at=now,
                        updated_at=now,
                    )
                )
        return group_ids, option_ids

    async def _seed_products(
        self, shop_id: str, h16: str, tpl: DemoShopSpec, cat_ids: dict[str, str]
    ) -> dict[str, str]:
        prod_ids: dict[str, str] = {}
        now = utcnow()
        for sort, spec in enumerate(tpl.products):
            product_id = _child_id(tpl.key, h16, "pr", spec.key)
            prod_ids[spec.key] = product_id
            existing = await ShopProduct.get_by_id(product_id)
            if existing is not None:
                continue
            photo_file_id = await self._upload_photo(
                shop_id=shop_id,
                product_id=product_id,
                tpl_key=tpl.key,
                photo=spec.photo,
            )
            _ = await ShopProduct.create(
                ShopProduct(
                    shop_product_id=product_id,
                    shop_id=shop_id,
                    category_id=cat_ids[spec.category_key],
                    name=spec.name,
                    description=spec.description,
                    portion=spec.portion,
                    badges=list(spec.badges),
                    price_minor=spec.price_minor,
                    photo_file_id=photo_file_id,
                    nutrition=dict(spec.nutrition),
                    is_available=spec.is_available,
                    sort=sort,
                    created_at=now,
                    updated_at=now,
                )
            )
        return prod_ids

    async def _attach_modifiers(
        self,
        shop_id: str,
        tpl: DemoShopSpec,
        prod_ids: dict[str, str],
        group_ids: dict[str, str],
    ) -> None:
        _ = shop_id
        for spec in tpl.products:
            product_id = prod_ids[spec.key]
            for sort, group_key in enumerate(spec.modifier_group_keys):
                group_id = group_ids[group_key]
                if await ShopProductModifierGroup.get_link(product_id, group_id):
                    continue
                _ = await ShopProductModifierGroup.create(
                    ShopProductModifierGroup(
                        product_id=product_id,
                        group_id=group_id,
                        sort=sort,
                    )
                )

    async def _seed_promos(
        self,
        shop_id: str,
        h16: str,
        tpl: DemoShopSpec,
        prod_ids: dict[str, str],
        cat_ids: dict[str, str],
    ) -> None:
        now = utcnow()
        for sort, spec in enumerate(tpl.promos):
            promo_id = _child_id(tpl.key, h16, "pm", spec.key)
            if await ShopPromo.get_by_id(promo_id) is not None:
                continue
            _ = await ShopPromo.create(
                ShopPromo(
                    shop_promo_id=promo_id,
                    shop_id=shop_id,
                    name=spec.name,
                    is_active=spec.is_active,
                    sort=sort,
                    priority=spec.priority,
                    stacking=spec.stacking,
                    window=dict(spec.window),
                    condition=self._resolve_refs(spec.condition, prod_ids, cat_ids),
                    action=self._resolve_refs(spec.action, prod_ids, cat_ids),
                    created_at=now,
                    updated_at=now,
                )
            )

    @staticmethod
    def _resolve_refs(
        payload: JsonObject, prod_ids: dict[str, str], cat_ids: dict[str, str]
    ) -> JsonObject:
        """Ключи продуктов/категорий в спеке → реальные id (JSONB форма)."""
        resolved = dict(payload)
        product_keys = resolved.get("product_ids")
        if isinstance(product_keys, list):
            resolved["product_ids"] = [
                prod_ids[_as_str(k)] for k in product_keys
            ]
        category_key = resolved.get("category_id")
        if isinstance(category_key, str):
            resolved["category_id"] = cat_ids[category_key]
        items = resolved.get("items")
        if isinstance(items, dict):
            resolved["items"] = {
                prod_ids[_as_str(k)]: v for k, v in items.items()
            }
        return resolved

    async def _seed_shelves(
        self,
        shop_id: str,
        h16: str,
        tpl: DemoShopSpec,
        prod_ids: dict[str, str],
        cat_ids: dict[str, str],
    ) -> dict[str, str]:
        """Полки ленты: ключи продуктов/категории спеки → реальные id."""
        now = utcnow()
        shelf_ids: dict[str, str] = {}
        for sort, spec in enumerate(tpl.shelves):
            shelf_id = _child_id(tpl.key, h16, "sh", spec.key)
            shelf_ids[spec.key] = shelf_id
            if await ShopShelf.get_by_id(shelf_id) is not None:
                continue
            _ = await ShopShelf.create(
                ShopShelf(
                    shop_shelf_id=shelf_id,
                    shop_id=shop_id,
                    kind=spec.kind,
                    layout=spec.layout,
                    placement=spec.placement,
                    title=spec.title,
                    subtitle=spec.subtitle,
                    product_ids=[prod_ids[k] for k in spec.product_keys],
                    category_id=(
                        cat_ids[spec.category_key] if spec.category_key else None
                    ),
                    limit=spec.limit,
                    sort=sort,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        return shelf_ids

    async def _seed_banners(
        self,
        shop_id: str,
        h16: str,
        tpl: DemoShopSpec,
        prod_ids: dict[str, str],
        cat_ids: dict[str, str],
        shelf_ids: dict[str, str],
    ) -> None:
        """Баннеры верха ленты: картинка грузится в файлы, deeplink
        ``<prefix>:<key>`` резолвится в реальную сущность шаблона."""
        now = utcnow()
        refs: dict[str, dict[str, str]] = {
            "product": prod_ids,
            "category": cat_ids,
            "shelf": shelf_ids,
        }
        for sort, spec in enumerate(tpl.banners):
            banner_id = _child_id(tpl.key, h16, "bn", spec.key)
            if await ShopBanner.get_by_id(banner_id) is not None:
                continue
            image_file_id = await self._upload_photo(
                shop_id=shop_id,
                product_id=None,
                tpl_key=tpl.key,
                photo=spec.photo,
            )
            link = spec.link
            if link:
                prefix, sep, ref_key = link.partition(":")
                if sep and prefix in refs:
                    link = f"{prefix}:{refs[prefix][_as_str(ref_key)]}"
            _ = await ShopBanner.create(
                ShopBanner(
                    shop_banner_id=banner_id,
                    shop_id=shop_id,
                    title=spec.title,
                    subtitle=spec.subtitle,
                    image_file_id=image_file_id,
                    link=link,
                    window=dict(spec.window),
                    sort=sort,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )

    async def _seed_tables(
        self, shop_id: str, h16: str, tpl: DemoShopSpec
    ) -> dict[str, str]:
        now = utcnow()
        table_ids: dict[str, str] = {}
        for spec in tpl.tables:
            table_id = _child_id(tpl.key, h16, "tb", spec.key)
            table_ids[spec.key] = table_id
            if await ShopTable.get_by_id(table_id) is not None:
                continue
            _ = await ShopTable.create(
                ShopTable(
                    shop_table_id=table_id,
                    shop_id=shop_id,
                    label=spec.label,
                    created_at=now,
                    updated_at=now,
                )
            )
        return table_ids

    async def _seed_orders(
        self,
        shop_id: str,
        h16: str,
        tpl: DemoShopSpec,
        prod_ids: dict[str, str],
        group_ids: dict[str, str],
        option_ids: dict[tuple[str, str], str],
        table_ids: dict[str, str],
    ) -> None:
        code_h = _sha(f"{tpl.key}:{shop_id}", 6).upper()
        groups_by_key = {g.key: g for g in tpl.modifier_groups}
        products_by_key = {p.key: p for p in tpl.products}
        now = utcnow()
        for index, order_spec in enumerate(tpl.orders, start=1):
            order_id = _child_id(tpl.key, h16, "or", f"o{index}")
            if await ShopOrder.get_by_id(order_id) is not None:
                continue
            items, items_total = self._build_order_items(
                order_id, order_spec, products_by_key, groups_by_key,
                prod_ids, group_ids, option_ids,
            )
            delivery_fee = (
                tpl.delivery_fee_minor
                if order_spec.delivery_type is ShopDeliveryType.DELIVERY
                else 0
            )
            created_at = now - timedelta(hours=order_spec.age_hours)
            history, status_changed_at = self._build_history(order_spec, created_at)
            geo = order_spec.geo
            _ = await ShopOrder.create(
                ShopOrder(
                    shop_order_id=order_id,
                    shop_id=shop_id,
                    public_code=f"DM{code_h}{index}",
                    status=order_spec.status,
                    customer_name=order_spec.customer_name,
                    customer_phone=order_spec.customer_phone,
                    delivery_type=order_spec.delivery_type,
                    address=order_spec.address,
                    delivery_eta_minutes=(
                        30 if order_spec.status is ShopOrderStatus.DELIVERING else None
                    ),
                    table_id=table_ids.get(order_spec.table_key, ""),
                    table_label=(
                        next(
                            (t.label for t in tpl.tables if t.key == order_spec.table_key),
                            "",
                        )
                    ),
                    comment=order_spec.comment,
                    items_total_minor=items_total,
                    discount_minor=0,
                    delivery_fee_minor=delivery_fee,
                    loyalty_reward_minor=order_spec.loyalty_reward_minor,
                    total_minor=items_total
                    + delivery_fee
                    - order_spec.loyalty_reward_minor,
                    currency="RUB",
                    idempotency_key=f"demo:{tpl.key}:{shop_id}:{index}",
                    status_history=history,
                    delivery_lat=geo.delivery_lat if geo else None,
                    delivery_lng=geo.delivery_lng if geo else None,
                    delivery_route=dict(geo.route) if geo else {},
                    shop_lat=geo.shop_lat if geo else None,
                    shop_lng=geo.shop_lng if geo else None,
                    created_at=created_at,
                    updated_at=status_changed_at,
                    status_changed_at=status_changed_at,
                )
            )
            _ = await ShopOrderItem.create_many(items)
            if order_spec.feedback is not None:
                await self._seed_feedback(
                    tpl.key, h16, shop_id, order_id, index,
                    order_spec, status_changed_at,
                )

    async def _seed_feedback(
        self,
        tpl_key: str,
        h16: str,
        shop_id: str,
        order_id: str,
        index: int,
        order_spec: DemoOrderSpec,
        status_changed_at: datetime,
    ) -> None:
        """Отзыв на demo-заказ: рейтинг/теги/комментарий ленты «Отзывы»."""
        spec = order_spec.feedback
        if spec is None or order_spec.status is not ShopOrderStatus.DONE:
            return
        feedback_id = _child_id(tpl_key, h16, "fb", f"o{index}")
        if await ShopOrderFeedback.get_by_id(feedback_id) is not None:
            return
        written_at = status_changed_at + timedelta(minutes=40)
        _ = await ShopOrderFeedback.create(
            ShopOrderFeedback(
                shop_order_feedback_id=feedback_id,
                shop_id=shop_id,
                shop_order_id=order_id,
                customer_id="",
                customer_name=order_spec.customer_name,
                rating=spec.rating,
                chips=[chip.value for chip in spec.chips],
                comment=spec.comment,
                created_at=written_at,
                updated_at=written_at,
            )
        )

    async def _seed_loyalty(
        self, tpl_key: str, h16: str, shop_id: str, tpl: DemoShopSpec
    ) -> None:
        """Программа лояльности витрины — одна строка на ``shop_id``."""
        spec = tpl.loyalty
        if spec is None:
            return
        if await ShopLoyaltyProgram.get_by_shop(shop_id) is not None:
            return
        now = utcnow()
        _ = await ShopLoyaltyProgram.create(
            ShopLoyaltyProgram(
                shop_loyalty_program_id=_child_id(tpl_key, h16, "lp", "main"),
                shop_id=shop_id,
                orders_goal=spec.orders_goal,
                reward_kind=spec.reward_kind,
                reward_value=spec.reward_value,
                created_at=now,
                updated_at=now,
            )
        )

    def _build_order_items(
        self,
        order_id: str,
        order_spec: DemoOrderSpec,
        products_by_key: dict[str, DemoProductSpec],
        groups_by_key: dict[str, DemoModifierGroupSpec],
        prod_ids: dict[str, str],
        group_ids: dict[str, str],
        option_ids: dict[tuple[str, str], str],
    ) -> tuple[list[ShopOrderItem], int]:
        items: list[ShopOrderItem] = []
        total = 0
        for index, item_spec in enumerate(order_spec.items):
            product = products_by_key[item_spec.product_key]
            unit = product.price_minor
            modifiers: list[dict[str, object]] = []
            for group_key, option_key in item_spec.selections:
                group = groups_by_key[group_key]
                option = next(o for o in group.options if o.key == option_key)
                if group.price_mode is ModifierPriceMode.ABSOLUTE:
                    unit = option.price_minor
                else:
                    unit += option.price_minor
                modifiers.append(
                    {
                        "group_id": group_ids[group_key],
                        "option_id": option_ids[(group_key, option_key)],
                        "group_name": group.name,
                        "option_name": option.name,
                        "price_minor": option.price_minor,
                        "qty": 1,
                    }
                )
            total += unit * item_spec.qty
            items.append(
                ShopOrderItem(
                    shop_order_item_id=f"{order_id}:i{index}",
                    order_id=order_id,
                    product_id=prod_ids[product.key],
                    name_snapshot=product.name,
                    price_minor=unit,
                    qty=item_spec.qty,
                    modifiers=modifiers,
                )
            )
        return items, total

    @staticmethod
    def _build_history(
        order_spec: DemoOrderSpec, created_at: datetime
    ) -> tuple[list[dict[str, object]], datetime]:
        chain = _ORDER_CHAIN[order_spec.delivery_type]
        end_index = chain.index(order_spec.status)
        if len(order_spec.history_minutes) != end_index:
            raise ValueError(
                f"order spec history_minutes {order_spec.history_minutes!r} does not reach status {order_spec.status!r}"
            )
        history: list[dict[str, object]] = [{"status": "new", "at": created_at}]
        for step, minutes in enumerate(order_spec.history_minutes, start=1):
            history.append(
                {
                    "status": chain[step].value,
                    "at": created_at + timedelta(minutes=minutes),
                }
            )
        return history, created_at + timedelta(
            minutes=order_spec.history_minutes[-1] if order_spec.history_minutes else 0
        )
