"""unique file-backed document bindings

Revision ID: office_0004
Revises: office_0003
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "office_0004"
down_revision: Union[str, None] = "office_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                binding_id,
                row_number() OVER (
                    PARTITION BY company_id, namespace, file_id
                    ORDER BY created_at DESC, binding_id DESC
                ) AS rn
            FROM office_document_bindings
        )
        DELETE FROM office_document_bindings b
        USING ranked r
        WHERE b.binding_id = r.binding_id
          AND r.rn > 1
        """
    )
    op.create_index(
        "uq_office_bindings_company_namespace_file",
        "office_document_bindings",
        ["company_id", "namespace", "file_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_office_bindings_company_namespace_file", table_name="office_document_bindings")
