"""
Pydantic модели для связей между сущностями CRM.
"""

from datetime import datetime
from typing import Optional, Dict, Any

from pydantic import BaseModel, ConfigDict

from core.fields import Field


class RelationshipCreate(BaseModel):
    """Создание связи"""
    
    model_config = ConfigDict(from_attributes=True)
    
    source_entity_id: str = Field(
        title="ID исходной сущности"
    )
    target_entity_id: str = Field(
        title="ID целевой сущности"
    )
    relationship_type: str = Field(
        title="Тип связи",
        description="works_for, connected_to, owns, etc."
    )
    weight: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        title="Вес связи"
    )
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        title="Атрибуты связи"
    )


class RelationshipResponse(BaseModel):
    """Ответ со связью"""
    
    model_config = ConfigDict(from_attributes=True)
    
    relationship_id: str = Field(title="ID связи", readonly=True)
    company_id: str = Field(title="ID компании", readonly=True)
    source_entity_id: str = Field(title="ID исходной сущности")
    target_entity_id: str = Field(title="ID целевой сущности")
    relationship_type: str = Field(title="Тип связи")
    weight: float = Field(title="Вес связи")
    attributes: Dict[str, Any] = Field(default_factory=dict, title="Атрибуты")
    created_at: datetime = Field(title="Дата создания", readonly=True)
    
    # Опционально: информация о связанных сущностях
    source_entity: Optional[Dict[str, Any]] = Field(
        default=None,
        title="Исходная сущность"
    )
    target_entity: Optional[Dict[str, Any]] = Field(
        default=None,
        title="Целевая сущность"
    )

