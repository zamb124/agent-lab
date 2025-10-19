"""
Модели базы данных SQLAlchemy.
Таблицы для key-value storage с маршрутизацией.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Index, UniqueConstraint, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()


class Storage(Base):
    """
    Основная таблица для key-value хранения сущностей.

    Ключи имеют префиксы:
    - agent:agent_id
    - flow:flow_id
    - session:session_id
    
    Задачи (task:*) теперь в отдельной таблице Tasks.
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


class Tasks(Base):
    """
    Таблица для задач (Tasks).
    
    Ключи имеют формат: task:task_id
    Физическая изоляция задач для лучшей производительности.
    """

    __tablename__ = "tasks"

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
        UniqueConstraint("key", name="uq_tasks_key"),
        Index("ix_tasks_key_prefix", "key"),
        Index("ix_tasks_updated_at", "updated_at"),
        Index("ix_tasks_expired_at", "expired_at"),
        Index("ix_tasks_key_created_at", "key", "created_at"),
        Index("ix_tasks_key_updated_at", "key", "updated_at"),
        Index("ix_tasks_status", (text("(value->>'status')"))),
        Index("ix_tasks_execute_at", (text("(value->>'execute_at')"))),
        Index("ix_tasks_session_flow", (text("(value->>'session_id')")), (text("(value->>'flow_id')"))),
        Index(
            "ix_tasks_pending_ready",
            (text("(value->>'status')")),
            (text("(value->>'execute_at')")),
            postgresql_where=text("(value->>'status') = 'pending'")
        ),
    )

    def __repr__(self):
        return f"<Tasks(key='{self.key}', updated_at='{self.updated_at}')>"


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
