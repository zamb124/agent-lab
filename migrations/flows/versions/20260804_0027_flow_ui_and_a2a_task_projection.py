"""Flow UI and lossless A2A task projections.

Revision ID: 20260804_0027
Revises: 20260721_0026
Create Date: 2026-08-04
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260804_0027"
down_revision: Union[str, None] = "20260721_0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "a2a_task_projections",
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("context_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("owner_user_id", sa.String(), nullable=False),
        sa.Column("task_state", sa.String(), nullable=False),
        sa.Column("task_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latest_sequence", sa.BigInteger(), nullable=False),
        sa.Column("is_terminal", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("task_id"),
        sa.UniqueConstraint("company_id", "task_id", name="uq_a2a_tasks_company_task"),
    )
    op.create_index(
        "ix_a2a_tasks_company_context_updated",
        "a2a_task_projections",
        ["company_id", "context_id", "updated_at"],
    )
    op.create_index(
        "ix_a2a_tasks_company_flow_updated",
        "a2a_task_projections",
        ["company_id", "flow_id", "updated_at"],
    )
    op.create_index(
        "ix_a2a_tasks_company_session",
        "a2a_task_projections",
        ["company_id", "session_id"],
    )
    op.create_index(
        "ix_a2a_tasks_company_owner_updated",
        "a2a_task_projections",
        ["company_id", "owner_user_id", "updated_at"],
    )
    op.create_index(
        "ix_a2a_tasks_company_state",
        "a2a_task_projections",
        ["company_id", "task_state"],
    )

    op.create_table(
        "a2a_task_messages",
        sa.Column("task_message_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("message_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["a2a_task_projections.task_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("task_message_id"),
        sa.UniqueConstraint("task_id", "message_id", name="uq_a2a_task_messages_task_message"),
        sa.UniqueConstraint("task_id", "ordinal", name="uq_a2a_task_messages_task_ordinal"),
    )
    op.create_index(
        "ix_a2a_task_messages_company_task",
        "a2a_task_messages",
        ["company_id", "task_id"],
    )

    op.create_table(
        "a2a_artifact_projections",
        sa.Column("artifact_projection_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("artifact_id", sa.String(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("artifact_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
        sa.Column("latest_sequence", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["a2a_task_projections.task_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("artifact_projection_id"),
        sa.UniqueConstraint("task_id", "artifact_id", name="uq_a2a_artifacts_task_artifact"),
        sa.UniqueConstraint("task_id", "ordinal", name="uq_a2a_artifacts_task_ordinal"),
    )
    op.create_index(
        "ix_a2a_artifacts_company_task",
        "a2a_artifact_projections",
        ["company_id", "task_id"],
    )

    op.create_table(
        "a2a_task_event_dedup",
        sa.Column("task_event_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("event_identity", sa.String(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_kind", sa.String(), nullable=False),
        sa.Column("event_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_fingerprint", sa.String(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["a2a_task_projections.task_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("task_event_id"),
        sa.UniqueConstraint("task_id", "event_identity", name="uq_a2a_events_task_identity"),
        sa.UniqueConstraint("task_id", "sequence", name="uq_a2a_events_task_sequence"),
    )
    op.create_index(
        "ix_a2a_events_company_task_sequence",
        "a2a_task_event_dedup",
        ["company_id", "task_id", "sequence"],
    )
    op.create_index(
        "ix_a2a_events_unpublished",
        "a2a_task_event_dedup",
        ["published_at", "created_at"],
    )

    op.create_table(
        "flow_ui_share_grants",
        sa.Column("grant_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("flow_id", sa.String(), nullable=False),
        sa.Column("branch_id", sa.String(), nullable=False),
        sa.Column("context_id", sa.String(), nullable=False),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("minimum_revision", sa.BigInteger(), nullable=False),
        sa.Column("permission", sa.String(), nullable=False),
        sa.Column("created_by_user_id", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("grant_id"),
    )
    op.create_index(
        "ix_flow_ui_share_company_context",
        "flow_ui_share_grants",
        ["company_id", "context_id"],
    )
    op.create_index(
        "ix_flow_ui_share_expiry",
        "flow_ui_share_grants",
        ["expires_at", "revoked_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_flow_ui_share_expiry", table_name="flow_ui_share_grants")
    op.drop_index("ix_flow_ui_share_company_context", table_name="flow_ui_share_grants")
    op.drop_table("flow_ui_share_grants")
    op.drop_index("ix_a2a_events_unpublished", table_name="a2a_task_event_dedup")
    op.drop_index("ix_a2a_events_company_task_sequence", table_name="a2a_task_event_dedup")
    op.drop_table("a2a_task_event_dedup")
    op.drop_index("ix_a2a_artifacts_company_task", table_name="a2a_artifact_projections")
    op.drop_table("a2a_artifact_projections")
    op.drop_index("ix_a2a_task_messages_company_task", table_name="a2a_task_messages")
    op.drop_table("a2a_task_messages")
    op.drop_index("ix_a2a_tasks_company_state", table_name="a2a_task_projections")
    op.execute(sa.text("DROP INDEX IF EXISTS ix_a2a_tasks_company_owner_updated"))
    op.drop_index("ix_a2a_tasks_company_session", table_name="a2a_task_projections")
    op.drop_index("ix_a2a_tasks_company_flow_updated", table_name="a2a_task_projections")
    op.drop_index("ix_a2a_tasks_company_context_updated", table_name="a2a_task_projections")
    op.drop_table("a2a_task_projections")
