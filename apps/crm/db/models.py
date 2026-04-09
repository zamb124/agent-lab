"""
SQLAlchemy модели для CRM Service.

Таблицы в crm_db:
- crm_entities: Сущности CRM с типизированными атрибутами
- entity_types: Типы сущностей с иерархией и промптами
- relationship_types: Типы связей с промптами
- relationships: Граф связей между entities
- company_mapping: Связь tenant (company) с entity
- access_grants: Гранты доступа
- access_requests: Запросы на доступ
"""

from datetime import datetime, date, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy import String, Text, Boolean, Float, Date, DateTime, Index, UniqueConstraint, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB, ARRAY, TSVECTOR

from core.db.models import Base


class CRMEntity(Base):
    """
    Сущности CRM с типизированными атрибутами.

    Структурные данные для SQL-запросов (фильтрация по типу, тегам, датам).
    Семантический поиск через JOIN с vector_documents (shared_db).
    """

    __tablename__ = "crm_entities"

    entity_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(100), default="default", nullable=False)

    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_subtype: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)

    tags: Mapped[List[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    attributes: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)

    priority: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    note_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    assignees: Mapped[List[str]] = mapped_column(ARRAY(String), default=list, nullable=False)

    attachment_ids: Mapped[List[str]] = mapped_column(ARRAY(String), default=list, nullable=False)

    user_id: Mapped[str] = mapped_column(String(100), nullable=False)

    source_entity_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_company_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    relevance: Mapped[float] = mapped_column(Float, default=1.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    search_vector: Mapped[Optional[str]] = mapped_column(TSVECTOR, nullable=True)

    __table_args__ = (
        Index("ix_crm_entities_company_type", "company_id", "entity_type"),
        Index("ix_crm_entities_tags", "tags", postgresql_using="gin"),
        Index("ix_crm_entities_due_date", "due_date"),
        Index("ix_crm_entities_note_date", "note_date"),
        Index("ix_crm_entities_namespace", "company_id", "namespace"),
        Index("ix_crm_entities_fts", "search_vector", postgresql_using="gin"),
    )

    @property
    def is_note(self) -> bool:
        return self.entity_type == "note"

    @property
    def is_task(self) -> bool:
        return self.entity_type == "task"

    @property
    def full_type(self) -> str:
        if self.entity_subtype:
            return f"{self.entity_type}:{self.entity_subtype}"
        return self.entity_type

    def __repr__(self) -> str:
        return f"<CRMEntity(entity_id='{self.entity_id}', type='{self.full_type}', company='{self.company_id}')>"


class EntityType(Base):
    """
    Типы сущностей CRM с иерархией и промптами.
    
    ВСЕ типы с company_id (ОБЯЗАТЕЛЬНО)!
    Системные типы копируются из шаблонов при создании компании.
    
    Иерархия:
    - note (parent=None)
      - meeting (parent="note")
      - call (parent="note")
      - webinar_notes (кастомный, parent="note")
    - task (parent=None)
    - contact (бизнес-тип, parent=None)
    - organization (бизнес-тип, parent=None)
    """
    
    __tablename__ = "entity_types"
    
    type_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        nullable=False,
        index=True
    )
    parent_type_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True
    )
    
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    prompt: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Промпт для AI извлечения этого типа"
    )
    
    required_fields: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    optional_fields: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Создан из системного шаблона (но с company_id!)"
    )
    is_event: Mapped[bool] = mapped_column(Boolean, default=False)
    check_duplicates: Mapped[bool] = mapped_column(Boolean, default=True)
    weight_coefficient: Mapped[float] = mapped_column(Float, default=1.0)
    
    # Публичные поля для этого типа
    public_fields: Mapped[List[str]] = mapped_column(
        JSONB,
        default=["name", "entity_type", "tags"],
        nullable=False,
        comment="Какие поля показывать при публичном доступе"
    )
    namespace_ids: Mapped[List[str]] = mapped_column(
        JSONB,
        default=["default"],
        nullable=False,
        comment="Список namespace, где тип разрешен"
    )
    is_context_anchor: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Тип может быть якорем контекста для заметок (сделка, лид и т.д.)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    
    __table_args__ = (
        Index("idx_entity_types_parent", "parent_type_id"),
        Index("idx_entity_types_system", "is_system"),
    )
    
    def __repr__(self) -> str:
        return f"<EntityType(type_id='{self.type_id}', name='{self.name}', company='{self.company_id}')>"


class RelationshipType(Base):
    """
    Типы связей между entities с промптами.
    
    ВСЕ типы с company_id (ОБЯЗАТЕЛЬНО)!
    Системные типы (mentions, linked) копируются при создании компании.
    
    Примеры:
    - mentions: AI извлекает упоминания (prompt)
    - linked: явная ссылка через @ (БЕЗ prompt, парсер)
    - works_for: кастомная связь (prompt)
    - manages: кастомная связь с обратной (inverse_type_id)
    """
    
    __tablename__ = "relationship_types"
    
    type_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    company_id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        nullable=False,
        index=True
    )
    
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    prompt: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Промпт для AI извлечения этой связи"
    )
    
    is_directed: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="Направленная (A→B) или симметричная (A↔B)"
    )
    inverse_type_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="ID обратной связи (manages ↔ reports_to)"
    )
    
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    is_system: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="Создан из системного шаблона"
    )
    weight_default: Mapped[float] = mapped_column(Float, default=1.0)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    
    __table_args__ = (Index("idx_relationship_types_system", "is_system"),)
    
    def __repr__(self) -> str:
        return f"<RelationshipType(type_id='{self.type_id}', name='{self.name}', company='{self.company_id}')>"


