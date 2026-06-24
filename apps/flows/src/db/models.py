"""
Модели базы данных сервиса flows.
"""

from datetime import datetime, timezone
from typing import override

from sqlalchemy import (
    BigInteger,
    Boolean,
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


class EvaluationSuites(Base):
    """First-class evaluation suite metadata."""

    __tablename__: str = "evaluation_suites"

    suite_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    flow_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[JsonArray] = mapped_column(JSONB, default=list)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("company_id", "flow_id", "name", name="uq_evaluation_suites_company_flow_name"),
        Index("ix_evaluation_suites_company_flow", "company_id", "flow_id"),
    )

    @override
    def __repr__(self) -> str:
        return f"<EvaluationSuites(suite_id='{self.suite_id}', flow_id='{self.flow_id}')>"


class EvaluationCases(Base):
    """First-class evaluation test case."""

    __tablename__: str = "evaluation_cases"

    case_id: Mapped[str] = mapped_column(String, primary_key=True)
    suite_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_suites.suite_id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    flow_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("company_id", "suite_id", "name", name="uq_evaluation_cases_suite_name"),
        Index("ix_evaluation_cases_company_suite", "company_id", "suite_id"),
        Index("ix_evaluation_cases_company_flow", "company_id", "flow_id"),
    )

    @override
    def __repr__(self) -> str:
        return f"<EvaluationCases(case_id='{self.case_id}', suite_id='{self.suite_id}')>"


class EvaluationRubrics(Base):
    """Reusable LLM judge rubric metadata."""

    __tablename__: str = "evaluation_rubrics"

    rubric_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    flow_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[JsonArray] = mapped_column(JSONB, default=list)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("company_id", "flow_id", "name", name="uq_evaluation_rubrics_company_flow_name"),
        Index("ix_evaluation_rubrics_company_flow", "company_id", "flow_id"),
    )

    @override
    def __repr__(self) -> str:
        return f"<EvaluationRubrics(rubric_id='{self.rubric_id}', flow_id='{self.flow_id}')>"


class EvaluationRubricVersions(Base):
    """Immutable rubric prompt version used by LLM judge checks."""

    __tablename__: str = "evaluation_rubric_versions"

    rubric_version_id: Mapped[str] = mapped_column(String, primary_key=True)
    rubric_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_rubrics.rubric_id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    flow_id: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    pass_threshold: Mapped[float] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("company_id", "rubric_id", "version", name="uq_evaluation_rubric_versions_version"),
        Index("ix_evaluation_rubric_versions_company_rubric", "company_id", "rubric_id"),
    )

    @override
    def __repr__(self) -> str:
        return f"<EvaluationRubricVersions(rubric_id='{self.rubric_id}', version={self.version})>"


class EvaluationSuiteVersions(Base):
    """Immutable snapshot of a suite and its cases used by a run."""

    __tablename__: str = "evaluation_suite_versions"

    suite_version_id: Mapped[str] = mapped_column(String, primary_key=True)
    suite_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_suites.suite_id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    flow_id: Mapped[str] = mapped_column(String, nullable=False)
    flow_config_version: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    suite_snapshot: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    cases_snapshot: Mapped[JsonArray] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("company_id", "suite_id", "version", name="uq_evaluation_suite_versions_version"),
        Index("ix_evaluation_suite_versions_company_suite", "company_id", "suite_id"),
    )

    @override
    def __repr__(self) -> str:
        return f"<EvaluationSuiteVersions(suite_id='{self.suite_id}', version={self.version})>"


