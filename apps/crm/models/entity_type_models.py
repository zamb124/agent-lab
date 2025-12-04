"""
Pydantic модели для типов сущностей CRM.
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict

from core.fields import Field


class EntityTypeCreate(BaseModel):
    """Создание типа сущности"""
    
    model_config = ConfigDict(from_attributes=True)
    
    type_id: str = Field(
        title="ID типа",
        description="Уникальный идентификатор (латиница, подчеркивания)"
    )
    name: str = Field(
        title="Название",
        description="Отображаемое название"
    )
    description: Optional[str] = Field(
        default=None,
        title="Описание"
    )
    prompt: Optional[str] = Field(
        default=None,
        title="Промпт для ИИ",
        description="Промпт для извлечения сущностей этого типа"
    )
    required_attributes: List[str] = Field(
        default_factory=list,
        title="Обязательные атрибуты"
    )
    optional_attributes: List[str] = Field(
        default_factory=list,
        title="Опциональные атрибуты"
    )
    icon: Optional[str] = Field(
        default=None,
        title="Иконка",
        description="Класс иконки (ti-user, ti-building, etc.)"
    )
    color: Optional[str] = Field(
        default=None,
        title="Цвет",
        description="HEX цвет (#4A90E2)"
    )
    check_duplicates: bool = Field(
        default=True,
        title="Проверять дубликаты"
    )
    is_filtered: bool = Field(
        default=False,
        title="Фильтровать по умолчанию",
        description="True = второстепенный тип"
    )


class EntityTypeUpdate(BaseModel):
    """Обновление типа сущности"""
    
    model_config = ConfigDict(from_attributes=True)
    
    name: Optional[str] = Field(default=None, title="Название")
    description: Optional[str] = Field(default=None, title="Описание")
    prompt: Optional[str] = Field(default=None, title="Промпт для ИИ")
    required_attributes: Optional[List[str]] = Field(default=None, title="Обязательные атрибуты")
    optional_attributes: Optional[List[str]] = Field(default=None, title="Опциональные атрибуты")
    icon: Optional[str] = Field(default=None, title="Иконка")
    color: Optional[str] = Field(default=None, title="Цвет")
    check_duplicates: Optional[bool] = Field(default=None, title="Проверять дубликаты")
    is_filtered: Optional[bool] = Field(default=None, title="Фильтровать по умолчанию")


class EntityTypeResponse(BaseModel):
    """Ответ с типом сущности"""
    
    model_config = ConfigDict(from_attributes=True)
    
    type_id: str = Field(title="ID типа", readonly=True)
    company_id: Optional[str] = Field(default=None, title="ID компании", readonly=True)
    name: str = Field(title="Название")
    description: Optional[str] = Field(default=None, title="Описание")
    prompt: Optional[str] = Field(default=None, title="Промпт для ИИ")
    required_attributes: List[str] = Field(default_factory=list, title="Обязательные атрибуты")
    optional_attributes: List[str] = Field(default_factory=list, title="Опциональные атрибуты")
    icon: Optional[str] = Field(default=None, title="Иконка")
    color: Optional[str] = Field(default=None, title="Цвет")
    is_system: bool = Field(default=False, title="Системный тип", readonly=True)
    check_duplicates: bool = Field(default=True, title="Проверять дубликаты")
    is_filtered: bool = Field(default=False, title="Фильтровать по умолчанию")
    created_at: datetime = Field(title="Дата создания", readonly=True)


