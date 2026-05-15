"""
Модели базы данных сервиса flows.
"""

from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models import Base


def utc_now() -> datetime:
    """Возвращает текущее время UTC."""
    return datetime.now(timezone.utc)


class Flows(Base):
    """
    Актуальные конфиги flow (KV).

    Ключи: flow:{flow_id}
    """

    __tablename__ = "flows"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        UniqueConstraint("key", name="uq_flows_key"),
        Index("ix_flows_key_prefix", "key"),
        Index("ix_flows_updated_at", "updated_at"),
        Index("ix_flows_expired_at", "expired_at"),
    )

    def __repr__(self) -> str:
        return f"<Flows(key='{self.key}', updated_at='{self.updated_at}')>"


class FlowsVersions(Base):
    """
    История версий flow.

    Ключи: flow:{flow_id}_v{version}
    """

    __tablename__ = "flows_versions"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        UniqueConstraint("key", name="uq_flows_versions_key"),
        Index("ix_flows_versions_key_prefix", "key"),
        Index("ix_flows_versions_updated_at", "updated_at"),
        Index("ix_flows_versions_expired_at", "expired_at"),
    )

    def __repr__(self) -> str:
        return f"<FlowsVersions(key='{self.key}', updated_at='{self.updated_at}')>"


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
    flow_id: Mapped[str] = mapped_column(String)
    branch_id: Mapped[str] = mapped_column(String)
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
            "flow_id", "branch_id", "run_date", "iteration", "test_case_id",
            name="uq_evaluation_results"
        ),
        Index("ix_evaluation_results_flow_skill", "flow_id", "branch_id"),
    )

    def __repr__(self) -> str:
        return f"<EvaluationResults(flow_id='{self.flow_id}', test_case_id='{self.test_case_id}')>"


class ScheduledTasks(Base):
    """
    Таблица для хранения scheduled tasks.
    """

    __tablename__ = "scheduled_tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    schedule_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    flow_id: Mapped[str] = mapped_column(String)
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
        Index("ix_scheduled_tasks_flow_id", "flow_id"),
        Index("ix_scheduled_tasks_status", "status"),
        Index("ix_scheduled_tasks_next_run", "next_run"),
    )

    def __repr__(self) -> str:
        return f"<ScheduledTasks(id='{self.id}', flow_id='{self.flow_id}', status='{self.status}')>"


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


class FlowStates(Base):
    """
    Состояния сессий (JSONB). Store — в таблице stores по store_id.
    """

    __tablename__ = "flow_states"

    session_id: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    store_id: Mapped[str] = mapped_column(String(255), nullable=False)
    state_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("ix_flow_states_store_id", "store_id"),
        Index("ix_flow_states_updated_at", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<FlowStates(session_id='{self.session_id}', store_id='{self.store_id}')>"


class OperatorQueues(Base):
    """
    Очередь назначения задач оператору (поддержка, эскалация).
    """

    __tablename__ = "operator_queues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(2048), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        UniqueConstraint("company_id", "slug", name="uq_operator_queues_company_slug"),
        Index("ix_operator_queues_company_id", "company_id"),
    )

    def __repr__(self) -> str:
        return f"<OperatorQueues(id='{self.id}', slug='{self.slug}')>"


class OperatorQueueMembers(Base):
    """Участник очереди (оператор)."""

    __tablename__ = "operator_queue_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    queue_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("operator_queues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="agent")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)

    __table_args__ = (
        UniqueConstraint("queue_id", "user_id", name="uq_operator_queue_members_queue_user"),
        Index("ix_operator_queue_members_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<OperatorQueueMembers(queue_id='{self.queue_id}', user_id='{self.user_id}')>"


class OperatorTasks(Base):
    """
    Задача оператора, созданная при interrupt (operator_task).
    """

    __tablename__ = "operator_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    queue_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("operator_queues.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    end_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    flow_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    branch_id: Mapped[str] = mapped_column(String(255), nullable=False, default="default")
    a2a_task_id: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    context_id: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(36), default=None, index=True)
    interrupt_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, default=None)
    claimed_by_user_id: Mapped[Optional[str]] = mapped_column(String(255), default=None)
    resolution_payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, default=None)
    dialog_log: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSONB, default=None)
    context_data_snapshot: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        Index("ix_operator_tasks_queue_status", "queue_id", "status"),
        UniqueConstraint("company_id", "correlation_id", name="uq_operator_tasks_company_correlation"),
    )

    def __repr__(self) -> str:
        return f"<OperatorTasks(id='{self.id}', status='{self.status}')>"