class EvaluationRuns(Base):
    """Evaluation run over an immutable suite version."""

    __tablename__: str = "evaluation_runs"

    run_id: Mapped[str] = mapped_column(String, primary_key=True)
    suite_id: Mapped[str] = mapped_column(String, nullable=False)
    suite_version_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_suite_versions.suite_version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    flow_id: Mapped[str] = mapped_column(String, nullable=False)
    flow_config_version: Mapped[str] = mapped_column(String, nullable=False)
    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    trigger: Mapped[str] = mapped_column(String, nullable=False)
    scope: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String, default=None)
    taskiq_task_id: Mapped[str | None] = mapped_column(String, default=None)
    gate_policy_id: Mapped[str | None] = mapped_column(String, default=None)
    gate_state: Mapped[str | None] = mapped_column(String, default=None)
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    trials: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_case_runs: Mapped[int] = mapped_column(Integer, nullable=False)
    passed_case_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_case_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_case_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    canceled_case_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_score: Mapped[float | None] = mapped_column(default=None)
    average_duration_ms: Mapped[float | None] = mapped_column(default=None)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    billing_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint(
            "company_id",
            "suite_id",
            "branch_id",
            "idempotency_key",
            name="uq_evaluation_runs_idempotency",
        ),
        Index("ix_evaluation_runs_company_suite", "company_id", "suite_id"),
        Index("ix_evaluation_runs_company_flow_branch", "company_id", "flow_id", "branch_id"),
    )

    @override
    def __repr__(self) -> str:
        return f"<EvaluationRuns(run_id='{self.run_id}', state='{self.state}')>"


class EvaluationRunJobs(Base):
    """Durable enqueue outbox for evaluation run execution."""

    __tablename__: str = "evaluation_run_jobs"

    run_job_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    taskiq_task_id: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    context_data: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    trace_context: Mapped[JsonObject | None] = mapped_column(JSONB, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    enqueued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("company_id", "run_id", name="uq_evaluation_run_jobs_run"),
        UniqueConstraint("company_id", "taskiq_task_id", name="uq_evaluation_run_jobs_taskiq"),
        Index("ix_evaluation_run_jobs_company_state", "company_id", "state", "created_at"),
    )

    @override
    def __repr__(self) -> str:
        return f"<EvaluationRunJobs(run_id='{self.run_id}', state='{self.state}')>"


class EvaluationCaseRuns(Base):
    """Evaluation result for one test case inside a run."""

    __tablename__: str = "evaluation_case_runs"

    case_run_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(String, nullable=False)
    trial_index: Mapped[int] = mapped_column(Integer, nullable=False)
    suite_id: Mapped[str] = mapped_column(String, nullable=False)
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    flow_id: Mapped[str] = mapped_column(String, nullable=False)
    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    task_id: Mapped[str | None] = mapped_column(String, default=None)
    context_id: Mapped[str | None] = mapped_column(String, default=None)
    session_id: Mapped[str | None] = mapped_column(String, default=None)
    trace_id: Mapped[str | None] = mapped_column(String, default=None)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    billing_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    turns_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scores: Mapped[JsonObject | None] = mapped_column(JSONB, default=None)
    total_score: Mapped[float | None] = mapped_column(default=None)
    judge_feedback: Mapped[str | None] = mapped_column(Text, default=None)
    dialog: Mapped[JsonArray] = mapped_column(JSONB, default=list)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint(
            "company_id",
            "run_id",
            "case_id",
            "trial_index",
            name="uq_evaluation_case_runs_run_case_trial",
        ),
        Index("ix_evaluation_case_runs_company_run", "company_id", "run_id"),
        Index("ix_evaluation_case_runs_company_case", "company_id", "case_id"),
    )

    @override
    def __repr__(self) -> str:
        return (
            f"<EvaluationCaseRuns(run_id='{self.run_id}', "
            + f"case_id='{self.case_id}', trial_index={self.trial_index})>"
        )


class EvaluationRunEvents(Base):
    """Append-only event stream for evaluation run UI."""

    __tablename__: str = "evaluation_run_events"

    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    case_run_id: Mapped[str | None] = mapped_column(String, default=None)
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("company_id", "run_id", "sequence", name="uq_evaluation_run_events_sequence"),
        Index("ix_evaluation_run_events_company_run", "company_id", "run_id"),
    )

    @override
    def __repr__(self) -> str:
        return f"<EvaluationRunEvents(run_id='{self.run_id}', sequence={self.sequence})>"


