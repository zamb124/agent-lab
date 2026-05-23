"""
Кастомный Field для моделей с поддержкой UI метаданных.

КРИТИЧНО для Pydantic v2:
- ВСЕ кастомные поля идут ТОЛЬКО в json_schema_extra
- НИЧЕГО кроме стандартных Pydantic параметров НЕ передается в FieldInfo
"""

from collections.abc import Callable
from typing import Any

from pydantic import Field as PydanticField

# Список кастомных UI полей
CUSTOM_UI_FIELDS = {
    "frozen",
    "readonly",
    "placeholder",
    "groups",
    "widget_attrs",
    "exclude_from_form",
    "editable_in_table",
    "hidden",
}


def Field(
    default: Any = ...,
    *,
    frozen: bool | None = None,
    readonly: bool = False,
    placeholder: str | None = None,
    groups: dict[str, Any] | None = None,
    widget_attrs: dict[str, Any] | None = None,
    exclude_from_form: bool = False,
    editable_in_table: bool = True,
    hidden: bool = False,
    title: str | None = None,
    description: str | None = None,
    default_factory: Callable[[], Any] | Callable[[dict[str, Any]], Any] | None = None,
    alias: str | None = None,
    **kwargs: Any,
) -> Any:
    """
    Кастомный Field для Pydantic v2.

    UI-специфичные поля (readonly, placeholder, etc) переносятся в json_schema_extra.
    В FieldInfo передаются ТОЛЬКО стандартные Pydantic параметры.
    """

    if frozen:
        readonly = True

    ui_extra: dict[str, Any] = {}

    if frozen is not None:
        ui_extra["frozen"] = frozen
    if readonly:
        ui_extra["readonly"] = readonly
    if placeholder:
        ui_extra["placeholder"] = placeholder
    if groups:
        ui_extra["groups"] = groups
    if widget_attrs:
        ui_extra["widget_attrs"] = widget_attrs
    if exclude_from_form:
        ui_extra["exclude_from_form"] = exclude_from_form
    if not editable_in_table:
        ui_extra["editable_in_table"] = editable_in_table
    if hidden:
        ui_extra["hidden"] = hidden

    existing_extra = kwargs.get("json_schema_extra")
    if existing_extra is not None:
        if not isinstance(existing_extra, dict):
            raise TypeError("Field json_schema_extra must be a dict when UI metadata is used")
        ui_extra = {**existing_extra, **ui_extra}

    if ui_extra:
        kwargs["json_schema_extra"] = ui_extra

    # Формируем параметры для FieldInfo (ТОЛЬКО стандартные Pydantic поля!)
    field_kwargs: dict[str, Any] = {
        "title": title,
        "description": description,
    }

    if default_factory is not None:
        field_kwargs["default_factory"] = default_factory
    if alias is not None:
        field_kwargs["alias"] = alias

    # Добавляем остальные стандартные Pydantic поля из kwargs
    standard_fields = {
        "gt",
        "ge",
        "lt",
        "le",
        "multiple_of",
        "max_length",
        "min_length",
        "pattern",
        "examples",
        "deprecated",
        "include",
        "exclude",
        "discriminator",
        "json_schema_extra",
        "validation_alias",
        "serialization_alias",
        "strict",
        "coerce_numbers_to_str",
        "allow_inf_nan",
    }

    for key in standard_fields:
        if key in kwargs:
            field_kwargs[key] = kwargs[key]

    return PydanticField(default, **field_kwargs)


__all__ = ["Field"]
