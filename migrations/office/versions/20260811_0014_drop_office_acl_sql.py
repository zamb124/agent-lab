"""drop office ACL SQL — ACL only OpenFGA

Revision ID: office_0014
Revises: office_0013
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "office_0014"
down_revision: Union[str, None] = "office_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS office_catalog_members CASCADE")
    op.execute("DROP TABLE IF EXISTS office_binding_members CASCADE")
    op.execute(
        "ALTER TABLE office_document_catalogs DROP COLUMN IF EXISTS is_public"
    )
    op.execute(
        "ALTER TABLE office_document_catalogs DROP COLUMN IF EXISTS owner_user_id"
    )


def downgrade() -> None:
    raise NotImplementedError(
        "office ACL columns/tables removed: ACL lives in OpenFGA only; restore from backup if needed"
    )
