"""
Модели для работы с переменными.
"""

from __future__ import annotations

from pydantic import BaseModel
from typing import Optional, Dict, Any, Union

from core.fields import Field


class VariableDefinition(BaseModel):
    """Определение переменной с описанием для установки flow"""

    key: str = Field(
        title="Ключ переменной",
        description="Имя переменной в формате @var:key"
    )
    description: str = Field(
        title="Описание",
        description="Описание переменной для пользователя"
    )
    default_value: Optional[str] = Field(
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
VariableDefinitionInput = Union[VariableDefinition, Dict[str, Any]]

