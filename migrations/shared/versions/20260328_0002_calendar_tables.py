"""Add calendar tables

Revision ID: shared_0002
Revises: shared_0001
Create Date: 2026-03-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "shared_0002"
down_revision: Union[str, None] = "shared_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("event_id", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("namespace", sa.String(length=255), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=1024), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attendees", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("recurrence_rule", sa.Text(), nullable=True),
        sa.Column("recurrence_id", sa.String(length=255), nullable=True),
        sa.Column("series_id", sa.String(length=255), nullable=True),
        sa.Column("deep_link", sa.Text(), nullable=True),
        sa.Column("external_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_user_id", sa.String(length=255), nullable=True),
        sa.Column("updated_by_user_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "source", "source_id", name="uq_calendar_events_company_source"),
    )
    op.create_index("ix_calendar_events_event_id", "calendar_events", ["event_id"])
    op.create_index("ix_calendar_events_company_id", "calendar_events", ["company_id"])
    op.create_index("ix_calendar_events_source", "calendar_events", ["source"])
    op.create_index("ix_calendar_events_status", "calendar_events", ["status"])
    op.create_index("ix_calendar_events_start_at", "calendar_events", ["start_at"])
    op.create_index("ix_calendar_events_end_at", "calendar_events", ["end_at"])
    op.create_index("ix_calendar_events_namespace", "calendar_events", ["namespace"])
    op.create_index("ix_calendar_events_kind", "calendar_events", ["kind"])
    op.create_index("ix_calendar_events_recurrence_id", "calendar_events", ["recurrence_id"])
    op.create_index("ix_calendar_events_series_id", "calendar_events", ["series_id"])
    op.create_index("ix_calendar_events_created_by_user_id", "calendar_events", ["created_by_user_id"])
    op.create_index("ix_calendar_events_updated_by_user_id", "calendar_events", ["updated_by_user_id"])
    op.create_index("ix_calendar_events_company_time", "calendar_events", ["company_id", "start_at", "end_at"])
    op.create_index("ix_calendar_events_company_kind_time", "calendar_events", ["company_id", "kind", "start_at"])
    op.create_index(
        "ix_calendar_events_attendees_gin",
        "calendar_events",
        ["attendees"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_calendar_events_external_refs_gin",
        "calendar_events",
        ["external_refs"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_calendar_events_metadata_gin",
        "calendar_events",
        ["metadata"],
        postgresql_using="gin",
    )

    op.create_table(
        "calendar_integrations",
        sa.Column("integration_id", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("credentials", postgresql.JSONB(), nullable=False),
        sa.Column("settings", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", "user_id", "provider", name="uq_calendar_integrations_user_provider"),
    )
    op.create_index("ix_calendar_integrations_integration_id", "calendar_integrations", ["integration_id"])
    op.create_index("ix_calendar_integrations_company_id", "calendar_integrations", ["company_id"])
    op.create_index("ix_calendar_integrations_user_id", "calendar_integrations", ["user_id"])
    op.create_index("ix_calendar_integrations_provider", "calendar_integrations", ["provider"])
    op.create_index(
        "ix_calendar_integrations_credentials_gin",
        "calendar_integrations",
        ["credentials"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_calendar_integrations_settings_gin",
        "calendar_integrations",
        ["settings"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_table("calendar_integrations")
    op.drop_table("calendar_events")
