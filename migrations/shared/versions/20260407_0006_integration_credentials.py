"""integration_credentials: таблица per-user OAuth токенов + миграция calendar_integrations

Revision ID: shared_0006
Revises: shared_0005
Create Date: 2026-04-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "shared_0006"
down_revision: Union[str, None] = "shared_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integration_credentials",
        sa.Column("credential_id", sa.String(255), primary_key=True, nullable=False),
        sa.Column("company_id", sa.String(255), nullable=False, index=True),
        sa.Column("user_id", sa.String(255), nullable=False, index=True),
        sa.Column("provider", sa.String(64), nullable=False, index=True),
        sa.Column("service", sa.String(64), nullable=False, index=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("token_type", sa.String(64), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "company_id", "user_id", "provider", "service",
            name="uq_integration_credentials_user_provider_service",
        ),
    )

    op.execute("""
        INSERT INTO integration_credentials (
            credential_id, company_id, user_id, provider, service,
            access_token, refresh_token, expires_at, scope, token_type,
            metadata_json, created_at, updated_at
        )
        SELECT
            integration_id,
            company_id,
            user_id,
            provider,
            'calendar',
            credentials->>'access_token',
            credentials->>'refresh_token',
            CASE
                WHEN credentials->>'expires_at' IS NOT NULL AND credentials->>'expires_at' != ''
                THEN (credentials->>'expires_at')::timestamptz
                ELSE NULL
            END,
            credentials->>'scope',
            credentials->>'token_type',
            jsonb_build_object(
                'username', credentials->>'username',
                'calendar_settings', settings
            ),
            created_at,
            updated_at
        FROM calendar_integrations
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("integration_credentials")
