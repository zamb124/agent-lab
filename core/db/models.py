"""
Модели базы данных SQLAlchemy.
Таблицы для key-value storage с маршрутизацией.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean, Float, Index, UniqueConstraint, text
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector

Base = declarative_base()


def _get_shared_db_url() -> str:
    """Получает URL shared БД из конфига."""
    from core.config import get_settings
    settings = get_settings()
    return settings.database.shared_url or settings.database.url


# Регистрируем shared сервис для миграций
from core.db.service_registry import register_service
register_service("shared", _get_shared_db_url, "core.db.models")


class Storage(Base):
    """
    Основная таблица для key-value хранения сущностей.

    Ключи имеют префиксы:
    - agent:agent_id
    - flow:flow_id
    - session:session_id
    """

    __tablename__ = "storage"

    key = Column(String, primary_key=True, index=True)
    value = Column(JSONB, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    expired_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("key", name="uq_storage_key"),
        Index("ix_storage_key_prefix", "key"),
        Index("ix_storage_updated_at", "updated_at"),
        Index("ix_storage_expired_at", "expired_at"),
        Index("ix_storage_key_created_at", "key", "created_at"),
        Index("ix_storage_key_updated_at", "key", "updated_at"),
        Index("ix_storage_key_expired_at", "key", "expired_at"),
    )

    def __repr__(self):
        return f"<Storage(key='{self.key}', updated_at='{self.updated_at}')>"


class Users(Base):
    """
    Таблица для хранения пользователей и аутентификации.

    Ключи имеют префиксы:
    - user:user_id (основная запись пользователя - source of truth)
    - user_providers:user_id (объект: {provider_user_id: {provider_name, email, metadata}})
    - auth_session:session_id (сессии аутентификации)
    - auth_state:state (временные состояния OAuth)
    """

    __tablename__ = "users"

    key = Column(String, primary_key=True, index=True)
    value = Column(JSONB, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    expired_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("key", name="uq_users_key"),
        Index("ix_users_key_prefix", "key"),
        Index("ix_users_updated_at", "updated_at"),
        Index("ix_users_expired_at", "expired_at"),
        Index("ix_users_key_created_at", "key", "created_at"),
        Index("ix_users_key_updated_at", "key", "updated_at"),
        Index("ix_users_key_expired_at", "key", "expired_at"),
        Index(
            "ix_users_providers_jsonb",
            text("value jsonb_path_ops"),
            postgresql_using="gin",
            postgresql_where=text("key LIKE 'user_providers:%'")
        ),
    )

    def __repr__(self):
        return f"<Users(key='{self.key}', updated_at='{self.updated_at}')>"


class Variables(Base):
    """
    Таблица для переменных всех компаний.

    Ключи имеют формат: company:{company_id}:var:{key}
    Изоляция per-company через префикс ключа.
    """

    __tablename__ = "variables"

    key = Column(String, primary_key=True, index=True)
    value = Column(JSONB, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    expired_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("key", name="uq_variables_key"),
        Index("ix_variables_key_prefix", "key"),
        Index("ix_variables_updated_at", "updated_at"),
        Index("ix_variables_expired_at", "expired_at"),
    )

    def __repr__(self):
        return f"<Variables(key='{self.key}', updated_at='{self.updated_at}')>"


class Stores(Base):
    """
    Таблица для хранения store (единого для всего flow).
    Все агенты в flow используют один и тот же store через store_id.
    """

    __tablename__ = "stores"

    store_id = Column(String(255), primary_key=True, index=True)
    store_data = Column(JSONB, nullable=False, default={})
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_stores_updated_at", "updated_at"),
    )

    def __repr__(self):
        return f"<Stores(store_id='{self.store_id}', updated_at='{self.updated_at}')>"


class AgentStates(Base):
    """
    Таблица для хранения состояний агентов.
    Хранит состояние сессий в формате JSONB.
    store хранится отдельно в таблице Stores и ссылается через store_id.
    """

    __tablename__ = "agent_states"

    session_id = Column(String(255), primary_key=True, index=True)
    store_id = Column(String(255), nullable=False)
    state_data = Column(JSONB, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_agent_states_store_id", "store_id"),
        Index("ix_agent_states_updated_at", "updated_at"),
    )

    def __repr__(self):
        return f"<AgentStates(session_id='{self.session_id}', store_id='{self.store_id}', updated_at='{self.updated_at}')>"


class Usage(Base):
    """
    Таблица для записей использования ресурсов (биллинг).

    Ключи имеют формат: company:{company_id}:usage:{resource_name}:{usage_id}
    Хранится в shared_db для централизованного учета.
    """

    __tablename__ = "usage"

    key = Column(String, primary_key=True, index=True)
    value = Column(JSONB, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    expired_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("key", name="uq_usage_key"),
        Index("ix_usage_key_prefix", "key"),
        Index("ix_usage_updated_at", "updated_at"),
        Index("ix_usage_expired_at", "expired_at"),
        Index("ix_usage_company_id", (text("(value->>'company_id')"))),
        Index("ix_usage_user_id", (text("(value->>'user_id')"))),
        Index("ix_usage_timestamp", (text("(value->>'timestamp')"))),
        Index("ix_usage_resource_name", (text("(value->>'resource_name')"))),
    )

    def __repr__(self):
        return f"<Usage(key='{self.key}', updated_at='{self.updated_at}')>"


class Namespaces(Base):
    """
    Таблица для namespace (изолированные области данных).
    Используется всеми сервисами: RAG, CRM, Agents.
    
    Ключи имеют формат: namespace:{company_id}:{namespace_name}
    """
    __tablename__ = "namespaces"
    
    key = Column(String, primary_key=True, index=True)
    value = Column(JSONB, nullable=False)
    expired_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    
    __table_args__ = (
        UniqueConstraint("key", name="uq_namespaces_key"),
        Index("ix_namespaces_key_prefix", "key"),
        Index("ix_namespaces_company_id", (text("(value->>'company_id')"))),
    )
    
    def __repr__(self):
        return f"<Namespaces(key='{self.key}', updated_at='{self.updated_at}')>"


class Spans(Base):
    """
    Таблица для хранения OpenTelemetry spans.
    
    Нормализованная структура для быстрого поиска по user_id, agent_id, session и т.д.
    """

    __tablename__ = "spans"

    span_id = Column(String, primary_key=True, index=True)
    trace_id = Column(String, nullable=False, index=True)
    parent_span_id = Column(String, nullable=True, index=True)
    
    operation_name = Column(String, nullable=False)
    kind = Column(String, nullable=True)
    
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    
    status = Column(String, nullable=True)
    status_message = Column(String, nullable=True)
    
    user_id = Column(String, nullable=True, index=True)
    user_name = Column(String, nullable=True)
    user_groups = Column(JSONB, nullable=True)
    
    session_auth = Column(String, nullable=True, index=True)
    session_agent = Column(String, nullable=True, index=True)
    
    agent_id = Column(String, nullable=True, index=True)
    task_id = Column(String, nullable=True, index=True)
    context_id = Column(String, nullable=True, index=True)
    skill_id = Column(String, nullable=True)
    channel = Column(String, nullable=True)
    
    node_id = Column(String, nullable=True)
    agent_name = Column(String, nullable=True)
    is_resume = Column(Boolean, nullable=True)
    
    attributes = Column(JSONB, nullable=True)
    events = Column(JSONB, nullable=True)

    __table_args__ = tuple()

    def __repr__(self):
        return f"<Spans(span_id='{self.span_id}', trace_id='{self.trace_id}', operation_name='{self.operation_name}')>"


class DocumentProcessingStatus(Base):
    """
    Таблица для отслеживания статуса обработки документов в RAG.
    
    Статусы: pending, processing, completed, failed
    """

    __tablename__ = "document_processing_status"

    document_id = Column(String(255), primary_key=True, index=True)
    task_id = Column(String(255), nullable=False, index=True, unique=True)
    namespace_id = Column(String(255), nullable=False, index=True)
    document_name = Column(String(500), nullable=False)
    status = Column(String(50), nullable=False, index=True)
    error_message = Column(String, nullable=True)
    s3_key = Column(String(1000), nullable=True)
    s3_bucket = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)
    chunks_count = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    extra_metadata = Column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_document_status_task_id", "task_id"),
        Index("ix_document_status_namespace_status", "namespace_id", "status"),
    )

    def __repr__(self):
        return f"<DocumentProcessingStatus(document_id='{self.document_id}', status='{self.status}')>"


class VectorDocument(Base):
    """
    Единое хранилище векторных документов для всех сервисов (RAG, CRM, Agents).

    Используется для семантического поиска через pgvector.
    Изоляция данных через namespace_id и company_id.
    """

    __tablename__ = "vector_documents"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    namespace_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    document_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    document_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(1024), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    metadata_: Mapped[Dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_vd_namespace_company", "namespace_id", "company_id"),
        Index("ix_vd_document_id", "document_id"),
        Index(
            "ix_vd_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self):
        return f"<VectorDocument(id='{self.id}', namespace='{self.namespace_id}', doc='{self.document_id}')>"