class EvaluationAnnotations(Base):
    """Human review annotations attached to evaluation runs and case runs."""

    __tablename__: str = "evaluation_annotations"

    annotation_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    case_run_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("evaluation_case_runs.case_run_id", ondelete="CASCADE"),
        default=None,
    )
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    case_id: Mapped[str | None] = mapped_column(String, default=None)
    annotation_type: Mapped[str] = mapped_column(String, nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    payload: Mapped[JsonObject] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)

    __table_args__: tuple[Index, ...] = (
        Index("ix_evaluation_annotations_company_run", "company_id", "run_id"),
        Index(
            "ix_evaluation_annotations_company_case_run",
            "company_id",
            "case_run_id",
        ),
    )

    @override
    def __repr__(self) -> str:
        return f"<EvaluationAnnotations(annotation_id='{self.annotation_id}', run_id='{self.run_id}')>"


class EvaluationBaselines(Base):
    """Pinned baseline run for a suite branch."""

    __tablename__: str = "evaluation_baselines"

    baseline_id: Mapped[str] = mapped_column(String, primary_key=True)
    suite_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_suites.suite_id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    flow_id: Mapped[str] = mapped_column(String, nullable=False)
    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    run_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_runs.run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("company_id", "suite_id", "branch_id", name="uq_evaluation_baselines_suite_branch"),
        Index("ix_evaluation_baselines_company_suite", "company_id", "suite_id"),
    )

    @override
    def __repr__(self) -> str:
        return f"<EvaluationBaselines(suite_id='{self.suite_id}', branch_id='{self.branch_id}')>"


class EvaluationGatePolicies(Base):
    """CI/nightly gate policy for a suite branch."""

    __tablename__: str = "evaluation_gate_policies"

    gate_policy_id: Mapped[str] = mapped_column(String, primary_key=True)
    suite_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_suites.suite_id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    flow_id: Mapped[str] = mapped_column(String, nullable=False)
    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    min_pass_rate: Mapped[float] = mapped_column(nullable=False)
    min_average_score: Mapped[float | None] = mapped_column(default=None)
    max_failed_case_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_error_case_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_average_duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    require_baseline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    min_baseline_score_delta: Mapped[float | None] = mapped_column(default=None)
    max_baseline_duration_delta_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("company_id", "suite_id", "branch_id", "name", name="uq_evaluation_gate_policy_name"),
        Index("ix_evaluation_gate_policies_company_suite", "company_id", "suite_id"),
    )

    @override
    def __repr__(self) -> str:
        return f"<EvaluationGatePolicies(gate_policy_id='{self.gate_policy_id}', suite_id='{self.suite_id}')>"


class EvaluationGateResults(Base):
    """Immutable result of applying a gate policy to a run."""

    __tablename__: str = "evaluation_gate_results"

    gate_result_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    gate_policy_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_gate_policies.gate_policy_id", ondelete="RESTRICT"),
        nullable=False,
    )
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    metrics: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    violations: Mapped[JsonArray] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint("company_id", "run_id", name="uq_evaluation_gate_results_run"),
        Index("ix_evaluation_gate_results_company_policy", "company_id", "gate_policy_id"),
    )

    @override
    def __repr__(self) -> str:
        return f"<EvaluationGateResults(run_id='{self.run_id}', state='{self.state}')>"


class EvaluationMonitors(Base):
    """Production trace sampling monitor for online evaluation workflows."""

    __tablename__: str = "evaluation_monitors"

    monitor_id: Mapped[str] = mapped_column(String, primary_key=True)
    suite_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_suites.suite_id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    flow_id: Mapped[str] = mapped_column(String, nullable=False)
    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    state: Mapped[str] = mapped_column(String, nullable=False)
    sampling_rate: Mapped[float] = mapped_column(nullable=False)
    max_traces_per_sample: Mapped[int] = mapped_column(Integer, nullable=False)
    filter: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    gate_policy_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("evaluation_gate_policies.gate_policy_id", ondelete="RESTRICT"),
        default=None,
    )
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now, onupdate=utc_now)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint(
            "company_id",
            "suite_id",
            "branch_id",
            "name",
            name="uq_evaluation_monitors_name",
        ),
        Index("ix_evaluation_monitors_company_suite", "company_id", "suite_id"),
        Index("ix_evaluation_monitors_company_flow_branch", "company_id", "flow_id", "branch_id"),
    )

    @override
    def __repr__(self) -> str:
        return f"<EvaluationMonitors(monitor_id='{self.monitor_id}', state='{self.state}')>"


