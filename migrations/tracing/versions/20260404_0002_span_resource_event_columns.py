"""Колонки event_type, resource_type, resource_id для журнала по сущности.

Revision ID: tracing_0002
Revises: tracing_0001
Create Date: 2026-04-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "tracing_0002"
down_revision: Union[str, None] = "tracing_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("spans", sa.Column("event_type", sa.String(), nullable=True))
    op.add_column("spans", sa.Column("resource_type", sa.String(), nullable=True))
    op.add_column("spans", sa.Column("resource_id", sa.String(), nullable=True))
    op.create_index("ix_spans_event_type", "spans", ["event_type"])
    op.create_index("ix_spans_resource_type", "spans", ["resource_type"])
    op.create_index("ix_spans_resource_id", "spans", ["resource_id"])
    op.create_index(
        "ix_spans_company_resource_time",
        "spans",
        ["company_id", "resource_type", "resource_id", "start_time"],
    )


def downgrade() -> None:
    op.drop_index("ix_spans_company_resource_time", table_name="spans")
    op.drop_index("ix_spans_resource_id", table_name="spans")
    op.drop_index("ix_spans_resource_type", table_name="spans")
    op.drop_index("ix_spans_event_type", table_name="spans")
    op.drop_column("spans", "resource_id")
    op.drop_column("spans", "resource_type")
    op.drop_column("spans", "event_type")
