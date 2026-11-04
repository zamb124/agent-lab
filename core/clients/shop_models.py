"""Args-модели клиента и tools сервиса shop.

Поля зеркалят payload `apps/shop/models/import_api.py` — сервис валидирует их же
на REST-границе. Enum-значения — строковые `Literal` с теми же значениями, что
`ShopMeasureUnit` и `ShopAllergen` (`apps/shop/models/enums.py`).
"""

from __future__ import annotations

from typing import ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

ShopMeasureUnitValue = Literal["g", "ml", "pcs"]
ShopAllergenValue = Literal[
    "gluten",
    "dairy",
    "egg",
    "fish",
    "shellfish",
    "nuts",
    "peanuts",
    "soy",
    "sesame",
    "mustard",
    "celery",
    "lupin",
    "molluscs",
    "sulphites",
]


class _ShopArgs(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ShopCatalogListArgs(_ShopArgs):
    shop_id: str = Field(..., min_length=1, description="shop_id from WorkItem.variables. Never invent.")


class ShopNutritionArgs(_ShopArgs):
    calories_kcal: float = Field(..., ge=0, description="kcal per 100 g.")
    proteins_g: float = Field(..., ge=0, description="Proteins, g per 100 g.")
    fats_g: float = Field(..., ge=0, description="Fats, g per 100 g.")
    carbs_g: float = Field(..., ge=0, description="Carbohydrates, g per 100 g.")


class ShopMenuPhotoCropArgs(_ShopArgs):
    file_id: str = Field(..., min_length=1, description="file_id of a WorkItem attachment (menu photo or PDF).")
    page: int = Field(0, ge=0, description="0-based PDF page; 0 for images.")
    x0: float = Field(..., ge=0, le=1, description="Left edge, fraction of page width.")
    y0: float = Field(..., ge=0, le=1, description="Top edge, fraction of page height.")
    x1: float = Field(..., ge=0, le=1, description="Right edge, fraction of page width.")
    y1: float = Field(..., ge=0, le=1, description="Bottom edge, fraction of page height.")

    @model_validator(mode="after")
    def _ordered_box(self) -> Self:
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("crop box requires x1 > x0 and y1 > y0")
        return self


class ShopMenuImportItemArgs(_ShopArgs):
    shop_product_id: str | None = Field(
        None,
        description="Existing catalog dish (template mode). Omit to create a new dish from the fields below.",
    )
    name: str = Field("", max_length=300, description="Dish name; required for a new dish.")
    description: str = Field("", description="Dish description.")
    price_minor: int | None = Field(None, ge=0, description="Price in minor units (kopecks); required for a new dish.")
    measure: int | None = Field(None, ge=0, description="Portion size in measure_unit.")
    measure_unit: ShopMeasureUnitValue = Field("g", description="g | ml | pcs.")
    ingredients: list[str] = Field(default_factory=list, description="Ingredients as listed on the menu.")
    nutrition: ShopNutritionArgs | None = Field(None, description="Nutrition per 100 g.")
    allergens: list[ShopAllergenValue] = Field(default_factory=list, description="Allergens.")
    photo: ShopMenuPhotoCropArgs | None = Field(None, description="Dish photo crop from an attachment.")

    @model_validator(mode="after")
    def _new_dish_fields(self) -> Self:
        if self.shop_product_id is None and (self.name == "" or self.price_minor is None):
            raise ValueError("new dish requires name and price_minor")
        return self


class ShopMenuImportSectionArgs(_ShopArgs):
    name: str = Field(..., min_length=1, max_length=200, description="Menu section name.")
    items: list[ShopMenuImportItemArgs] = Field(..., min_length=1, description="Dishes of the section.")


class ShopMenuImportApplyArgs(_ShopArgs):
    shop_id: str = Field(..., min_length=1, description="shop_id from WorkItem.variables.")
    work_item_id: str = Field(..., min_length=1, description="work_item_id of the import WorkItem.")
    sections: list[ShopMenuImportSectionArgs] = Field(..., min_length=1, description="Recognized menu.")


class ShopProductEnrichUpdateArgs(_ShopArgs):
    shop_product_id: str = Field(..., min_length=1, description="Dish from shop_catalog_list.")
    description: str | None = Field(None, description="Written only when the dish description is empty.")
    measure: int | None = Field(None, ge=0, description="Written only when the dish has no measure.")
    measure_unit: ShopMeasureUnitValue | None = Field(None, description="Unit for measure.")
    ingredients: list[str] | None = Field(None, description="Written only when the dish has no ingredients.")
    nutrition: ShopNutritionArgs | None = Field(None, description="Written only when the dish has no nutrition.")
    allergens: list[ShopAllergenValue] | None = Field(None, description="Written only when the dish has no allergens.")
    photo_file_id: str | None = Field(None, description="Stored image file_id; written only when the dish has no photo.")


class ShopProductsEnrichApplyArgs(_ShopArgs):
    shop_id: str = Field(..., min_length=1, description="shop_id from WorkItem.variables.")
    work_item_id: str = Field(..., min_length=1, description="work_item_id of the enrich WorkItem.")
    updates: list[ShopProductEnrichUpdateArgs] = Field(..., min_length=1, description="Per-dish enrichment.")


__all__ = [
    "ShopAllergenValue",
    "ShopCatalogListArgs",
    "ShopMeasureUnitValue",
    "ShopMenuImportApplyArgs",
    "ShopMenuImportItemArgs",
    "ShopMenuImportSectionArgs",
    "ShopMenuPhotoCropArgs",
    "ShopNutritionArgs",
    "ShopProductEnrichUpdateArgs",
    "ShopProductsEnrichApplyArgs",
]