class EvaluationMonitorObservations(Base):
    """Sampled production trace observation for an evaluation monitor."""

    __tablename__: str = "evaluation_monitor_observations"

    observation_id: Mapped[str] = mapped_column(String, primary_key=True)
    monitor_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_monitors.monitor_id", ondelete="CASCADE"),
        nullable=False,
    )
    suite_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_suites.suite_id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    flow_id: Mapped[str] = mapped_column(String, nullable=False)
    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    trace_id: Mapped[str] = mapped_column(String, nullable=False)
    task_id: Mapped[str | None] = mapped_column(String, default=None)
    session_id: Mapped[str | None] = mapped_column(String, default=None)
    state: Mapped[str] = mapped_column(String, nullable=False)
    span_count: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    sampled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)
    curated_case_id: Mapped[str | None] = mapped_column(String, default=None)

    __table_args__: tuple[UniqueConstraint | Index, ...] = (
        UniqueConstraint(
            "company_id",
            "monitor_id",
            "trace_id",
            name="uq_evaluation_monitor_observations_trace",
        ),
        Index(
            "ix_evaluation_monitor_observations_company_monitor",
            "company_id",
            "monitor_id",
            "sampled_at",
        ),
        Index("ix_evaluation_monitor_observations_company_trace", "company_id", "trace_id"),
    )

    @override
    def __repr__(self) -> str:
        return f"<EvaluationMonitorObservations(trace_id='{self.trace_id}', state='{self.state}')>"


class EvaluationPairwiseJudgments(Base):
    """Human or LLM pairwise judgment over two evaluation case runs."""

    __tablename__: str = "evaluation_pairwise_judgments"

    pairwise_judgment_id: Mapped[str] = mapped_column(String, primary_key=True)
    company_id: Mapped[str] = mapped_column(String, nullable=False)
    suite_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_suites.suite_id", ondelete="CASCADE"),
        nullable=False,
    )
    flow_id: Mapped[str] = mapped_column(String, nullable=False)
    branch_id: Mapped[str] = mapped_column(String, nullable=False)
    left_run_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    right_run_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    left_case_run_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_case_runs.case_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    right_case_run_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("evaluation_case_runs.case_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    mode: Mapped[str] = mapped_column(String, nullable=False)
    preferred: Mapped[str] = mapped_column(String, nullable=False)
    rubric_version_id: Mapped[str | None] = mapped_column(
        String,
        ForeignKey("evaluation_rubric_versions.rubric_version_id", ondelete="RESTRICT"),
        default=None,
    )
    scores: Mapped[JsonObject] = mapped_column(JSONB, nullable=False, default=dict)
    feedback: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), insert_default=utc_now)

    __table_args__: tuple[Index, ...] = (
        Index(
            "ix_evaluation_pairwise_judgments_company_suite",
            "company_id",
            "suite_id",
            "created_at",
        ),
        Index(
            "ix_evaluation_pairwise_judgments_company_left_case_run",
            "company_id",
            "left_case_run_id",
        ),
        Index(
            "ix_evaluation_pairwise_judgments_company_right_case_run",
            "company_id",
            "right_case_run_id",
        ),
    )

    @override
    def __repr__(self) -> str:
        return (
            "<EvaluationPairwiseJudgments("
            + f"pairwise_judgment_id='{self.pairwise_judgment_id}', "
            + f"preferred='{self.preferred}')>"
        )


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


