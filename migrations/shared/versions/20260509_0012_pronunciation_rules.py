"""Таблицы правил произношения TTS: platform_pronunciation_rules + company_pronunciation_rules.

Revision ID: shared_0012
Revises: shared_0011
Create Date: 2026-05-09

platform_pronunciation_rules — глобальные правила, управляются суперадмином.
company_pronunciation_rules  — per-company правила, накладываются поверх платформенных.

Каскад применения: platform → company → per-call (SpeechOverride.pronunciation_rules).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "shared_0012"
down_revision: Union[str, None] = "shared_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KIND_CHECK = "kind IN ('alias','regex','stress')"


def upgrade() -> None:
    op.create_table(
        "platform_pronunciation_rules",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("replacement", sa.Text(), nullable=False),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("case_sensitive", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("word_boundary", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("providers", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("voices", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="platform_pronunciation_rules_pk"),
        sa.CheckConstraint(_KIND_CHECK, name="platform_pronunciation_rules_kind_check"),
    )
    op.create_index(
        "ix_platform_pronunciation_rules_enabled",
        "platform_pronunciation_rules",
        ["enabled"],
    )
    op.create_index(
        "ix_platform_pronunciation_rules_language",
        "platform_pronunciation_rules",
        ["language"],
    )

    op.create_table(
        "company_pronunciation_rules",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("company_id", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("replacement", sa.Text(), nullable=False),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("case_sensitive", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("word_boundary", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("providers", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("voices", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="company_pronunciation_rules_pk"),
        sa.CheckConstraint(_KIND_CHECK, name="company_pronunciation_rules_kind_check"),
        sa.UniqueConstraint(
            "company_id", "id", name="uq_company_pronunciation_rules_company_id"
        ),
    )
    op.create_index(
        "ix_company_pronunciation_rules_company_id",
        "company_pronunciation_rules",
        ["company_id"],
    )
    op.create_index(
        "ix_company_pronunciation_rules_company_enabled",
        "company_pronunciation_rules",
        ["company_id", "enabled"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_pronunciation_rules_company_enabled",
        table_name="company_pronunciation_rules",
    )
    op.drop_index(
        "ix_company_pronunciation_rules_company_id",
        table_name="company_pronunciation_rules",
    )
    op.drop_table("company_pronunciation_rules")

    op.drop_index(
        "ix_platform_pronunciation_rules_language",
        table_name="platform_pronunciation_rules",
    )
    op.drop_index(
        "ix_platform_pronunciation_rules_enabled",
        table_name="platform_pronunciation_rules",
    )
    op.drop_table("platform_pronunciation_rules")
