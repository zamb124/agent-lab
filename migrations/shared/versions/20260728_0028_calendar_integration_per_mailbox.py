"""Calendar integration per mailbox binding + autolink status on binding.

Revision ID: shared_0028
Revises: shared_0027
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "shared_0028"
down_revision: Union[str, None] = "shared_0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "integration_credentials",
        sa.Column("mailbox_binding_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_integration_credentials_mailbox_binding_id",
        "integration_credentials",
        ["mailbox_binding_id"],
    )
    op.execute(
        sa.text(
            "UPDATE integration_credentials AS ic "
            "SET mailbox_binding_id = mb.mailbox_binding_id "
            "FROM mailbox_bindings AS mb "
            "WHERE ic.service = 'calendar' "
            "AND ic.provider IN ('yandex', 'mailru', 'caldav') "
            "AND mb.company_id = ic.company_id "
            "AND mb.user_id = ic.user_id "
            "AND lower(mb.email_address) = lower(ic.metadata_json->>'username')"
        )
    )
    op.drop_constraint(
        "uq_integration_credentials_user_provider_service",
        "integration_credentials",
        type_="unique",
    )
    op.create_index(
        "uq_integration_credentials_user_provider_service",
        "integration_credentials",
        ["company_id", "user_id", "provider", "service"],
        unique=True,
        postgresql_where=sa.text("mailbox_binding_id IS NULL"),
    )
    op.create_index(
        "uq_integration_credentials_user_provider_service_mailbox",
        "integration_credentials",
        ["company_id", "user_id", "provider", "service", "mailbox_binding_id"],
        unique=True,
        postgresql_where=sa.text("mailbox_binding_id IS NOT NULL"),
    )

    op.add_column(
        "mailbox_bindings",
        sa.Column(
            "calendar_autolink_status",
            sa.String(length=32),
            nullable=False,
            server_default="disabled",
        ),
    )
    op.add_column(
        "mailbox_bindings",
        sa.Column("calendar_autolink_detail", sa.Text(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE mailbox_bindings AS mb SET calendar_autolink_status = 'linked' "
            "WHERE EXISTS ("
            "SELECT 1 FROM integration_credentials AS ic "
            "WHERE ic.service = 'calendar' AND ic.mailbox_binding_id = mb.mailbox_binding_id"
            ")"
        )
    )


def downgrade() -> None:
    op.drop_column("mailbox_bindings", "calendar_autolink_detail")
    op.drop_column("mailbox_bindings", "calendar_autolink_status")
    op.drop_index(
        "uq_integration_credentials_user_provider_service_mailbox",
        table_name="integration_credentials",
    )
    op.drop_index(
        "uq_integration_credentials_user_provider_service",
        table_name="integration_credentials",
    )
    op.create_unique_constraint(
        "uq_integration_credentials_user_provider_service",
        "integration_credentials",
        ["company_id", "user_id", "provider", "service"],
    )
    op.drop_index(
        "ix_integration_credentials_mailbox_binding_id",
        table_name="integration_credentials",
    )
    op.drop_column("integration_credentials", "mailbox_binding_id")
