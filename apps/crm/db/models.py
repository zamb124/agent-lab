"""
SQLAlchemy модели для CRM Service.

Таблицы в crm_db:
- entity_types: Типы сущностей (person, organization, project, task + кастомные)
- relationships: Связи между сущностями
- notes: Заметки (Daily Notes, Meeting Minutes, etc.)
- tasks: Задачи с приоритетами и дедлайнами
- company_mapping: Связь tenant (company) с entity в ChromaDB
"""

from datetime import datetime, timezone, date
from typing import Optional, List, Dict, Any

from sqlalchemy import String, Text, Boolean, Float, Date, DateTime, Index, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB, ARRAY


class Base(DeclarativeBase):
    """Базовый класс для всех моделей CRM"""
    pass


class EntityType(Base):
    """
    Типы сущностей.
    
    Системные типы (is_system=True):
    - person: люди, контакты
    - organization: организации, компании-партнеры
    - project: проекты
    - task: задачи
    
    Кастомные типы создаются пользователями (company_id != NULL).
    """
    
    __tablename__ = "entity_types"
    
    type_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    company_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    required_attributes: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    optional_attributes: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    check_duplicates: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_filtered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    __table_args__ = (
        UniqueConstraint("type_id", "company_id", name="uq_entity_type_company"),
        Index("ix_entity_types_is_system", "is_system"),
    )
    
    def __repr__(self) -> str:
        return f"<EntityType(type_id='{self.type_id}', name='{self.name}')>"


class CompanyMapping(Base):
    """
    Связь между tenant (company из shared_db) и entity в ChromaDB.
    
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


class Relationship(Base):
    """
    Связи между сущностями.
    
    source_entity_id и target_entity_id - ID сущностей в ChromaDB.
    relationship_type - тип связи (works_for, connected_to, etc.)
    weight - вес связи от 0.0 до 1.0
    """
    
    __tablename__ = "relationships"
    
    relationship_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_entity_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_entity_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(100), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    attributes: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    __table_args__ = (
        Index("ix_relationships_type", "relationship_type"),
        Index("ix_relationships_source_target", "source_entity_id", "target_entity_id"),
    )
    
    def __repr__(self) -> str:
        return f"<Relationship(id='{self.relationship_id}', type='{self.relationship_type}')>"


class Note(Base):
    """
    Заметки (Daily Notes).
    
    Типы заметок:
    - freeform: свободная форма
    - meeting_minutes: протокол встречи
    - call_log: лог звонка
    
    linked_entity_ids - список ID сущностей в ChromaDB, связанных с заметкой.
    """
    
    __tablename__ = "notes"
    
    note_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    note_type: Mapped[str] = mapped_column(String(50), default="freeform", nullable=False)
    note_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    linked_entity_ids: Mapped[List[str]] = mapped_column(JSONB, default=list)
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
        Index("ix_notes_note_type", "note_type"),
        Index("ix_notes_company_date", "company_id", "note_date"),
    )
    
    def __repr__(self) -> str:
        return f"<Note(note_id='{self.note_id}', title='{self.title[:30]}...')>"


class Task(Base):
    """
    Задачи с приоритетами и дедлайнами.
    
    Приоритеты: low, medium, high, urgent
    Статусы: pending, in_progress, completed, cancelled
    """
    
    __tablename__ = "tasks"
    
    task_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    linked_entity_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    source_note_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
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
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_priority", "priority"),
        Index("ix_tasks_company_status", "company_id", "status"),
        Index("ix_tasks_user_status", "user_id", "status"),
    )
    
    def __repr__(self) -> str:
        return f"<Task(task_id='{self.task_id}', title='{self.title[:30]}...')>"
