"""
Модели для работы с переменными.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from core.fields import Field


class VariableDefinition(BaseModel):
    """Определение переменной с описанием для установки flow"""

    key: str = Field(
        title="Ключ переменной",
        description="Имя переменной в формате @var:key"
    )
    description: str = Field(
        default="",
        title="Описание",
        description="Описание переменной для пользователя"
    )
    default_value: str | None = Field(
        default=None,
        title="Значение по умолчанию",
        description="Предлагаемое значение по умолчанию"
    )
    is_secret: bool = Field(
        default=False,
        title="Секретная переменная",
        description="Переменная содержит чувствительные данные"
    )
    required: bool = Field(
        default=True,
        title="Обязательная",
        description="Требуется ли заполнить переменную при установке"
    )


# Type alias для гибкого определения переменных
VariableDefinitionInput = VariableDefinition | dict[str, Any]
