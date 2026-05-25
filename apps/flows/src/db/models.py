"""
Модели базы данных сервиса flows.
"""

from datetime import date, datetime, timezone
from typing import override

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models import Base
from core.types import JsonArray, JsonObject


def utc_now() -> datetime:
    """Возвращает текущее время UTC."""
    return datetime.now(timezone.utc)


class Flows(Base):
    """
    Актуальные конфиги flow (KV).

    Ключи: flow:{flow_id}
    """

    __tablename__: str = "flows"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[JsonObject] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("key", name="uq_flows_key"),
        Index("ix_flows_key_prefix", "key"),
        Index("ix_flows_updated_at", "updated_at"),
        Index("ix_flows_expired_at", "expired_at"),
    )

    @override
    def __repr__(self) -> str:
        return f"<Flows(key='{self.key}', updated_at='{self.updated_at}')>"


class FlowsVersions(Base):
    """
    История версий flow.

    Ключи: flow:{flow_id}_v{version}
    """

    __tablename__: str = "flows_versions"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[JsonObject] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("key", name="uq_flows_versions_key"),
        Index("ix_flows_versions_key_prefix", "key"),
        Index("ix_flows_versions_updated_at", "updated_at"),
        Index("ix_flows_versions_expired_at", "expired_at"),
    )

    @override
    def __repr__(self) -> str:
        return f"<FlowsVersions(key='{self.key}', updated_at='{self.updated_at}')>"


class Nodes(Base):
    """
    Таблица для хранения нод.

    Ключи имеют формат: node:{node_id}
    """

    __tablename__: str = "nodes"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[JsonObject] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("key", name="uq_nodes_key"),
        Index("ix_nodes_key_prefix", "key"),
        Index("ix_nodes_updated_at", "updated_at"),
        Index("ix_nodes_expired_at", "expired_at"),
    )

    @override
    def __repr__(self) -> str:
        return f"<Nodes(key='{self.key}', updated_at='{self.updated_at}')>"


class Tools(Base):
    """
    Таблица для хранения инструментов (tools).

    Ключи имеют формат: tool:{tool_id}
    """

    __tablename__: str = "tools"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[JsonObject] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("key", name="uq_tools_key"),
        Index("ix_tools_key_prefix", "key"),
        Index("ix_tools_updated_at", "updated_at"),
        Index("ix_tools_expired_at", "expired_at"),
    )

    @override
    def __repr__(self) -> str:
        return f"<Tools(key='{self.key}', updated_at='{self.updated_at}')>"


class WorkflowInstances(Base):
    """Current durable workflow head/projection."""

    __tablename__: str = "workflow_instances"

    workflow_instance_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    flow_id: Mapped[str | None] = mapped_column(String, default=None)
    context_id: Mapped[str | None] = mapped_column(String, default=None)
    task_id: Mapped[str | None] = mapped_column(String, default=None)
    user_id: Mapped[str | None] = mapped_column(String, default=None)
    flow_branch_id: Mapped[str | None] = mapped_column(String, default=None)
    active_execution_branch_id: Mapped[str] = mapped_column(String, nullable=False)
    head_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    head_state_hash: Mapped[str | None] = mapped_column(String, default=None)
    latest_snapshot_id: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("company_id", "session_id", name="uq_workflow_instances_company_session"),
        Index("ix_workflow_instances_company_flow_updated", "company_id", "flow_id", "updated_at"),
        Index("ix_workflow_instances_company_user_updated", "company_id", "user_id", "updated_at"),
        Index("ix_workflow_instances_company_task", "company_id", "task_id"),
        Index("ix_workflow_instances_company_context", "company_id", "context_id"),
        Index("ix_workflow_instances_company_status", "company_id", "status"),
        Index("ix_workflow_instances_company_updated", "company_id", "updated_at"),
    )


class ExecutionBranches(Base):
    """Append-only execution branch lineage for fork/rewind/retry."""

    __tablename__: str = "execution_branches"

    execution_branch_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    parent_execution_branch_id: Mapped[str | None] = mapped_column(String, default=None)
    base_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    base_state_hash: Mapped[str | None] = mapped_column(String, default=None)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)

    __table_args__: tuple[Index, ...] = (
        Index("ix_execution_branches_company_session", "company_id", "session_id"),
        Index("ix_execution_branches_parent", "parent_execution_branch_id"),
    )


class WorkflowEvents(Base):
    """Canonical append-only event history."""

    __tablename__: str = "workflow_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    execution_branch_id: Mapped[str] = mapped_column(String, nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[JsonObject] = mapped_column(JSONB, nullable=False, default=dict)
    state_delta: Mapped[JsonObject] = mapped_column(JSONB, nullable=False, default=dict)
    prev_state_hash: Mapped[str | None] = mapped_column(String, default=None)
    next_state_hash: Mapped[str] = mapped_column(String, nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String, default=None)
    correlation_id: Mapped[str | None] = mapped_column(String, default=None)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint(
            "company_id",
            "session_id",
            "execution_branch_id",
            "sequence",
            name="uq_workflow_events_sequence",
        ),
        Index("ix_workflow_events_company_session_sequence", "company_id", "session_id", "sequence"),
        Index("ix_workflow_events_branch_sequence", "execution_branch_id", "sequence"),
        Index("ix_workflow_events_type", "event_type"),
    )


class WorkflowSnapshots(Base):
    """Materialized projection anchors for rehydration."""

    __tablename__: str = "workflow_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    execution_branch_id: Mapped[str] = mapped_column(String, nullable=False)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state_json: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    state_hash: Mapped[str] = mapped_column(String, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint(
            "company_id",
            "session_id",
            "execution_branch_id",
            "sequence",
            name="uq_workflow_snapshots_sequence",
        ),
        Index("ix_workflow_snapshots_company_session_sequence", "company_id", "session_id", "sequence"),
        Index("ix_workflow_snapshots_branch_sequence", "execution_branch_id", "sequence"),
    )


