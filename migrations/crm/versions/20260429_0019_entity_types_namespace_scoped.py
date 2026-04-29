"""entity_types: scoped primary key (company_id, namespace, type_id); drop namespace_ids

Revision ID: crm_0019
Revises: crm_0018
Create Date: 2026-04-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "crm_0019"
down_revision: Union[str, None] = "crm_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE entity_types RENAME TO entity_types_old"))
    op.execute(
        sa.text(
            "ALTER TABLE entity_types_old RENAME CONSTRAINT entity_types_pkey TO entity_types_old_pkey"
        )
    )

    op.create_table(
        "entity_types",
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("namespace", sa.String(100), nullable=False),
        sa.Column("type_id", sa.String(100), nullable=False),
        sa.Column("parent_type_id", sa.String(100), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("required_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("optional_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("color", sa.String(20), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("is_event", sa.Boolean(), nullable=False),
        sa.Column("check_duplicates", sa.Boolean(), nullable=False),
        sa.Column("weight_coefficient", sa.Float(), nullable=False),
        sa.Column("public_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_context_anchor", sa.Boolean(), nullable=False),
        sa.Column("extractable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_voice_target", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("company_id", "namespace", "type_id", name="entity_types_pkey"),
    )
    op.create_index("ix_entity_types_company_ns", "entity_types", ["company_id", "namespace"])
    op.create_index("idx_entity_types_parent", "entity_types", ["parent_type_id"])
    op.create_index("idx_entity_types_system", "entity_types", ["is_system"])

    op.execute(
        sa.text("""
        INSERT INTO entity_types (
            company_id, namespace, type_id, parent_type_id, name, description, prompt,
            required_fields, optional_fields, icon, color, is_system, is_event,
            check_duplicates, weight_coefficient, public_fields, is_context_anchor,
            extractable, is_voice_target, created_at
        )
        SELECT
            e.company_id,
            x.ns,
            e.type_id,
            e.parent_type_id,
            e.name,
            e.description,
            e.prompt,
            e.required_fields,
            e.optional_fields,
            e.icon,
            e.color,
            e.is_system,
            e.is_event,
            e.check_duplicates,
            e.weight_coefficient,
            e.public_fields,
            e.is_context_anchor,
            e.extractable,
            e.is_voice_target,
            e.created_at
        FROM entity_types_old e
        CROSS JOIN LATERAL (
            SELECT elem AS ns
            FROM jsonb_array_elements_text(e.namespace_ids) AS elem
        ) x
        WHERE e.namespace_ids IS NOT NULL
          AND jsonb_typeof(e.namespace_ids) = 'array'
          AND jsonb_array_length(e.namespace_ids) > 0
          AND NOT (e.namespace_ids @> '["*"]'::jsonb)
        """)
    )

    op.execute(
        sa.text("""
        INSERT INTO entity_types (
            company_id, namespace, type_id, parent_type_id, name, description, prompt,
            required_fields, optional_fields, icon, color, is_system, is_event,
            check_duplicates, weight_coefficient, public_fields, is_context_anchor,
            extractable, is_voice_target, created_at
        )
        SELECT
            e.company_id,
            u.ns,
            e.type_id,
            e.parent_type_id,
            e.name,
            e.description,
            e.prompt,
            e.required_fields,
            e.optional_fields,
            e.icon,
            e.color,
            e.is_system,
            e.is_event,
            e.check_duplicates,
            e.weight_coefficient,
            e.public_fields,
            e.is_context_anchor,
            e.extractable,
            e.is_voice_target,
            e.created_at
        FROM entity_types_old e
        INNER JOIN (
            SELECT DISTINCT cr.company_id, cr.namespace AS ns
            FROM crm_entities cr
            UNION
            SELECT et2.company_id, CAST('default' AS VARCHAR(100)) AS ns
            FROM entity_types_old et2
            WHERE NOT EXISTS (
                SELECT 1 FROM crm_entities crx WHERE crx.company_id = et2.company_id
            )
        ) u ON u.company_id = e.company_id
        WHERE (e.namespace_ids IS NULL
            OR e.namespace_ids = '[]'::jsonb
            OR (jsonb_typeof(e.namespace_ids) = 'array' AND jsonb_array_length(e.namespace_ids) = 0))
          AND NOT (e.namespace_ids @> '["*"]'::jsonb)
        """)
    )

    op.execute(
        sa.text("""
        INSERT INTO entity_types (
            company_id, namespace, type_id, parent_type_id, name, description, prompt,
            required_fields, optional_fields, icon, color, is_system, is_event,
            check_duplicates, weight_coefficient, public_fields, is_context_anchor,
            extractable, is_voice_target, created_at
        )
        SELECT
            e.company_id,
            u.ns,
            e.type_id,
            e.parent_type_id,
            e.name,
            e.description,
            e.prompt,
            e.required_fields,
            e.optional_fields,
            e.icon,
            e.color,
            e.is_system,
            e.is_event,
            e.check_duplicates,
            e.weight_coefficient,
            e.public_fields,
            e.is_context_anchor,
            e.extractable,
            e.is_voice_target,
            e.created_at
        FROM entity_types_old e
        INNER JOIN (
            SELECT DISTINCT cr.company_id, cr.namespace AS ns
            FROM crm_entities cr
            UNION
            SELECT DISTINCT et.company_id, CAST('default' AS VARCHAR(100)) AS ns
            FROM entity_types_old et
        ) u ON u.company_id = e.company_id
        WHERE e.namespace_ids @> '["*"]'::jsonb
        """)
    )

    op.execute(sa.text("DROP TABLE entity_types_old"))


def downgrade() -> None:
    raise RuntimeError("crm_0019: downgrade не поддерживается — откат только из бэкапа БД")