class Relationship(Base):
    """
    Граф связей между entities.
    
    ВСЕ связи ТОЛЬКО здесь (нет linked_entity_ids в CRMEntity)!
    
    source_entity_id и target_entity_id - ID сущностей в crm_entities.
    relationship_type - ID типа связи из RelationshipType.
    namespace - изоляция связей по пространствам.
    """
    
    __tablename__ = "relationships"
    
    relationship_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(100), nullable=False, default="default", index=True)
    
    source_entity_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_entity_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    relationship_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    attributes: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    
    __table_args__ = (
        Index("idx_relationships_source", "source_entity_id"),
        Index("idx_relationships_target", "target_entity_id"),
        Index("idx_relationships_source_target", "source_entity_id", "target_entity_id"),
        Index("idx_relationships_type", "relationship_type"),
        Index("idx_relationships_namespace", "company_id", "namespace"),
    )
    
    def __repr__(self) -> str:
        return f"<Relationship(id='{self.relationship_id}', type='{self.relationship_type}')>"


class CompanyMapping(Base):
    """
    Связь между tenant (company из shared_db) и entity в crm_entities.
    
    При первом входе в CRM автоматически создается entity типа 'organization'
    для компании пользователя с is_owner=True.
    """
    
    __tablename__ = "company_mapping"
    
    company_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<CompanyMapping(company_id='{self.company_id}', entity_id='{self.entity_id}')>"


class AccessGrant(Base):
    """
    Универсальные гранты доступа.
    
    Позволяет шарить:
    - Конкретную entity
    - Весь namespace
    
    Кому:
    - public (весь интернет, анонимы)
    - user (конкретный user_id из любой компании)
    - company (вся компания)
    """
    
    __tablename__ = "access_grants"
    
    grant_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    
    # Владелец
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # ЧТО шарим
    resource_type: Mapped[str] = mapped_column(
        String(50), 
        nullable=False,
        comment="entity | namespace"
    )
    resource_id: Mapped[str] = mapped_column(
        String(200), 
        nullable=False, 
        index=True,
        comment="entity_id или namespace name"
    )
    
    # КОМУ шарим
    grant_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="public | user | company"
    )
    
    # Для grant_type="user"
    target_user_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="User ID (может быть из любой компании)"
    )
    
    # Для grant_type="company"
    target_company_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Company ID"
    )
    
    # Права
    role: Mapped[str] = mapped_column(
        String(50),
        default="viewer",
        nullable=False,
        comment="viewer | editor | admin"
    )
    
    # Опционально: временный доступ
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Срок действия (опционально)"
    )
    
    # Опционально: токен для анонимного доступа
    access_token: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
        comment="Токен для шаринга по ссылке"
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )
    
    __table_args__ = (
        Index("idx_grants_resource", "resource_type", "resource_id", "company_id"),
        Index("idx_grants_target_user", "target_user_id"),
        Index("idx_grants_target_company", "target_company_id"),
        Index("idx_grants_token", "access_token"),
    )
    
    def __repr__(self) -> str:
        return f"<AccessGrant(grant_id='{self.grant_id}', type='{self.grant_type}', resource='{self.resource_type}:{self.resource_id}')>"


class AccessRequest(Base):
    """
    Запросы на доступ к скрытым заметкам/сущностям.
    
    Статусы: pending, approved, rejected
    """
    
    __tablename__ = "access_requests"
    
    request_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    requester_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    requester_company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    
    # Deep copy опции
    include_dependencies: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_depth: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Результат
    created_entity_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    __table_args__ = (
        Index("idx_access_requests_owner_status", "owner_id", "status"),
        Index("idx_access_requests_resource", "resource_type", "resource_id"),
    )
    
    def __repr__(self) -> str:
        return f"<AccessRequest(request_id='{self.request_id}', status='{self.status}')>"


class NamespaceTemplate(Base):
    """Шаблон namespace (редактируемый в БД)."""

    __tablename__ = "namespace_templates"

    template_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("company_id", "template_id", name="uq_namespace_template_company"),
        Index("idx_namespace_template_company_system", "company_id", "is_system"),
    )

    def __repr__(self) -> str:
        return f"<NamespaceTemplate(template_id='{self.template_id}', company='{self.company_id}')>"


class NamespaceTemplateType(Base):
    """Тип сущности внутри шаблона namespace."""

    __tablename__ = "namespace_template_types"

    entry_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    template_key: Mapped[str] = mapped_column(
        ForeignKey("namespace_templates.template_key", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    parent_type_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    required_fields: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    optional_fields: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_event: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    check_duplicates: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    weight_coefficient: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    namespace_ids: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    is_context_anchor: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="При материализации в EntityType — якорь контекста",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("template_key", "type_id", name="uq_namespace_template_type"),
        Index("idx_namespace_template_type_template", "template_key"),
    )

    def __repr__(self) -> str:
        return f"<NamespaceTemplateType(template_key='{self.template_key}', type_id='{self.type_id}')>"


class CRMKnowledgeImport(Base):
    """
    Журнал импорта базы знаний (мастер начальной загрузки): метаданные, прогресс, id для отката.
    """

    __tablename__ = "crm_knowledge_imports"

    import_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False)

    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    extract_entity_types: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    source_file_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_file_ids: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    source_text_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    split_by_headings: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    chunk_max_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=50_000)

    taskiq_task_id: Mapped[Optional[str]] = mapped_column(String(220), nullable=True)

    notes_created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    entities_created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    relationships_created_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_entity_ids: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    created_relationship_ids: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    attachment_document_ids: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)

    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chunk_errors: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_crm_knowledge_imports_company_ns_status", "company_id", "namespace", "status"),
    )

    def __repr__(self) -> str:
        return f"<CRMKnowledgeImport(import_id='{self.import_id}', status='{self.status}')>"
