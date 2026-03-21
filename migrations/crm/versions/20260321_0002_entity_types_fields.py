"""entity_types: required_fields, optional_fields, is_event, public_fields

Revision ID: crm_0002
Revises: crm_0001
Create Date: 2026-03-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "crm_0002"
down_revision: Union[str, None] = "crm_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "entity_types",
        sa.Column(
            "required_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "entity_types",
        sa.Column(
            "optional_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "entity_types",
        sa.Column(
            "is_event",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "entity_types",
        sa.Column(
            "check_duplicates",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "entity_types",
        sa.Column(
            "weight_coefficient",
            sa.Float(),
            nullable=False,
            server_default=sa.text("1.0"),
        ),
    )
    op.add_column(
        "entity_types",
        sa.Column(
            "public_fields",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[\"name\", \"entity_type\", \"tags\"]'::jsonb"),
        ),
    )
    op.drop_column("entity_types", "fields_schema")


def downgrade() -> None:
    op.add_column(
        "entity_types",
        sa.Column("fields_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.drop_column("entity_types", "public_fields")
    op.drop_column("entity_types", "weight_coefficient")
    op.drop_column("entity_types", "check_duplicates")
    op.drop_column("entity_types", "is_event")
    op.drop_column("entity_types", "optional_fields")
    op.drop_column("entity_types", "required_fields")
