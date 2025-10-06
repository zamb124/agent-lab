"""
Модели базы данных SQLAlchemy.
Одна таблица для key-value storage всех сущностей.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Index, UniqueConstraint, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()


class Storage(Base):
    """
    Единственная таблица для key-value хранения всех сущностей.

    Ключи имеют префиксы:
    - agent:agent_id
    - flow:flow_id
    - task:task_id
    - session:session_id
    """

    __tablename__ = "storage"

    key = Column(String, primary_key=True, index=True)
    value = Column(JSONB, nullable=False)  # JSON данные
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    expired_at = Column(DateTime(timezone=True), nullable=True)  # TTL поле

    # Индексы для быстрого поиска по префиксам и уникальность ключа
    __table_args__ = (
        UniqueConstraint("key", name="uq_storage_key"),  # Явное ограничение уникальности
        Index("ix_storage_key_prefix", "key"),
        Index("ix_storage_updated_at", "updated_at"),
        Index("ix_storage_expired_at", "expired_at"),  # Для TTL очистки
        # Составные индексы для оптимизации запросов по ключу + временным полям
        Index("ix_storage_key_created_at", "key", "created_at"),
        Index("ix_storage_key_updated_at", "key", "updated_at"),
        Index("ix_storage_key_expired_at", "key", "expired_at"),
        # Индексы на конкретные JSON поля для быстрого поиска задач
        Index("ix_storage_task_status", (text("(value->>'status')")), postgresql_where=text("key LIKE 'task:%'")),
        Index("ix_storage_task_session_flow", (text("(value->>'session_id')")), (text("(value->>'flow_id')")), postgresql_where=text("key LIKE 'task:%'")),
    )

    def __repr__(self):
        return f"<Storage(key='{self.key}', updated_at='{self.updated_at}')>"
