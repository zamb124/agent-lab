"""
Базовые модели для платформы.

StrictBaseModel - базовый класс с extra='forbid' для Zero-Guess архитектуры.
FlexibleBaseModel - базовый класс с extra='allow' для runtime данных.
"""

from pydantic import BaseModel, ConfigDict


class StrictBaseModel(BaseModel):
    """
    Строгая базовая модель с запретом неизвестных полей.

    Zero-Guess Architecture:
    - extra='forbid' - любое неизвестное поле выбрасывает ошибку
    - validate_assignment=True - валидация при присваивании
    - use_enum_values=True - автоматическое извлечение значений из Enum

    Философия: "Better to crash than to guess"

    Если конфиг содержит неизвестное поле - это либо опечатка,
    либо устаревший конфиг. Система не должна молчать об этом.

    Examples:
        >>> class UserConfig(StrictBaseModel):
        ...     name: str
        ...     age: int

        >>> UserConfig(name="Alice", age=30)  # ✅ OK
        >>> UserConfig(name="Bob", age=25, extra_field="value")  # ❌ ValidationError
    """

    model_config = ConfigDict(
        extra='forbid',              # Запрещаем неизвестные поля
        validate_assignment=True,    # Валидация при присваивании
        use_enum_values=True,        # Используем значения Enum
        str_strip_whitespace=True,   # Убираем пробелы из строк
        validate_default=True,       # Валидация значений по умолчанию
    )


class FlexibleBaseModel(BaseModel):
    """
    Гибкая базовая модель для runtime данных (не конфигурации).

    Использовать ТОЛЬКО для:
    - Runtime state (ExecutionState)
    - Временных данных
    - Ответов от внешних API

    НЕ использовать для:
    - FlowConfig
    - NodeConfig
    - Любой конфигурации из БД

    Конфигурация должна быть строгой (StrictBaseModel).
    """

    model_config = ConfigDict(
        extra='allow',                # Разрешаем дополнительные поля
        validate_assignment=False,    # Без валидации при присваивании (производительность)
        use_enum_values=True,
        str_strip_whitespace=True,
    )


__all__ = [
    "StrictBaseModel",
    "FlexibleBaseModel",
]
