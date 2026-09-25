"""Базовая модель сервиса stock: enum-поля остаются членами enum."""

from typing import ClassVar

from pydantic import ConfigDict

from core.models import StrictBaseModel


class StockBaseModel(StrictBaseModel):
    """Строгая модель stock с сохранением enum-типов."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=False,
        str_strip_whitespace=True,
        validate_default=True,
    )


__all__ = ["StockBaseModel"]
