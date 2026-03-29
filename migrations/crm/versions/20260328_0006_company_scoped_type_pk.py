"""crm company scoped type primary keys

Revision ID: crm_0006
Revises: crm_0005
Create Date: 2026-03-28
"""

from typing import Sequence, Union

from alembic import op

revision: str = "crm_0006"
down_revision: Union[str, None] = "crm_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE entity_types DROP CONSTRAINT IF EXISTS entity_types_parent_type_id_fkey")
    op.execute("ALTER TABLE entity_types DROP CONSTRAINT IF EXISTS entity_types_pkey")
    op.execute("ALTER TABLE entity_types DROP CONSTRAINT IF EXISTS uq_entity_type_company")
    op.create_primary_key("entity_types_pkey", "entity_types", ["type_id", "company_id"])

    op.execute("ALTER TABLE relationship_types DROP CONSTRAINT IF EXISTS relationship_types_pkey")
    op.execute("ALTER TABLE relationship_types DROP CONSTRAINT IF EXISTS uq_relationship_type_company")
    op.create_primary_key("relationship_types_pkey", "relationship_types", ["type_id", "company_id"])


def downgrade() -> None:
    op.drop_constraint("relationship_types_pkey", "relationship_types", type_="primary")
    op.create_primary_key("relationship_types_pkey", "relationship_types", ["type_id"])
    op.create_unique_constraint(
        "uq_relationship_type_company",
        "relationship_types",
        ["type_id", "company_id"],
    )

    op.drop_constraint("entity_types_pkey", "entity_types", type_="primary")
    op.create_primary_key("entity_types_pkey", "entity_types", ["type_id"])
    op.create_unique_constraint(
        "uq_entity_type_company",
        "entity_types",
        ["type_id", "company_id"],
    )
    op.create_foreign_key(
        "entity_types_parent_type_id_fkey",
        "entity_types",
        "entity_types",
        ["parent_type_id"],
        ["type_id"],
        ondelete="CASCADE",
    )
