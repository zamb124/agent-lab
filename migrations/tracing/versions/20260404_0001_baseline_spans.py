"""Baseline platform_tracing: spans

Revision ID: tracing_0001
Revises:
Create Date: 2026-04-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "tracing_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
        sa.Column("service_name", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=True),
        sa.Column("namespace", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("user_name", sa.String(), nullable=True),
        sa.Column("user_groups", postgresql.JSONB(), nullable=True),
        sa.Column("session_auth", sa.String(), nullable=True),
        sa.Column("session_agent", sa.String(), nullable=True),
        sa.Column("channel", sa.String(), nullable=True),
        sa.Column("attributes", postgresql.JSONB(), nullable=True),
        sa.Column("events", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_spans_span_id", "spans", ["span_id"])
    op.create_index("ix_spans_trace_id", "spans", ["trace_id"])
    op.create_index("ix_spans_parent_span_id", "spans", ["parent_span_id"])
    op.create_index("ix_spans_start_time", "spans", ["start_time"])
    op.create_index("ix_spans_service_name", "spans", ["service_name"])
    op.create_index("ix_spans_company_id", "spans", ["company_id"])
    op.create_index("ix_spans_namespace", "spans", ["namespace"])
    op.create_index("ix_spans_user_id", "spans", ["user_id"])
    op.create_index("ix_spans_session_auth", "spans", ["session_auth"])


def downgrade() -> None:
    op.drop_table("spans")
