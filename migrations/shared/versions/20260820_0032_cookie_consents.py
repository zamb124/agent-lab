"""Append-only cookie consent journal.

Revision ID: shared_0032
Revises: shared_0031
Create Date: 2026-08-20
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "shared_0032"
down_revision: Union[str, None] = "shared_0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cookie_consents",
        sa.Column("cookie_consent_id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("brand_host", sa.String(length=255), nullable=False),
        sa.Column("apex_domain", sa.String(length=255), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("analytics_allowed", sa.Boolean(), nullable=False),
        sa.Column("consent_text_version", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("user_agent", sa.String(length=512), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
        sa.Column("supersedes_cookie_consent_id", sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            "decision IN ('accept_all','necessary_only','custom')",
            name="cookie_consents_decision_check",
        ),
        sa.CheckConstraint(
            "locale IN ('ru','en')",
            name="cookie_consents_locale_check",
        ),
    )
    op.create_index("ix_cookie_consents_created_at", "cookie_consents", ["created_at"])
    op.create_index(
        "ix_cookie_consents_apex_domain_created_at",
        "cookie_consents",
        ["apex_domain", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_cookie_consents_apex_domain_created_at", table_name="cookie_consents")
    op.drop_index("ix_cookie_consents_created_at", table_name="cookie_consents")
    op.drop_table("cookie_consents")
