"""shared OpenFGA cutover: drop mailbox_binding_members

Revision ID: shared_0030
Revises: shared_0029
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "shared_0030"
down_revision: Union[str, None] = "shared_0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_mailbox_binding_members_user_id", table_name="mailbox_binding_members")
    op.drop_index("ix_mailbox_binding_members_company_id", table_name="mailbox_binding_members")
    op.drop_table("mailbox_binding_members")


def downgrade() -> None:
    raise NotImplementedError(
        "shared_0030 is a hard cutover; ACL lives in OpenFGA only; restore from backup if needed"
    )
