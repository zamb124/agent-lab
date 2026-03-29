"""
Модели shared-базы данных.

Таблицы platform БД: storage, users, variables, usage, namespaces, spans, push_subscriptions.
"""

from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy import String, Text, DateTime, Integer, Boolean, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from core.db.models.base import Base


class Storage(Base):
    """
    Таблица для key-value хранения сущностей.

    Ключи имеют префиксы:
    - agent:flow_id
    - flow:flow_id
    - session:session_id
    """

    __tablename__ = "storage"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("key", name="uq_storage_key"),
        Index("ix_storage_key_prefix", "key"),
        Index("ix_storage_updated_at", "updated_at"),
        Index("ix_storage_expired_at", "expired_at"),
        Index("ix_storage_key_created_at", "key", "created_at"),
        Index("ix_storage_key_updated_at", "key", "updated_at"),
        Index("ix_storage_key_expired_at", "key", "expired_at"),
    )

    def __repr__(self) -> str:
        return f"<Storage(key='{self.key}', updated_at='{self.updated_at}')>"


class Users(Base):
    """
    Таблица для хранения пользователей и аутентификации.

    Ключи имеют префиксы:
    - user:user_id (основная запись пользователя - source of truth)
    - user_providers:user_id (провайдеры)
    - auth_session:session_id (сессии)
    - auth_state:state (временные OAuth-состояния)
    """

    __tablename__ = "users"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

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
            postgresql_where=text("key LIKE 'user_providers:%'"),
        ),
    )

    def __repr__(self) -> str:
        return f"<Users(key='{self.key}', updated_at='{self.updated_at}')>"


class Variables(Base):
    """
    Таблица для переменных всех компаний.

    Ключи имеют формат: company:{company_id}:var:{key}
    """

    __tablename__ = "variables"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("key", name="uq_variables_key"),
        Index("ix_variables_key_prefix", "key"),
        Index("ix_variables_updated_at", "updated_at"),
        Index("ix_variables_expired_at", "expired_at"),
    )

    def __repr__(self) -> str:
        return f"<Variables(key='{self.key}', updated_at='{self.updated_at}')>"


class Usage(Base):
    """
    Таблица для записей использования ресурсов (биллинг).

    Ключи имеют формат: company:{company_id}:usage:{resource_name}:{usage_id}
    """

    __tablename__ = "usage"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("key", name="uq_usage_key"),
        Index("ix_usage_key_prefix", "key"),
        Index("ix_usage_updated_at", "updated_at"),
        Index("ix_usage_expired_at", "expired_at"),
        Index("ix_usage_company_id", text("(value->>'company_id')")),
        Index("ix_usage_user_id", text("(value->>'user_id')")),
        Index("ix_usage_timestamp", text("(value->>'timestamp')")),
        Index("ix_usage_resource_name", text("(value->>'resource_name')")),
    )

    def __repr__(self) -> str:
        return f"<Usage(key='{self.key}', updated_at='{self.updated_at}')>"


class Namespaces(Base):
    """
    Таблица для namespace (изолированные области данных).

    Ключи имеют формат: namespace:{company_id}:{namespace_name}
    """

    __tablename__ = "namespaces"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("key", name="uq_namespaces_key"),
        Index("ix_namespaces_key_prefix", "key"),
        Index("ix_namespaces_company_id", text("(value->>'company_id')")),
    )

    def __repr__(self) -> str:
        return f"<Namespaces(key='{self.key}', updated_at='{self.updated_at}')>"


class Spans(Base):
    """
    Таблица для хранения OpenTelemetry spans.

    Нормализованная структура для быстрого поиска по user_id, flow_id, session.
    """

    __tablename__ = "spans"

    span_id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    trace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    parent_span_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    operation_name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    user_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_groups: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    session_auth: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    session_agent: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    flow_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    task_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    context_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    skill_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    channel: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    node_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    agent_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_resume: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    events: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    __table_args__ = ()

    def __repr__(self) -> str:
        return f"<Spans(span_id='{self.span_id}', trace_id='{self.trace_id}', operation_name='{self.operation_name}')>"


class CalendarEventRecord(Base):
    """Реляционная таблица событий платформенного календаря."""

    __tablename__ = "calendar_events"

    event_id: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    company_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    namespace: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    attendees: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    recurrence_rule: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recurrence_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    series_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    deep_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    external_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_by_user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    updated_by_user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("company_id", "source", "source_id", name="uq_calendar_events_company_source"),
        Index("ix_calendar_events_company_time", "company_id", "start_at", "end_at"),
        Index("ix_calendar_events_company_kind_time", "company_id", "kind", "start_at"),
        Index("ix_calendar_events_attendees_gin", "attendees", postgresql_using="gin"),
        Index("ix_calendar_events_external_refs_gin", "external_refs", postgresql_using="gin"),
        Index("ix_calendar_events_metadata_gin", "metadata", postgresql_using="gin"),
    )


class CalendarIntegrationRecord(Base):
    """Реляционная таблица интеграций календаря на уровне пользователя."""

    __tablename__ = "calendar_integrations"

    integration_id: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    company_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    credentials: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("company_id", "user_id", "provider", name="uq_calendar_integrations_user_provider"),
        Index("ix_calendar_integrations_credentials_gin", "credentials", postgresql_using="gin"),
        Index("ix_calendar_integrations_settings_gin", "settings", postgresql_using="gin"),
    )


class SchedulerTaskRecord(Base):
    """Служебная таблица задач платформенного scheduler (shared БД)."""

    __tablename__ = "scheduler_tasks"

    id: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    company_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    schedule_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    target_service: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    task_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    queue_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    schedule_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    cron: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    interval_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="pending")
    created_by_user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_scheduler_tasks_company_status", "company_id", "status"),
        Index("ix_scheduler_tasks_company_service", "company_id", "target_service"),
        Index("ix_scheduler_tasks_company_task", "company_id", "task_name"),
        Index("ix_scheduler_tasks_company_next_run", "company_id", "next_run_at"),
    )


class PushSubscription(Base):
    """Подписка пользователя на push-уведомления."""

    __tablename__ = "push_subscriptions"

    id: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    keys: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    platform: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_push_subscriptions_user_endpoint", "user_id", "endpoint"),
    )

    def __repr__(self) -> str:
        return f"<PushSubscription(user_id={self.user_id}, platform={self.platform})>"
