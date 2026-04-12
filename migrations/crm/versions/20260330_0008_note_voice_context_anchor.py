"""note_voice, in_context relationship types; is_context_anchor on entity types

Revision ID: crm_0008
Revises: crm_0007
Create Date: 2026-03-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "crm_0008"
down_revision: Union[str, None] = "crm_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "entity_types",
        sa.Column(
            "is_context_anchor",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "namespace_template_types",
        sa.Column(
            "is_context_anchor",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.execute(
        sa.text("""
        INSERT INTO relationship_types (
            type_id, company_id, name, description, prompt, is_directed, inverse_type_id,
            icon, color, is_system, weight_default, created_at
        )
        SELECT
            'note_voice',
            c.company_id,
            'Голос заметки',
            'Направленная связь: заметка (источник) — сущность-голос (цель)',
            NULL,
            true,
            NULL,
            'user',
            '#7CB342',
            true,
            1.0,
            NOW()
        FROM (SELECT DISTINCT company_id FROM relationship_types) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM relationship_types r
            WHERE r.company_id = c.company_id AND r.type_id = 'note_voice'
        )
        """)
    )
    op.execute(
        sa.text("""
        INSERT INTO relationship_types (
            type_id, company_id, name, description, prompt, is_directed, inverse_type_id,
            icon, color, is_system, weight_default, created_at
        )
        SELECT
            'in_context',
            c.company_id,
            'В контексте',
            'Заметка привязана к якорной сущности',
            NULL,
            true,
            NULL,
            'anchor',
            '#5C6BC0',
            true,
            1.0,
            NOW()
        FROM (SELECT DISTINCT company_id FROM relationship_types) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM relationship_types r
            WHERE r.company_id = c.company_id AND r.type_id = 'in_context'
        )
        """)
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM relationship_types WHERE type_id IN ('note_voice', 'in_context')"))
    op.drop_column("namespace_template_types", "is_context_anchor")
    op.drop_column("entity_types", "is_context_anchor")
