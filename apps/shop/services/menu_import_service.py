"""Черновик импорта меню: Redis на 24 часа, публикация пишет листинг."""

from __future__ import annotations

import json

from apps.shop.events import publish_shop_menu_import_updated
from apps.shop.models.api import (
    MenuImportDraft,
    MenuImportItem,
    MenuImportItemUpdate,
    ShopCategoryCreateRequest,
    ShopNutrition,
    ShopProductCreateRequest,
    ShopProductUpdateRequest,
)
from apps.shop.models.common import new_id
from apps.shop.models.enums import MenuImportStatus
from apps.shop.models.product import ShopProduct
from apps.shop.services.shop_service import (
    ShopService,
    clean_shop_allergens,
    clean_shop_ingredients,
)
from core.clients.redis_client import RedisClient
from core.errors.boundary import (
    PlatformBoundaryError,
    PlatformConflictError,
    PlatformNotFoundError,
    PlatformUnavailableError,
)
from core.types import JsonObject, JsonValue

_DRAFT_TTL_SECONDS = 24 * 60 * 60
_PORTION_LABEL = {"g": "г", "ml": "мл", "pcs": "шт"}


def _draft_key(company_id: str, shop_id: str) -> str:
    return f"shop:menu_import:{company_id}:{shop_id}"


def _portion_text(measure: JsonValue, unit: JsonValue) -> str:
    if measure is None:
        return ""
    if isinstance(measure, bool) or not isinstance(measure, int) or measure < 0:
        raise PlatformBoundaryError(
            "menu measure is invalid", error_code="ai_empty_result"
        )
    if not isinstance(unit, str) or unit not in _PORTION_LABEL:
        raise PlatformBoundaryError(
            "menu measure unit is invalid", error_code="ai_empty_result"
        )
    return f"{measure} {_PORTION_LABEL[unit]}"


def _nutrition_from_agent(
    raw: JsonValue, measure: JsonValue, unit: JsonValue
) -> tuple[ShopNutrition, bool]:
    """КБЖУ агента — на 100 г. Граммы пересчитываются на порцию."""
    if raw is None:
        return ShopNutrition(), False
    if not isinstance(raw, dict):
        raise PlatformBoundaryError(
            "menu nutrition is invalid", error_code="ai_empty_result"
        )
    keys = {
        "kcal": "calories_kcal",
        "protein_g": "proteins_g",
        "fat_g": "fats_g",
        "carb_g": "carbs_g",
    }
    values: dict[str, float] = {}
    for field, source in keys.items():
        number = raw.get(source)
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise PlatformBoundaryError(
                "menu nutrition is invalid", error_code="ai_empty_result"
            )
        values[field] = float(number)
    per_100g = True
    if (
        unit == "g"
        and isinstance(measure, int)
        and not isinstance(measure, bool)
        and measure > 0
    ):
        factor = measure / 100
        values = {field: number * factor for field, number in values.items()}
        per_100g = False
    return ShopNutrition.model_validate(values), per_100g


def _string_list(raw: JsonValue, *, code: str) -> list[str]:
    if not isinstance(raw, list):
        raise PlatformBoundaryError("menu list is invalid", error_code=code)
    items: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise PlatformBoundaryError("menu list is invalid", error_code=code)
        items.append(item)
    return items


def _photo_file_id(raw: JsonValue) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise PlatformBoundaryError(
            "menu photo is invalid", error_code="ai_empty_result"
        )
    file_id = raw.get("file_id")
    if not isinstance(file_id, str) or file_id.strip() == "":
        return None
    return file_id.strip()


def items_from_agent_sections(sections: JsonValue) -> list[MenuImportItem]:
    """Секции ответа shop_menu_agent → строки черновика без совпадения имён."""
    if not isinstance(sections, list):
        raise PlatformBoundaryError(
            "menu agent payload has no sections", error_code="ai_empty_result"
        )
    items: list[MenuImportItem] = []
    for section in sections:
        if not isinstance(section, dict):
            raise PlatformBoundaryError(
                "menu section is invalid", error_code="ai_empty_result"
            )
        section_name = section.get("name")
        if not isinstance(section_name, str):
            raise PlatformBoundaryError(
                "menu section name is invalid", error_code="ai_empty_result"
            )
        raw_items = section.get("items")
        if not isinstance(raw_items, list):
            raise PlatformBoundaryError(
                "menu section items are invalid", error_code="ai_empty_result"
            )
        for raw in raw_items:
            if not isinstance(raw, dict):
                raise PlatformBoundaryError(
                    "menu item is invalid", error_code="ai_empty_result"
                )
            name = raw.get("name")
            if not isinstance(name, str) or name.strip() == "":
                raise PlatformBoundaryError(
                    "menu item name is invalid", error_code="ai_empty_result"
                )
            description = raw.get("description")
            if description is None:
                description = ""
            if not isinstance(description, str):
                raise PlatformBoundaryError(
                    "menu item description is invalid", error_code="ai_empty_result"
                )
            price = raw.get("price_minor")
            if isinstance(price, bool) or not isinstance(price, int) or price < 0:
                raise PlatformBoundaryError(
                    "menu item price is invalid", error_code="ai_empty_result"
                )
            measure = raw.get("measure")
            unit = raw.get("measure_unit")
            nutrition, per_100g = _nutrition_from_agent(
                raw.get("nutrition"), measure, unit
            )
            items.append(
                MenuImportItem(
                    item_id=new_id("menuimp"),
                    section_name=section_name.strip(),
                    name=name.strip(),
                    description=description,
                    price_minor=price,
                    portion=_portion_text(measure, unit),
                    nutrition=nutrition,
                    nutrition_is_per_100g=per_100g,
                    ingredients=clean_shop_ingredients(
                        _string_list(raw.get("ingredients"), code="ingredient_invalid")
                    ),
                    allergens=clean_shop_allergens(
                        _string_list(raw.get("allergens"), code="allergen_invalid")
                    ),
                    photo_file_id=_photo_file_id(raw.get("photo")),
                )
            )
    return items


