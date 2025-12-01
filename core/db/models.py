"""
Модели базы данных SQLAlchemy.
Таблицы для key-value storage с маршрутизацией.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Index, UniqueConstraint, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()


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
    Таблица для хранения состояний агентов (замена checkpointer из LangGraph).
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


class OtelSpans(Base):
    """
    Таблица для OpenTelemetry.

    Ключи имеют формат: otel:{trace_id}:span:{span_id}
    Физическая изоляция spans для лучшей производительности трейсинга.
    """

    __tablename__ = "otel_spans"

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
        UniqueConstraint("key", name="uq_otel_spans_key"),
        Index("ix_otel_spans_key_prefix", "key"),
        Index("ix_otel_spans_updated_at", "updated_at"),
        Index("ix_otel_spans_trace_id", (text("(value->>'trace_id')"))),
        Index("ix_otel_spans_span_type", (text("(value->>'span_type')"))),
        Index("ix_otel_spans_status", (text("(value->>'status')"))),
        Index("ix_otel_spans_start_time", (text("(value->>'start_time')"))),
    )

    def __repr__(self):
        return f"<OtelSpans(key='{self.key}', updated_at='{self.updated_at}')>"