class ActivityTasks(Base):
    """Logical durable activity identity scoped by workflow branch."""

    __tablename__: str = "activity_tasks"

    activity_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    execution_branch_id: Mapped[str] = mapped_column(String, nullable=False)
    node_id: Mapped[str | None] = mapped_column(String, default=None)
    tool_call_id: Mapped[str | None] = mapped_column(String, default=None)
    activity_type: Mapped[str] = mapped_column(String, nullable=False)
    input_hash: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String, default=None)
    side_effect_policy: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint(
            "company_id",
            "session_id",
            "execution_branch_id",
            "idempotency_key",
            name="uq_activity_tasks_branch_idempotency_key",
        ),
        Index("ix_activity_tasks_company_session", "company_id", "session_id"),
        Index("ix_activity_tasks_branch", "execution_branch_id"),
        Index("ix_activity_tasks_node", "node_id"),
    )


class ActivityAttempts(Base):
    """Append-only durable activity attempts with lease/result/error per attempt."""

    __tablename__: str = "activity_attempts"

    activity_attempt_id: Mapped[str] = mapped_column(String, primary_key=True)
    activity_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("activity_tasks.activity_id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    execution_branch_id: Mapped[str] = mapped_column(String, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    result_json: Mapped[JsonObject | None] = mapped_column(JSONB, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint(
            "activity_id",
            "attempt",
            name="uq_activity_attempts_activity_attempt",
        ),
        Index("ix_activity_attempts_activity", "activity_id"),
        Index("ix_activity_attempts_branch_status", "execution_branch_id", "status"),
        Index("ix_activity_attempts_company_session", "company_id", "session_id"),
    )


class EvaluationResults(Base):
    """
    Таблица для хранения результатов evaluation.
    """

    __tablename__: str = "evaluation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    flow_id: Mapped[str] = mapped_column(String)
    branch_id: Mapped[str] = mapped_column(String)
    run_date: Mapped[date] = mapped_column(Date)
    iteration: Mapped[int] = mapped_column(Integer)
    test_case_id: Mapped[str] = mapped_column(String)
    task_id: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String)
    duration_ms: Mapped[int] = mapped_column(Integer)
    turns_count: Mapped[int] = mapped_column(Integer, default=0)
    dialog: Mapped[JsonObject | None] = mapped_column(JSONB, default=None)
    scores: Mapped[JsonObject | None] = mapped_column(JSONB, default=None)
    judge_feedback: Mapped[str | None] = mapped_column(String, default=None)
    error: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint(
            "flow_id", "branch_id", "run_date", "iteration", "test_case_id",
            name="uq_evaluation_results"
        ),
        Index("ix_evaluation_results_flow_skill", "flow_id", "branch_id"),
    )

    @override
    def __repr__(self) -> str:
        return f"<EvaluationResults(flow_id='{self.flow_id}', test_case_id='{self.test_case_id}')>"


class Resources(Base):
    """
    Таблица для хранения shared ресурсов.

    Ключи имеют формат: resource:{resource_id}
    """

    __tablename__: str = "resources"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[JsonObject] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("key", name="uq_resources_key"),
        Index("ix_resources_key_prefix", "key"),
        Index("ix_resources_updated_at", "updated_at"),
        Index("ix_resources_expired_at", "expired_at"),
    )

    @override
    def __repr__(self) -> str:
        return f"<Resources(key='{self.key}', updated_at='{self.updated_at}')>"


class OperatorQueues(Base):
    """
    Очередь назначения задач оператору (поддержка, эскалация).
    """

    __tablename__: str = "operator_queues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2048), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now
    )

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("company_id", "slug", name="uq_operator_queues_company_slug"),
        Index("ix_operator_queues_company_id", "company_id"),
    )

    @override
    def __repr__(self) -> str:
        return f"<OperatorQueues(id='{self.id}', slug='{self.slug}')>"


class OperatorQueueMembers(Base):
    """Участник очереди (оператор)."""

    __tablename__: str = "operator_queue_members"

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

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("queue_id", "user_id", name="uq_operator_queue_members_queue_user"),
        Index("ix_operator_queue_members_user_id", "user_id"),
    )

    @override
    def __repr__(self) -> str:
        return f"<OperatorQueueMembers(queue_id='{self.queue_id}', user_id='{self.user_id}')>"


class OperatorTasks(Base):
    """
    Задача оператора, созданная при interrupt (operator_task).
    """

    __tablename__: str = "operator_tasks"

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
    a2a_task_id: Mapped[str | None] = mapped_column(String(255), default=None)
    context_id: Mapped[str | None] = mapped_column(String(255), default=None)
    correlation_id: Mapped[str | None] = mapped_column(String(36), default=None, index=True)
    interrupt_snapshot: Mapped[JsonObject | None] = mapped_column(JSONB, default=None)
    claimed_by_user_id: Mapped[str | None] = mapped_column(String(255), default=None)
    resolution_payload: Mapped[JsonObject | None] = mapped_column(JSONB, default=None)
    dialog_log: Mapped[JsonArray | None] = mapped_column(JSONB, default=None)
    context_data_snapshot: Mapped[JsonObject | None] = mapped_column(JSONB, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now
    )

    __table_args__: tuple[Index | UniqueConstraint, ...] = (
        Index("ix_operator_tasks_queue_status", "queue_id", "status"),
        UniqueConstraint("company_id", "correlation_id", name="uq_operator_tasks_company_correlation"),
    )

    @override
    def __repr__(self) -> str:
        return f"<OperatorTasks(id='{self.id}', status='{self.status}')>"
