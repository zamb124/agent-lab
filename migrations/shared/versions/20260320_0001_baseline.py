"""Baseline shared DB

Revision ID: shared_0001
Revises:
Create Date: 2026-03-20
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "shared_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "storage",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_storage_key"),
    )
    op.create_index("ix_storage_key_prefix", "storage", ["key"])
    op.create_index("ix_storage_updated_at", "storage", ["updated_at"])
    op.create_index("ix_storage_expired_at", "storage", ["expired_at"])
    op.create_index("ix_storage_key_created_at", "storage", ["key", "created_at"])
    op.create_index("ix_storage_key_updated_at", "storage", ["key", "updated_at"])
    op.create_index("ix_storage_key_expired_at", "storage", ["key", "expired_at"])

    op.create_table(
        "users",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_users_key"),
    )
    op.create_index("ix_users_key_prefix", "users", ["key"])
    op.create_index("ix_users_updated_at", "users", ["updated_at"])
    op.create_index("ix_users_expired_at", "users", ["expired_at"])
    op.create_index("ix_users_key_created_at", "users", ["key", "created_at"])
    op.create_index("ix_users_key_updated_at", "users", ["key", "updated_at"])
    op.create_index("ix_users_key_expired_at", "users", ["key", "expired_at"])
    op.create_index(
        "ix_users_providers_jsonb", "users",
        [sa.text("value jsonb_path_ops")],
        postgresql_using="gin",
        postgresql_where=sa.text("key LIKE 'user_providers:%'"),
    )

    op.create_table(
        "variables",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_variables_key"),
    )
    op.create_index("ix_variables_key_prefix", "variables", ["key"])
    op.create_index("ix_variables_updated_at", "variables", ["updated_at"])
    op.create_index("ix_variables_expired_at", "variables", ["expired_at"])

    op.create_table(
        "usage",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_usage_key"),
    )
    op.create_index("ix_usage_key_prefix", "usage", ["key"])
    op.create_index("ix_usage_updated_at", "usage", ["updated_at"])
    op.create_index("ix_usage_expired_at", "usage", ["expired_at"])
    op.create_index("ix_usage_company_id", "usage", [sa.text("(value->>'company_id')")])
    op.create_index("ix_usage_user_id", "usage", [sa.text("(value->>'user_id')")])
    op.create_index("ix_usage_timestamp", "usage", [sa.text("(value->>'timestamp')")])
    op.create_index("ix_usage_resource_name", "usage", [sa.text("(value->>'resource_name')")])

    op.create_table(
        "namespaces",
        sa.Column("key", sa.String(), primary_key=True, nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("key", name="uq_namespaces_key"),
    )
    op.create_index("ix_namespaces_key_prefix", "namespaces", ["key"])
    op.create_index("ix_namespaces_company_id", "namespaces", [sa.text("(value->>'company_id')")])

    op.create_table(
        "spans",
        sa.Column("span_id", sa.String(), primary_key=True, nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("parent_span_id", sa.String(), nullable=True),
        sa.Column("operation_name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("status_message", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("user_name", sa.String(), nullable=True),
        sa.Column("user_groups", postgresql.JSONB(), nullable=True),
        sa.Column("session_auth", sa.String(), nullable=True),
        sa.Column("session_agent", sa.String(), nullable=True),
        sa.Column("agent_id", sa.String(), nullable=True),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("context_id", sa.String(), nullable=True),
        sa.Column("skill_id", sa.String(), nullable=True),
        sa.Column("channel", sa.String(), nullable=True),
        sa.Column("node_id", sa.String(), nullable=True),
        sa.Column("agent_name", sa.String(), nullable=True),
        sa.Column("is_resume", sa.Boolean(), nullable=True),
        sa.Column("attributes", postgresql.JSONB(), nullable=True),
        sa.Column("events", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_spans_span_id", "spans", ["span_id"])
    op.create_index("ix_spans_trace_id", "spans", ["trace_id"])
    op.create_index("ix_spans_parent_span_id", "spans", ["parent_span_id"])
    op.create_index("ix_spans_start_time", "spans", ["start_time"])
    op.create_index("ix_spans_user_id", "spans", ["user_id"])
    op.create_index("ix_spans_session_auth", "spans", ["session_auth"])
    op.create_index("ix_spans_session_agent", "spans", ["session_agent"])
    op.create_index("ix_spans_agent_id", "spans", ["agent_id"])
    op.create_index("ix_spans_task_id", "spans", ["task_id"])
    op.create_index("ix_spans_context_id", "spans", ["context_id"])

    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.String(255), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("endpoint", sa.String(2048), nullable=False, unique=True),
        sa.Column("keys", postgresql.JSONB(), nullable=False),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("platform", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_push_subscriptions_id", "push_subscriptions", ["id"])
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])
    op.create_index("ix_push_subscriptions_user_endpoint", "push_subscriptions", ["user_id", "endpoint"])


def downgrade() -> None:
    op.drop_table("push_subscriptions")
    op.drop_table("spans")
    op.drop_table("namespaces")
    op.drop_table("usage")
    op.drop_table("variables")
    op.drop_table("users")
    op.drop_table("storage")
