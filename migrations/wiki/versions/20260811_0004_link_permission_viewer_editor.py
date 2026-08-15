"""link_permission canon: viewer | editor

Revision ID: wiki_0004
Revises: wiki_0003
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "wiki_0004"
down_revision: Union[str, None] = "wiki_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE wiki_pages SET link_permission = 'viewer' "
        "WHERE link_permission = 'view'"
    )
    op.execute(
        "UPDATE wiki_pages SET link_permission = 'editor' "
        "WHERE link_permission IN ('edit', 'comment')"
    )
    op.alter_column(
        "wiki_pages",
        "link_permission",
        server_default="viewer",
    )


def downgrade() -> None:
    raise NotImplementedError(
        "wiki_0004 downgrade is not supported; reset DB and upgrade head"
    )
