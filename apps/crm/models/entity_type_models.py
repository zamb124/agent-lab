"""
Pydantic модели для типов сущностей CRM.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict

from pydantic import BaseModel, ConfigDict

from core.fields import Field


class FieldType(str, Enum):
    """Тип поля сущности для UI"""
    STR = "str"
    TEXTAREA = "textarea"
    INT = "int"
    EMAIL = "email"
    PHONE = "phone"
    LINK = "link"
    DATE = "date"


class FieldCategory(str, Enum):
    """Категория поля для расположения в UI"""
    MAIN = "main"          # Боковая панель карточки
    OPTIONAL = "optional"  # Основная часть карточки


class FieldDefinition(BaseModel):
    """Определение поля типа сущности"""
    
    model_config = ConfigDict(from_attributes=True)
    
    label: str = Field(title="Отображаемое название")
    type: FieldType = Field(default=FieldType.STR, title="Тип поля")
    category: FieldCategory = Field(default=FieldCategory.OPTIONAL, title="Категория")
    prompt: str = Field(title="Промпт для AI извлечения")
    icon: Optional[str] = Field(default=None, title="Иконка (ti-mail, ti-phone)")
    placeholder: Optional[str] = Field(default=None, title="Placeholder для input")


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
        description="Общий промпт для извлечения сущностей этого типа"
    )
    required_fields: Dict[str, FieldDefinition] = Field(
        default_factory=dict,
        title="Обязательные поля",
        description="Поля которые должны быть заполнены"
    )
    optional_fields: Dict[str, FieldDefinition] = Field(
        default_factory=dict,
        title="Опциональные поля"
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
    is_event: bool = Field(
        default=False,
        title="Тип события",
        description="True = тип является событием (meeting, call, email)"
    )
    weight_coefficient: float = Field(
        default=1.0,
        title="Коэффициент веса",
        description="Множитель для расчета важности сущности (0.5-2.0)"
    )


class EntityTypeUpdate(BaseModel):
    """Обновление типа сущности"""
    
    model_config = ConfigDict(from_attributes=True)
    
    name: Optional[str] = Field(default=None, title="Название")
    description: Optional[str] = Field(default=None, title="Описание")
    prompt: Optional[str] = Field(default=None, title="Промпт для ИИ")
    required_fields: Optional[Dict[str, FieldDefinition]] = Field(
        default=None, 
        title="Обязательные поля"
    )
    optional_fields: Optional[Dict[str, FieldDefinition]] = Field(
        default=None, 
        title="Опциональные поля"
    )
    icon: Optional[str] = Field(default=None, title="Иконка")
    color: Optional[str] = Field(default=None, title="Цвет")
    check_duplicates: Optional[bool] = Field(default=None, title="Проверять дубликаты")
    is_filtered: Optional[bool] = Field(default=None, title="Фильтровать по умолчанию")
    is_event: Optional[bool] = Field(default=None, title="Тип события")
    weight_coefficient: Optional[float] = Field(default=None, title="Коэффициент веса")


class EntityTypeResponse(BaseModel):
    """Ответ с типом сущности"""
    
    model_config = ConfigDict(from_attributes=True)
    
    type_id: str = Field(title="ID типа", readonly=True)
    company_id: Optional[str] = Field(default=None, title="ID компании", readonly=True)
    name: str = Field(title="Название")
    description: Optional[str] = Field(default=None, title="Описание")
    prompt: Optional[str] = Field(default=None, title="Промпт для ИИ")
    required_fields: Dict[str, FieldDefinition] = Field(
        default_factory=dict, 
        title="Обязательные поля"
    )
    optional_fields: Dict[str, FieldDefinition] = Field(
        default_factory=dict, 
        title="Опциональные поля"
    )
    icon: Optional[str] = Field(default=None, title="Иконка")
    color: Optional[str] = Field(default=None, title="Цвет")
    is_system: bool = Field(default=False, title="Системный тип", readonly=True)
    is_event: bool = Field(default=False, title="Тип события", readonly=True)
    check_duplicates: bool = Field(default=True, title="Проверять дубликаты")
    is_filtered: bool = Field(default=False, title="Фильтровать по умолчанию")
    weight_coefficient: float = Field(default=1.0, title="Коэффициент веса")
    created_at: datetime = Field(title="Дата создания", readonly=True)
