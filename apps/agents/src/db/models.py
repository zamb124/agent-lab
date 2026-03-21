"""
Модели базы данных для сервиса agents.
"""

from datetime import datetime, timezone, date
from typing import Any, Optional
from sqlalchemy import String, Index, UniqueConstraint, Integer, Date, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from core.db.models import Base


def utc_now() -> datetime:
    """Возвращает текущее время UTC."""
    return datetime.now(timezone.utc)


class Agents(Base):
    """
    Таблица для хранения агентов (актуальные версии).

    Ключи имеют формат: agent:{agent_id}
    """

    __tablename__ = "agents"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        UniqueConstraint("key", name="uq_agents_key"),
        Index("ix_agents_key_prefix", "key"),
        Index("ix_agents_updated_at", "updated_at"),
        Index("ix_agents_expired_at", "expired_at"),
    )

    def __repr__(self) -> str:
        return f"<Agents(key='{self.key}', updated_at='{self.updated_at}')>"


class AgentsVersions(Base):
    """
    Таблица для хранения версий агентов.

    Ключи имеют формат: agent:{agent_id}_v{version}
    """

    __tablename__ = "agents_versions"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        UniqueConstraint("key", name="uq_agents_versions_key"),
        Index("ix_agents_versions_key_prefix", "key"),
        Index("ix_agents_versions_updated_at", "updated_at"),
        Index("ix_agents_versions_expired_at", "expired_at"),
    )

    def __repr__(self) -> str:
        return f"<AgentsVersions(key='{self.key}', updated_at='{self.updated_at}')>"


class Nodes(Base):
    """
    Таблица для хранения нод.

    Ключи имеют формат: node:{node_id}
    """

    __tablename__ = "nodes"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        UniqueConstraint("key", name="uq_nodes_key"),
        Index("ix_nodes_key_prefix", "key"),
        Index("ix_nodes_updated_at", "updated_at"),
        Index("ix_nodes_expired_at", "expired_at"),
    )

    def __repr__(self) -> str:
        return f"<Nodes(key='{self.key}', updated_at='{self.updated_at}')>"


class Tools(Base):
    """
    Таблица для хранения инструментов (tools).

    Ключи имеют формат: tool:{tool_id}
    """

    __tablename__ = "tools"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        UniqueConstraint("key", name="uq_tools_key"),
        Index("ix_tools_key_prefix", "key"),
        Index("ix_tools_updated_at", "updated_at"),
        Index("ix_tools_expired_at", "expired_at"),
    )

    def __repr__(self) -> str:
        return f"<Tools(key='{self.key}', updated_at='{self.updated_at}')>"


class States(Base):
    """
    Таблица для хранения состояний агентов.

    Ключи имеют формат: company:{company_id}:state:{session_id}
    """

    __tablename__ = "states"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        UniqueConstraint("key", name="uq_states_key"),
        Index("ix_states_key_prefix", "key"),
        Index("ix_states_updated_at", "updated_at"),
        Index("ix_states_expired_at", "expired_at"),
    )

    def __repr__(self) -> str:
        return f"<States(key='{self.key}', updated_at='{self.updated_at}')>"


class EvaluationResults(Base):
    """
    Таблица для хранения результатов evaluation.
    """

    __tablename__ = "evaluation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String)
    skill_id: Mapped[str] = mapped_column(String)
    run_date: Mapped[date] = mapped_column(Date)
    iteration: Mapped[int] = mapped_column(Integer)
    test_case_id: Mapped[str] = mapped_column(String)
    task_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String)
    duration_ms: Mapped[int] = mapped_column(Integer)
    turns_count: Mapped[int] = mapped_column(Integer, default=0)
    dialog: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, default=None)
    scores: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, default=None)
    judge_feedback: Mapped[Optional[str]] = mapped_column(String, default=None)
    error: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)

    __table_args__ = (
        UniqueConstraint(
            "agent_id", "skill_id", "run_date", "iteration", "test_case_id",
            name="uq_evaluation_results"
        ),
        Index("ix_evaluation_results_agent_skill", "agent_id", "skill_id"),
    )

    def __repr__(self) -> str:
        return f"<EvaluationResults(agent_id='{self.agent_id}', test_case_id='{self.test_case_id}')>"


class ScheduledTasks(Base):
    """
    Таблица для хранения scheduled tasks.
    """

    __tablename__ = "scheduled_tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    schedule_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    agent_id: Mapped[str] = mapped_column(String)
    session_id: Mapped[str] = mapped_column(String)
    user_id: Mapped[str] = mapped_column(String)
    schedule_type: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String)
    cron: Mapped[Optional[str]] = mapped_column(String, default=None)
    interval_minutes: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)
    content: Mapped[str] = mapped_column(String)
    tool_args: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, default=None)
    description: Mapped[Optional[str]] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)
    next_run: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)
    error_message: Mapped[Optional[str]] = mapped_column(String, default=None)

    __table_args__ = (
        Index("ix_scheduled_tasks_session_id", "session_id"),
        Index("ix_scheduled_tasks_agent_id", "agent_id"),
        Index("ix_scheduled_tasks_status", "status"),
        Index("ix_scheduled_tasks_next_run", "next_run"),
    )

    def __repr__(self) -> str:
        return f"<ScheduledTasks(id='{self.id}', agent_id='{self.agent_id}', status='{self.status}')>"


class Resources(Base):
    """
    Таблица для хранения shared ресурсов.

    Ключи имеют формат: resource:{resource_id}
    """

    __tablename__ = "resources"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        UniqueConstraint("key", name="uq_resources_key"),
        Index("ix_resources_key_prefix", "key"),
        Index("ix_resources_updated_at", "updated_at"),
        Index("ix_resources_expired_at", "expired_at"),
    )

    def __repr__(self) -> str:
        return f"<Resources(key='{self.key}', updated_at='{self.updated_at}')>"


class Stores(Base):
    """
    Таблица хранения store (единого для всего flow).
    Все агенты в flow используют один и тот же store через store_id.
    """

    __tablename__ = "stores"

    store_id: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    store_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("ix_stores_updated_at", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<Stores(store_id='{self.store_id}', updated_at='{self.updated_at}')>"


class AgentStates(Base):
    """
    Таблица хранения состояний агентов.
    Хранит состояние сессий в формате JSONB.
    Store хранится отдельно в таблице Stores и ссылается через store_id.
    """

    __tablename__ = "agent_states"

    session_id: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    store_id: Mapped[str] = mapped_column(String(255), nullable=False)
    state_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("ix_agent_states_store_id", "store_id"),
        Index("ix_agent_states_updated_at", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<AgentStates(session_id='{self.session_id}', store_id='{self.store_id}')>"

