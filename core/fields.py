"""
Кастомный Field для моделей с поддержкой UI метаданных.

КРИТИЧНО для Pydantic v2: 
- ВСЕ кастомные поля идут ТОЛЬКО в json_schema_extra
- НИЧЕГО кроме стандартных Pydantic параметров НЕ передается в FieldInfo
"""

from typing import Any, Optional, Dict
from pydantic.fields import FieldInfo


# Список кастомных UI полей
CUSTOM_UI_FIELDS = {
    'frozen', 'readonly', 'placeholder', 'groups', 'widget_attrs', 
    'exclude_from_form', 'editable_in_table', 'hidden'
}


def Field(
    default: Any = ...,
    *,
    frozen: Optional[bool] = None,
    readonly: bool = False,
    placeholder: Optional[str] = None,
    groups: Optional[Dict] = None,
    widget_attrs: Optional[Dict] = None,
    exclude_from_form: bool = False,
    editable_in_table: bool = True,
    hidden: bool = False,
    title: Optional[str] = None,
    description: Optional[str] = None,
    default_factory: Any = None,
    alias: Optional[str] = None,
    **kwargs
) -> Any:
    """
    Кастомный Field для Pydantic v2.
    
    UI-специфичные поля (readonly, placeholder, etc) переносятся в json_schema_extra.
    В FieldInfo передаются ТОЛЬКО стандартные Pydantic параметры.
    """
    
    if frozen:
        readonly = True
    
    our_extra: Dict[str, Any] = {}
    
    if frozen is not None:
        our_extra['frozen'] = frozen
    if readonly:
        our_extra['readonly'] = readonly
    if placeholder:
        our_extra['placeholder'] = placeholder
    if groups:
        our_extra['groups'] = groups
    if widget_attrs:
        our_extra['widget_attrs'] = widget_attrs
    if exclude_from_form:
        our_extra['exclude_from_form'] = exclude_from_form
    if not editable_in_table:
        our_extra['editable_in_table'] = editable_in_table
    if hidden:
        our_extra['hidden'] = hidden
    
    existing_extra = kwargs.get('json_schema_extra')
    if existing_extra and isinstance(existing_extra, dict):
        our_extra = {**existing_extra, **our_extra}
    
    if our_extra:
        kwargs['json_schema_extra'] = our_extra
    
    # Формируем параметры для FieldInfo (ТОЛЬКО стандартные Pydantic поля!)
    field_kwargs = {
        'title': title,
        'description': description,
    }
    
    if default_factory is not None:
        field_kwargs['default_factory'] = default_factory
    if alias is not None:
        field_kwargs['alias'] = alias
    
    # Добавляем остальные стандартные Pydantic поля из kwargs
    standard_fields = {
        'gt', 'ge', 'lt', 'le', 'multiple_of', 'max_length', 'min_length',
        'pattern', 'examples', 'deprecated', 'include', 'exclude',
        'discriminator', 'json_schema_extra', 'validation_alias', 'serialization_alias',
        'strict', 'coerce_numbers_to_str', 'allow_inf_nan'
    }
    
    for key in standard_fields:
        if key in kwargs:
            field_kwargs[key] = kwargs[key]
    
    return FieldInfo(default=default, **field_kwargs)


__all__ = ['Field']