class MenuImportService:
    """Один черновик на магазин. Публикация создаёт или обновляет листинг."""

    def __init__(self, redis: RedisClient, shop_service: ShopService) -> None:
        self._redis: RedisClient = redis
        self._shop: ShopService = shop_service

    async def get_draft(self, company_id: str, shop_id: str) -> MenuImportDraft:
        draft = await self._load(company_id, shop_id)
        if draft is None:
            raise PlatformNotFoundError(
                "Menu import draft not found", error_code="menu_import_not_found"
            )
        return draft

    async def begin(self, company_id: str, shop_id: str) -> MenuImportDraft:
        """Сбросить черновик в ``parsing`` до ответа агента."""
        _ = await self._shop.get_shop(company_id, shop_id)
        draft = MenuImportDraft(
            shop_id=shop_id,
            status=MenuImportStatus.PARSING,
        )
        await self._save(company_id, draft)
        return draft

    async def store_agent_payload(
        self, company_id: str, shop_id: str, payload: JsonObject
    ) -> MenuImportDraft:
        """Разобранные секции агента становятся строками ``ready`` или ``failed``."""
        failure = payload.get("failure_reason")
        failure_reason = failure.strip() if isinstance(failure, str) else ""
        items = items_from_agent_sections(payload.get("sections"))
        if not items:
            if failure_reason == "":
                failure_reason = "menu_unreadable"
            draft = MenuImportDraft(
                shop_id=shop_id,
                status=MenuImportStatus.FAILED,
                failure_reason=failure_reason,
            )
        else:
            draft = MenuImportDraft(
                shop_id=shop_id,
                status=MenuImportStatus.READY,
                items=await self._match(company_id, shop_id, items),
            )
        await self._save(company_id, draft)
        return draft

    async def mark_failed(
        self, company_id: str, shop_id: str, failure_reason: str
    ) -> MenuImportDraft:
        draft = MenuImportDraft(
            shop_id=shop_id,
            status=MenuImportStatus.FAILED,
            failure_reason=failure_reason,
        )
        await self._save(company_id, draft)
        return draft

    async def update_item(
        self, company_id: str, shop_id: str, payload: MenuImportItemUpdate
    ) -> MenuImportDraft:
        draft = await self._ready(company_id, shop_id)
        replacement = MenuImportItem(
            item_id=payload.item_id,
            section_name=payload.section_name.strip(),
            name=payload.name.strip(),
            description=payload.description,
            price_minor=payload.price_minor,
            portion=payload.portion,
            nutrition=payload.nutrition,
            nutrition_is_per_100g=payload.nutrition_is_per_100g,
            ingredients=clean_shop_ingredients(payload.ingredients),
            allergens=clean_shop_allergens(payload.allergens),
            photo_file_id=payload.photo_file_id,
        )
        found = False
        items: list[MenuImportItem] = []
        for item in draft.items:
            if item.item_id == payload.item_id:
                items.append(replacement)
                found = True
            else:
                items.append(item)
        if not found:
            raise PlatformNotFoundError(
                "Menu import item not found", error_code="menu_import_item_not_found"
            )
        updated = draft.model_copy(
            update={"items": await self._match(company_id, shop_id, items)}
        )
        await self._save(company_id, updated)
        return updated

    async def publish(
        self, company_id: str, shop_id: str, item_ids: list[str]
    ) -> tuple[MenuImportDraft, list[str]]:
        """Опубликовать выбранные строки. Пустой список — все строки."""
        draft = await self._ready(company_id, shop_id)
        if item_ids:
            wanted = set(item_ids)
            chosen = [item for item in draft.items if item.item_id in wanted]
            if len(chosen) != len(wanted):
                raise PlatformNotFoundError(
                    "Menu import item not found",
                    error_code="menu_import_item_not_found",
                )
        else:
            chosen = list(draft.items)
        if not chosen:
            raise PlatformConflictError(
                "Menu import draft is empty", error_code="menu_import_empty"
            )
        product_ids: list[str] = []
        for item in chosen:
            product_ids.append(
                await self._publish_item(company_id, shop_id, item)
            )
        published = {item.item_id for item in chosen}
        updated = draft.model_copy(
            update={
                "items": [
                    item for item in draft.items if item.item_id not in published
                ]
            }
        )
        await self._save(company_id, updated)
        return updated, product_ids

    async def discard(
        self, company_id: str, shop_id: str, item_id: str | None
    ) -> MenuImportDraft:
        draft = await self.get_draft(company_id, shop_id)
        if item_id is None:
            emptied = MenuImportDraft(shop_id=shop_id, status=MenuImportStatus.READY)
            await self._save(company_id, emptied)
            return emptied
        if draft.status != MenuImportStatus.READY:
            raise PlatformConflictError(
                "Menu import draft is not ready", error_code="menu_import_not_ready"
            )
        remaining = [item for item in draft.items if item.item_id != item_id]
        if len(remaining) == len(draft.items):
            raise PlatformNotFoundError(
                "Menu import item not found", error_code="menu_import_item_not_found"
            )
        updated = draft.model_copy(update={"items": remaining})
        await self._save(company_id, updated)
        return updated

    async def _ready(self, company_id: str, shop_id: str) -> MenuImportDraft:
        draft = await self.get_draft(company_id, shop_id)
        if draft.status != MenuImportStatus.READY:
            raise PlatformConflictError(
                "Menu import draft is not ready", error_code="menu_import_not_ready"
            )
        return draft

    async def _match(
        self, company_id: str, shop_id: str, items: list[MenuImportItem]
    ) -> list[MenuImportItem]:
        listings = await self._shop.list_products(company_id, shop_id)
        by_name: dict[str, str] = {}
        for row in listings:
            key = row.name.casefold()
            if key not in by_name:
                by_name[key] = row.product_id
        return [
            item.model_copy(
                update={"matched_product_id": by_name.get(item.name.casefold())}
            )
            for item in items
        ]

    async def _publish_item(
        self, company_id: str, shop_id: str, item: MenuImportItem
    ) -> str:
        category_id = await self._category_id(company_id, shop_id, item.section_name)
        if item.matched_product_id is not None:
            existing = await ShopProduct.by_shop_and_product(
                shop_id, item.matched_product_id
            )
            if existing is not None:
                updated = await self._shop.update_product(
                    company_id,
                    shop_id,
                    item.matched_product_id,
                    self._update_request(item, category_id),
                )
                return updated.product_id
        created = await self._shop.create_product(
            company_id,
            shop_id,
            ShopProductCreateRequest(
                product_id=item.matched_product_id,
                category_id=category_id,
                name=item.name,
                description=item.description,
                portion=item.portion,
                price_minor=item.price_minor,
                photo_file_id=item.photo_file_id,
                nutrition=item.nutrition,
                ingredients=item.ingredients,
                allergens=item.allergens,
            ),
        )
        return created.product_id

    def _update_request(
        self, item: MenuImportItem, category_id: str | None
    ) -> ShopProductUpdateRequest:
        if item.photo_file_id is None:
            return ShopProductUpdateRequest(
                category_id=category_id,
                description=item.description,
                portion=item.portion,
                price_minor=item.price_minor,
                nutrition=item.nutrition,
                ingredients=item.ingredients,
                allergens=item.allergens,
            )
        return ShopProductUpdateRequest(
            category_id=category_id,
            description=item.description,
            portion=item.portion,
            price_minor=item.price_minor,
            photo_file_id=item.photo_file_id,
            nutrition=item.nutrition,
            ingredients=item.ingredients,
            allergens=item.allergens,
        )

    async def _category_id(
        self, company_id: str, shop_id: str, section_name: str
    ) -> str | None:
        text = section_name.strip()
        if text == "":
            return None
        categories = await self._shop.list_categories(company_id, shop_id)
        for category in categories:
            if category.name.casefold() == text.casefold():
                return category.shop_category_id
        created = await self._shop.create_category(
            company_id, shop_id, ShopCategoryCreateRequest(name=text)
        )
        return created.shop_category_id

    async def _load(self, company_id: str, shop_id: str) -> MenuImportDraft | None:
        raw = await self._redis.get(_draft_key(company_id, shop_id))
        if raw is None:
            return None
        return MenuImportDraft.model_validate_json(raw)

    async def _save(self, company_id: str, draft: MenuImportDraft) -> None:
        stored = await self._redis.set(
            _draft_key(company_id, draft.shop_id),
            json.dumps(draft.model_dump(mode="json"), ensure_ascii=False),
            ttl=_DRAFT_TTL_SECONDS,
        )
        if stored is not True:
            raise PlatformUnavailableError(
                "Menu import draft store is unavailable",
                error_code="menu_import_unavailable",
            )
        await publish_shop_menu_import_updated(
            company_id=company_id,
            shop_id=draft.shop_id,
            status=draft.status,
        )
