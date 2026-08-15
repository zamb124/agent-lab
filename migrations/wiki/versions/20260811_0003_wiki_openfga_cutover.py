"""wiki OpenFGA cutover: company_visible + drop members

Revision ID: wiki_0003
Revises: wiki_0002
Create Date: 2026-08-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "wiki_0003"
down_revision: Union[str, None] = "wiki_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "wiki_pages",
        sa.Column("company_visible", sa.Boolean(), nullable=True),
    )
    op.execute(
        """
        UPDATE wiki_pages
        SET company_visible = CASE
            WHEN visibility = 'company' THEN true
            ELSE false
        END
        """
    )
    op.alter_column(
        "wiki_pages",
        "company_visible",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text("true"),
    )
    op.drop_column("wiki_pages", "visibility")
    op.drop_table("wiki_page_members")


def downgrade() -> None:
    raise NotImplementedError("wiki_0003 is a hard cutover; downgrade is not supported")
