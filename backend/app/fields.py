"""
Кастомный Field для моделей с поддержкой frozen -> readonly автоматически
"""

from typing import Any, Optional, Dict
from pydantic import Field as PydanticField


def Field(
    default: Any = ...,
    *,
    frozen: Optional[bool] = None,
    readonly: bool = False,
    title: Optional[str] = None,
    **kwargs
) -> Any:
    """
    Кастомный Field который автоматически делает frozen поля readonly.
    
    Если frozen=True, то автоматически устанавливается readonly=True в json_schema_extra.
    """
    
    # Если frozen=True, то поле автоматически readonly
    if frozen:
        readonly = True
    
    # Правильно обрабатываем json_schema_extra
    existing_extra = kwargs.pop('json_schema_extra', None)
    
    # Создаем наш extra (сохраняем и frozen и readonly для прозрачности)
    our_extra: Dict[str, Any] = {
        'readonly': readonly,
        'frozen': frozen
    }
    
    # Мержим с существующим
    if existing_extra:
        if isinstance(existing_extra, dict):
            our_extra = {**existing_extra, **our_extra}
        elif callable(existing_extra):
            # Если это функция, создаем wrapper
            original_func = existing_extra
            def combined_extra(schema: Dict[str, Any], model_type: Any) -> None:
                original_func(schema, model_type)
                schema.update(our_extra)
            kwargs['json_schema_extra'] = combined_extra
        else:
            kwargs['json_schema_extra'] = our_extra
    else:
        kwargs['json_schema_extra'] = our_extra
    
    return PydanticField(default, frozen=frozen, title=title, **kwargs)


__all__ = ['Field']

