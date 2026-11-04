"""КБЖУ блюда — вложенный документ каталога, не отдельная таблица."""

from __future__ import annotations

from pydantic import Field

from core.models import StrictBaseModel


class ShopNutrition(StrictBaseModel):
    """Пищевая ценность на 100 г продукта."""

    calories_kcal: float = Field(ge=0)
    proteins_g: float = Field(ge=0)
    fats_g: float = Field(ge=0)
    carbs_g: float = Field(ge=0)
