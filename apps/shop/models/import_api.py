"""Payload и результаты агентного и файлового импорта меню shop.

Write-back агента (`ShopMenuImportApplyPayload`, `ShopProductsEnrichApplyPayload`)
зеркалит `core/clients/shop_models.py` — args `ShopClient` и builtins `shop_*`.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from apps.shop.models.enums import (
    ShopAllergen,
    ShopMeasureUnit,
    ShopMenuFileFormat,
    ShopMenuImportTarget,
)
from apps.shop.models.nutrition import ShopNutrition
from core.models import StrictBaseModel


class ShopMenuImportTargetSpec(StrictBaseModel):
    """Куда пишет импорт: каталог, новое меню или существующее меню."""

    shop_id: str = Field(min_length=1)
    target: ShopMenuImportTarget
    shop_menu_id: str | None = Field(default=None, min_length=1)
    menu_name: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _target_fields(self) -> Self:
        if self.target == ShopMenuImportTarget.INTO_MENU and self.shop_menu_id is None:
            raise ValueError("target into_menu requires shop_menu_id")
        if self.target == ShopMenuImportTarget.NEW_MENU and self.menu_name is None:
            raise ValueError("target new_menu requires menu_name")
        return self


class ShopMenuImportStartPayload(ShopMenuImportTargetSpec):
    file_ids: list[str] = Field(min_length=1, max_length=20)


class ShopMenuTemplateBuildPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    menu_name: str = Field(min_length=1, max_length=200)
    brief: str = Field(default="", max_length=2000)


class ShopProductsEnrichPayload(StrictBaseModel):
    """Пустой ``shop_product_ids`` — все блюда без фото, КБЖУ или состава."""

    shop_id: str = Field(min_length=1)
    shop_product_ids: list[str] = Field(default_factory=list, max_length=500)


class ShopMenuFileImportRunPayload(ShopMenuImportTargetSpec):
    file_id: str = Field(min_length=1)
    format: ShopMenuFileFormat
    enrich_after: bool = False


class ShopMenuPhotoCrop(StrictBaseModel):
    """Прямоугольник фото блюда во вложении; координаты — доли страницы."""

    file_id: str = Field(min_length=1)
    page: int = Field(default=0, ge=0)
    x0: float = Field(ge=0, le=1)
    y0: float = Field(ge=0, le=1)
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _ordered_box(self) -> Self:
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("crop box requires x1 > x0 and y1 > y0")
        return self


class ShopMenuImportItemPlan(StrictBaseModel):
    """Позиция плана: существующее блюдо (``shop_product_id``) или новое."""

    shop_product_id: str | None = Field(default=None, min_length=1)
    name: str = Field(default="", max_length=300)
    description: str = ""
    price_minor: int | None = Field(default=None, ge=0)
    measure: int | None = Field(default=None, ge=0)
    measure_unit: ShopMeasureUnit = ShopMeasureUnit.G
    ingredients: list[str] = Field(default_factory=list)
    nutrition: ShopNutrition | None = None
    allergens: list[ShopAllergen] = Field(default_factory=list)
    photo: ShopMenuPhotoCrop | None = None

    @model_validator(mode="after")
    def _new_dish_fields(self) -> Self:
        if self.shop_product_id is None and (self.name == "" or self.price_minor is None):
            raise ValueError("new dish requires name and price_minor")
        return self


class ShopMenuImportSectionPlan(StrictBaseModel):
    name: str = Field(min_length=1, max_length=200)
    items: list[ShopMenuImportItemPlan] = Field(min_length=1)


class ShopMenuImportApplyPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    work_item_id: str = Field(min_length=1)
    sections: list[ShopMenuImportSectionPlan] = Field(min_length=1)


class ShopMenuImportApplyResult(StrictBaseModel):
    """Итог write-back; хранится в ``WorkItem.variables.apply_result``."""

    work_item_id: str
    shop_id: str
    shop_menu_id: str | None
    shop_product_ids: list[str]
    similar_count: int = Field(ge=0)


class ShopProductEnrichUpdate(StrictBaseModel):
    """Обогащение блюда: каждое поле пишется только в пустое поле каталога."""

    shop_product_id: str = Field(min_length=1)
    description: str | None = None
    measure: int | None = Field(default=None, ge=0)
    measure_unit: ShopMeasureUnit | None = None
    ingredients: list[str] | None = None
    nutrition: ShopNutrition | None = None
    allergens: list[ShopAllergen] | None = None
    photo_file_id: str | None = Field(default=None, min_length=1)


class ShopProductsEnrichApplyPayload(StrictBaseModel):
    shop_id: str = Field(min_length=1)
    work_item_id: str = Field(min_length=1)
    updates: list[ShopProductEnrichUpdate] = Field(min_length=1)


class ShopProductsEnrichApplyResult(StrictBaseModel):
    """Итог обогащения; хранится в ``WorkItem.variables.apply_result``."""

    work_item_id: str
    shop_id: str
    shop_product_ids: list[str]


class ShopMenuFileImportError(StrictBaseModel):
    """Строка файла, которая не стала блюдом. ``row`` — 1-based номер строки или позиции."""

    row: int = Field(ge=1)
    error_code: str = Field(min_length=1)


class ShopMenuFileImportReport(StrictBaseModel):
    shop_id: str
    shop_menu_id: str | None
    created: int = Field(ge=0)
    similar: int = Field(ge=0)
    errors: list[ShopMenuFileImportError]
    enrich_work_item_id: str | None
