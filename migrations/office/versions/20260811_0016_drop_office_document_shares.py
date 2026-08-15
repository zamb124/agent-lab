"""drop office_document_shares — public link AuthN on bindings only

Revision ID: office_0016
Revises: office_0015
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "office_0016"
down_revision: Union[str, None] = "office_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("office_document_shares")


def downgrade() -> None:
    raise NotImplementedError("office_document_shares drop is not reversible")
