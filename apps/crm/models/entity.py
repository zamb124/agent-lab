"""
Единая модель для ВСЕХ сущностей CRM в ChromaDB.

БЕЗ linked_entity_ids - все связи через Relationship в PostgreSQL!
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import date, datetime


class ChromaDBEntity(BaseModel):
    """
    Универсальная модель для всех сущностей CRM.
    
    Иерархия типов:
    - entity_type: базовый тип (note, task, contact, organization)
    - entity_subtype: подтип для note (meeting, call, webinar_notes)
    
    Связи:
    - ВСЕ связи через Relationship в PostgreSQL
    - НЕТ linked_entity_ids!
    """
    
    entity_id: str = Field(description="Уникальный ID")
    company_id: str = Field(description="ID компании (ОБЯЗАТЕЛЬНО)")
    
    # Namespace изоляция (default по умолчанию)
    namespace: str = Field(
        default="default",
        description="Namespace внутри компании"
    )
    
    entity_type: str = Field(description="Базовый тип: note, task, contact и тд")
    entity_subtype: Optional[str] = Field(
        default=None,
        description="Подтип для note: meeting, call, webinar_notes"
    )
    
    name: str = Field(description="Название/заголовок")
    description: Optional[str] = Field(default=None, description="Описание")
    
    status: str = Field(default="active", description="active, archived, completed, cancelled")
    
    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Кастомные атрибуты (любая JSON структура)"
    )
    tags: List[str] = Field(default_factory=list, description="Теги")
    
    attachment_ids: List[str] = Field(
        default_factory=list,
        description="ID вложений в RAG Service"
    )
    
    note_date: Optional[date] = Field(default=None, description="Дата записи")
    
    due_date: Optional[date] = Field(default=None, description="Дедлайн")
    priority: Optional[str] = Field(default=None, description="low, medium, high, urgent")
    assignees: List[str] = Field(default_factory=list, description="ID исполнителей")
    
    user_id: str = Field(description="Создатель (обязательно)")
    
    # Для скопированных entities (cross-company)
    source_entity_id: Optional[str] = Field(
        default=None,
        description="ID оригинала (если скопировано из другой компании)"
    )
    source_company_id: Optional[str] = Field(
        default=None,
        description="Company ID оригинала"
    )
    
    # Метаданные relationships из другой компании
    external_relationships: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Read-only инфо о связях из source (для скопированных)"
    )
    
    relevance: float = Field(default=1.0, description="Релевантность для AI")
    
    created_at: datetime
    updated_at: datetime
    
    @property
    def is_note(self) -> bool:
        return self.entity_type == "note"
    
    @property
    def is_task(self) -> bool:
        return self.entity_type == "task"
    
    @property
    def full_type(self) -> str:
        """note:meeting или task"""
        if self.entity_subtype:
            return f"{self.entity_type}:{self.entity_subtype}"
        return self.entity_type

