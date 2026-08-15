"""link_permission canon: viewer | editor

Revision ID: office_0015
Revises: office_0014
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "office_0015"
down_revision: Union[str, None] = "office_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE office_document_catalogs SET link_permission = 'viewer' "
        "WHERE link_permission = 'view'"
    )
    op.execute(
        "UPDATE office_document_catalogs SET link_permission = 'editor' "
        "WHERE link_permission = 'edit'"
    )
    op.execute(
        "UPDATE office_document_bindings SET link_permission = 'viewer' "
        "WHERE link_permission = 'view'"
    )
    op.execute(
        "UPDATE office_document_bindings SET link_permission = 'editor' "
        "WHERE link_permission = 'edit'"
    )
    op.execute(
        "UPDATE office_document_shares SET permission = 'viewer' "
        "WHERE permission = 'view'"
    )
    op.execute(
        "UPDATE office_document_shares SET permission = 'editor' "
        "WHERE permission = 'edit'"
    )
    op.alter_column(
        "office_document_catalogs",
        "link_permission",
        server_default="viewer",
    )
    op.alter_column(
        "office_document_bindings",
        "link_permission",
        server_default="viewer",
    )
    op.alter_column(
        "office_document_shares",
        "permission",
        server_default="viewer",
    )


def downgrade() -> None:
    raise NotImplementedError(
        "office_0015 downgrade is not supported; reset DB and upgrade head"
    )
