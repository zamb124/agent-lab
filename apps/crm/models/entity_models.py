"""
Pydantic модели для сущностей CRM.

Сущности хранятся в ChromaDB с embeddings.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

from pydantic import BaseModel, ConfigDict

from core.fields import Field


class EntityStatus(str, Enum):
    """Статусы сущности"""
    PENDING = "pending"      # Ожидает review
    APPROVED = "approved"    # Подтверждена
    REJECTED = "rejected"    # Отклонена


class EntityCreate(BaseModel):
    """Создание сущности"""
    
    model_config = ConfigDict(from_attributes=True)
    
    type: str = Field(
        title="Тип сущности",
        description="ID типа (person, organization, project, etc.)"
    )
    name: str = Field(
        title="Название",
        description="Название сущности"
    )
    description: Optional[str] = Field(
        default=None,
        title="Описание",
        description="Описание сущности"
    )
    ai_description: Optional[str] = Field(
        default=None,
        title="AI описание",
        description="Контекстное описание от AI: откуда сущность, на какой встрече, из какой компании"
    )
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        title="Атрибуты",
        description="Дополнительные атрибуты (email, phone, etc.)"
    )
    status: EntityStatus = Field(
        default=EntityStatus.PENDING,
        title="Статус",
        description="Статус сущности (pending, approved, rejected)"
    )
    source_note_id: Optional[str] = Field(
        default=None,
        title="ID исходной заметки",
        description="Заметка из которой была извлечена сущность"
    )
    relevance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        title="Релевантность",
        description="Оценка важности сущности от AI (0.0-1.0)"
    )


class EntityUpdate(BaseModel):
    """Обновление сущности"""
    
    model_config = ConfigDict(from_attributes=True)
    
    name: Optional[str] = Field(
        default=None,
        title="Название"
    )
    description: Optional[str] = Field(
        default=None,
        title="Описание"
    )
    ai_description: Optional[str] = Field(
        default=None,
        title="AI описание"
    )
    attributes: Optional[Dict[str, Any]] = Field(
        default=None,
        title="Атрибуты"
    )
    relevance: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        title="Релевантность"
    )


class EntityResponse(BaseModel):
    """Ответ с сущностью"""
    
    model_config = ConfigDict(from_attributes=True)
    
    entity_id: str = Field(
        title="ID сущности",
        readonly=True
    )
    company_id: str = Field(
        title="ID компании",
        readonly=True
    )
    type: str = Field(
        title="Тип сущности"
    )
    name: str = Field(
        title="Название"
    )
    description: Optional[str] = Field(
        default=None,
        title="Описание"
    )
    ai_description: Optional[str] = Field(
        default=None,
        title="AI описание",
        description="Контекстное описание от AI для поиска"
    )
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        title="Атрибуты"
    )
    status: str = Field(
        default="pending",
        title="Статус"
    )
    source_note_id: Optional[str] = Field(
        default=None,
        title="ID исходной заметки"
    )
    relevance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        title="Релевантность",
        description="Оценка важности сущности от AI (0.0-1.0)"
    )
    created_at: Optional[datetime] = Field(
        default=None,
        title="Дата создания",
        readonly=True
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        title="Дата обновления",
        readonly=True
    )


class EntitySearchRequest(BaseModel):
    """Запрос поиска сущностей"""
    
    model_config = ConfigDict(from_attributes=True)
    
    query: Optional[str] = Field(
        default=None,
        title="Поисковый запрос",
        description="Семантический поиск по тексту"
    )
    entity_type: Optional[str] = Field(
        default=None,
        title="Тип сущности",
        description="Фильтр по типу"
    )
    filters: Dict[str, Any] = Field(
        default_factory=dict,
        title="Фильтры",
        description="Фильтры по атрибутам"
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        title="Лимит"
    )
    offset: int = Field(
        default=0,
        ge=0,
        title="Смещение"
    )


class EntitySearchResponse(BaseModel):
    """Ответ поиска сущностей"""
    
    model_config = ConfigDict(from_attributes=True)
    
    entities: List[EntityResponse] = Field(
        default_factory=list,
        title="Сущности"
    )
    total: int = Field(
        title="Всего найдено"
    )
    query: Optional[str] = Field(
        default=None,
        title="Поисковый запрос"
    )

