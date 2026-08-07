"""Task-scoped representation snapshot and Flow UI hard-cut data cleanup.

Revision ID: 20260804_0028
Revises: 20260804_0027
Create Date: 2026-08-04
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260804_0028"
down_revision: Union[str, None] = "20260804_0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "a2a_task_projections",
        sa.Column("execution_branch_id", sa.String(), nullable=True),
    )
    op.add_column(
        "a2a_task_projections",
        sa.Column(
            "task_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "a2a_task_projections",
        sa.Column(
            "negotiated_extensions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "a2a_task_projections",
        sa.Column(
            "representation",
            sa.String(),
            nullable=False,
            server_default="generic-a2a",
        ),
    )
    op.add_column(
        "a2a_task_projections",
        sa.Column("input_message_id", sa.String(), nullable=True),
    )
    op.add_column(
        "a2a_task_projections",
        sa.Column("flow_config_version", sa.String(), nullable=True),
    )
    op.add_column(
        "a2a_task_projections",
        sa.Column("ui_template_version", sa.String(), nullable=True),
    )
    op.add_column(
        "a2a_task_projections",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE workflow_snapshots "
            "SET state_json = state_json - 'ui_events_pending' "
            "WHERE state_json ? 'ui_events_pending'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE workflow_events SET state_delta = "
            "jsonb_set("
            "jsonb_set(state_delta, '{fields_set}', "
            "COALESCE(state_delta->'fields_set', '{}'::jsonb) - 'ui_events_pending', true), "
            "'{fields_unset}', "
            "COALESCE((SELECT jsonb_agg(value) FROM jsonb_array_elements_text("
            "COALESCE(state_delta->'fields_unset', '[]'::jsonb)) AS value "
            "WHERE value <> 'ui_events_pending'), '[]'::jsonb), true) "
            "WHERE COALESCE(state_delta->'fields_set', '{}'::jsonb) ? 'ui_events_pending' "
            "OR COALESCE(state_delta->'fields_unset', '[]'::jsonb) @> '[\"ui_events_pending\"]'::jsonb"
        )
    )


def downgrade() -> None:
    op.drop_column("a2a_task_projections", "completed_at")
    op.drop_column("a2a_task_projections", "ui_template_version")
    op.drop_column("a2a_task_projections", "flow_config_version")
    op.drop_column("a2a_task_projections", "input_message_id")
    op.drop_column("a2a_task_projections", "representation")
    op.drop_column("a2a_task_projections", "negotiated_extensions")
    op.drop_column("a2a_task_projections", "task_metadata")
    op.drop_column("a2a_task_projections", "execution_branch_id")
