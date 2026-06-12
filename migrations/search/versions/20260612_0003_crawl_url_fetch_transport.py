"""fetch_transport column on crawl_urls

Revision ID: search_0003
Revises: search_0002
Create Date: 2026-06-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "search_0003"
down_revision: Union[str, None] = "search_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "crawl_urls",
        sa.Column("fetch_transport", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("crawl_urls", "fetch_transport")
