"""
Базовая модель сервиса wiki.

Отличие от `StrictBaseModel` — `use_enum_values=False`: enum-поля остаются
членами enum (`WikiVisibility`, `WikiLinkTargetKind`, ...), а не голыми
строками. Иначе сервис получает строку там, где ждёт тип, и обращение к
`.value` падает уже в рантайме.
"""

from typing import ClassVar

from pydantic import ConfigDict

from core.models import StrictBaseModel


class WikiBaseModel(StrictBaseModel):
    """Строгая модель wiki с сохранением enum-типов."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=False,
        str_strip_whitespace=True,
        validate_default=True,
    )


class WikiContentModel(WikiBaseModel):
    """Модель содержимого документа.

    Пробелы в тексте значимы: обрезка сломала бы форматирование абзаца, где
    пробел разделяет фрагменты с разными марками.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=False,
        str_strip_whitespace=False,
        validate_default=True,
    )


__all__ = ["WikiBaseModel", "WikiContentModel"]
