"""Company mail connections and mailbox bindings.

Revision ID: shared_0018
Revises: shared_0017
Create Date: 2026-07-19
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "shared_0018"
down_revision: Union[str, None] = "shared_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company_mail_connections",
        sa.Column("company_mail_connection_id", sa.String(length=255), primary_key=True),
        sa.Column("company_id", sa.String(length=255), nullable=False),
        sa.Column("mail_domain", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("imap_host", sa.String(length=255), nullable=False),
        sa.Column("imap_port", sa.Integer(), nullable=False),
        sa.Column("smtp_host", sa.String(length=255), nullable=False),
        sa.Column("smtp_port", sa.Integer(), nullable=False),
        sa.Column("use_ssl", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("supports_provision", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("ispmanager_base_url", sa.String(length=1024), nullable=True),
        sa.Column("ispmanager_authinfo_user", sa.String(length=255), nullable=True),
        sa.Column("ispmanager_authinfo_password_encrypted", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("company_id", name="uq_company_mail_connections_company_id"),
        sa.CheckConstraint(
            "provider IN ('ispmanager','generic_imap_smtp')",
            name="company_mail_connections_provider_check",
        ),
        sa.CheckConstraint(
            "status IN ('active','degraded','disabled')",
            name="company_mail_connections_status_check",
        ),
    )
    op.create_index(
        "ix_company_mail_connections_company_id",
        "company_mail_connections",
        ["company_id"],
    )
    op.create_index(
        "ix_company_mail_connections_mail_domain",
        "company_mail_connections",
        ["mail_domain"],
    )

    op.create_table(
        "mailbox_bindings",
        sa.Column("mailbox_binding_id", sa.String(length=255), primary_key=True),
        sa.Column("company_id", sa.String(length=255), nullable=False),
        sa.Column("company_mail_connection_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("email_address", sa.String(length=320), nullable=False),
        sa.Column("local_part", sa.String(length=255), nullable=False),
        sa.Column("sync_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "company_id",
            "email_address",
            name="uq_mailbox_bindings_company_email",
        ),
        sa.CheckConstraint(
            "kind IN ('user','role')",
            name="mailbox_bindings_kind_check",
        ),
    )
    op.create_index("ix_mailbox_bindings_company_id", "mailbox_bindings", ["company_id"])
    op.create_index(
        "ix_mailbox_bindings_company_mail_connection_id",
        "mailbox_bindings",
        ["company_mail_connection_id"],
    )
    op.create_index("ix_mailbox_bindings_user_id", "mailbox_bindings", ["user_id"])
    op.create_index(
        "ix_mailbox_bindings_local_part",
        "mailbox_bindings",
        ["company_id", "local_part"],
    )


def downgrade() -> None:
    op.drop_table("mailbox_bindings")
    op.drop_table("company_mail_connections")
