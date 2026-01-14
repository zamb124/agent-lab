"""
Pydantic модели для API endpoints.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Any, List, Optional, Literal
from datetime import date, datetime


class EntityCreate(BaseModel):
    """Создание entity"""
    entity_type: str
    entity_subtype: Optional[str] = None
    namespace: str = Field(default="default", description="Namespace для изоляции")
    name: str
    description: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    user_id: Optional[str] = None
    
    note_date: Optional[date] = None
    due_date: Optional[date] = None
    priority: Optional[str] = None
    assignees: List[str] = Field(default_factory=list)


class EntityUpdate(BaseModel):
    """Обновление entity"""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    
    note_date: Optional[date] = None
    due_date: Optional[date] = None
    priority: Optional[str] = None
    assignees: Optional[List[str]] = Field(default=None)


class EntityResponse(BaseModel):
    """Response с entity"""
    model_config = ConfigDict(from_attributes=True)
    
    entity_id: str
    company_id: str
    namespace: str
    entity_type: str
    entity_subtype: Optional[str]
    name: str
    description: Optional[str]
    status: str
    attributes: Dict[str, Any]
    tags: List[str]
    attachment_ids: List[str]
    
    note_date: Optional[date]
    due_date: Optional[date]
    priority: Optional[str]
    assignees: List[str]
    
    user_id: Optional[str]
    source_entity_id: Optional[str]
    source_company_id: Optional[str]
    external_relationships: List[Dict[str, Any]]
    relevance: float
    
    created_at: datetime
    updated_at: datetime


class EntityTypeCreate(BaseModel):
    """Создание типа сущности"""
    type_id: str
    parent_type_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    prompt: Optional[str] = None
    required_fields: Optional[Dict[str, Any]] = None
    optional_fields: Optional[Dict[str, Any]] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    is_event: bool = False
    check_duplicates: bool = True


class EntityTypeUpdate(BaseModel):
    """Обновление типа сущности"""
    name: Optional[str] = None
    description: Optional[str] = None
    parent_type_id: Optional[str] = None
    prompt: Optional[str] = None
    required_fields: Optional[Dict[str, Any]] = None
    optional_fields: Optional[Dict[str, Any]] = None
    icon: Optional[str] = None
    color: Optional[str] = None


class EntityTypeResponse(BaseModel):
    """Response с типом сущности"""
    model_config = ConfigDict(from_attributes=True)
    
    type_id: str
    company_id: str
    parent_type_id: Optional[str]
    name: str
    description: Optional[str]
    prompt: Optional[str]
    required_fields: Dict[str, Any]
    optional_fields: Dict[str, Any]
    icon: Optional[str]
    color: Optional[str]
    is_system: bool
    is_event: bool
    check_duplicates: bool
    weight_coefficient: float
    created_at: datetime


class RelationshipTypeCreate(BaseModel):
    """Создание типа связи"""
    type_id: str
    name: str
    description: Optional[str] = None
    prompt: Optional[str] = None
    is_directed: bool = True
    inverse_type_id: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    weight_default: float = 1.0


class RelationshipTypeResponse(BaseModel):
    """Response с типом связи"""
    model_config = ConfigDict(from_attributes=True)
    
    type_id: str
    company_id: str
    name: str
    description: Optional[str]
    prompt: Optional[str]
    is_directed: bool
    inverse_type_id: Optional[str]
    icon: Optional[str]
    color: Optional[str]
    is_system: bool
    weight_default: float
    created_at: datetime


class RelationshipCreate(BaseModel):
    """Создание связи"""
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    namespace: str = Field(default="default", description="Namespace для изоляции")
    weight: float = 1.0
    attributes: Optional[Dict[str, Any]] = None


class RelationshipResponse(BaseModel):
    """Response со связью"""
    model_config = ConfigDict(from_attributes=True)
    
    relationship_id: str
    company_id: str
    namespace: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: str
    weight: float
    attributes: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SearchMentionsRequest(BaseModel):
    """Запрос на поиск упоминаний в тексте"""
    text: str = Field(description="Текст для поиска упоминаний")


class AIAnalyzeRequest(BaseModel):
    """Запрос на AI анализ текста"""
    text: str = Field(description="Текст для анализа")
    extract_entity_types: Optional[List[str]] = Field(
        default=None,
        description="Типы для извлечения (None = все)"
    )
    extract_relationship_types: Optional[List[str]] = Field(
        default=None,
        description="Типы связей для извлечения (None = все кроме linked)"
    )
    mentioned_entity_ids: Optional[List[str]] = Field(
        default=None,
        description="ID entities, упомянутых через @"
    )


class AIExtractedEntity(BaseModel):
    """Entity извлеченная AI (без БД полей)"""
    model_config = {"extra": "allow"}  # Разрешаем дополнительные поля от AI
    
    entity_type: str
    name: str
    entity_subtype: Optional[str] = None
    description: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    note_date: Optional[str] = None
    confidence: Optional[float] = None
    # Поля для tasks
    due_date: Optional[str] = None
    priority: Optional[str] = None
    assignees: Optional[List[str]] = None
    
    # Поля дедупликации (заполняются после проверки)
    dedup_action: Optional[Literal["create", "merge"]] = None
    dedup_existing_id: Optional[str] = None
    dedup_existing_name: Optional[str] = None
    dedup_confidence: Optional[float] = None


class AIExtractedRelationship(BaseModel):
    """Relationship извлеченная AI (без БД полей)"""
    source_entity_id: Optional[str] = None
    source_name: Optional[str] = None
    source_type: Optional[str] = None
    target_entity_id: Optional[str] = None
    target_name: Optional[str] = None
    target_type: Optional[str] = None
    relationship_type: str
    weight: Optional[float] = None


class AIAnalyzeResponse(BaseModel):
    """Результат AI анализа"""
    note: Optional[AIExtractedEntity] = Field(
        default=None,
        description="Извлеченная заметка с подтипом"
    )
    entities: List[AIExtractedEntity] = Field(
        default_factory=list,
        description="Извлеченные entities"
    )
    relationships: List[AIExtractedRelationship] = Field(
        default_factory=list,
        description="Извлеченные связи"
    )


class DeduplicateResult(BaseModel):
    """Результат проверки на дубликат"""
    is_duplicate: bool
    confidence: float
    reason: str
    action: Literal["merge", "create"]
    existing_entity_id: Optional[str] = None
    existing_entity_name: Optional[str] = None
    merged_attributes: Optional[Dict[str, Any]] = None
    merged_description: Optional[str] = None

