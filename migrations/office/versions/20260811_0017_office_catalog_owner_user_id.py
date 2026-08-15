"""office_document_catalogs.owner_user_id materialization for OpenFGA backfill

Revision ID: office_0017
Revises: office_0016
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "office_0017"
down_revision: Union[str, None] = "office_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable first: existing rows get owner from dual-write/backfill; new creates require it.
    op.execute(
        """
        ALTER TABLE office_document_catalogs
        ADD COLUMN IF NOT EXISTS owner_user_id VARCHAR(100)
        """
    )
    op.execute(
        """
        UPDATE office_document_catalogs
        SET owner_user_id = company_id
        WHERE owner_user_id IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE office_document_catalogs
        ALTER COLUMN owner_user_id SET NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_office_catalogs_owner_user_id
        ON office_document_catalogs (owner_user_id)
        """
    )


def downgrade() -> None:
    raise NotImplementedError("office_0017 owner_user_id is not reversible")
