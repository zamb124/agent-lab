"""FK на relationships, убрать дублирующие одиночные индексы, составные индексы, UniqueConstraint

Revision ID: crm_0013
Revises: crm_0012
Create Date: 2026-04-09
"""

from typing import Sequence, Union

from alembic import op

revision: str = "crm_0013"
down_revision: Union[str, None] = "crm_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MANAGED_TABLES = {"crm_entities", "relationships"}


def upgrade() -> None:
    # -- crm_entities: убрать одиночные дублирующие индексы --
    op.execute("DROP INDEX IF EXISTS ix_crm_entities_company_id")
    op.execute("DROP INDEX IF EXISTS ix_crm_entities_entity_type")

    # -- crm_entities: составные индексы --
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_crm_entities_company_ns_type
        ON crm_entities (company_id, namespace, entity_type)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_crm_entities_company_status
        ON crm_entities (company_id, status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_crm_entities_company_user
        ON crm_entities (company_id, user_id)
    """)

    # -- relationships: убрать дублирующие одиночные индексы --
    op.execute("DROP INDEX IF EXISTS ix_relationships_company_id")
    op.execute("DROP INDEX IF EXISTS ix_relationships_namespace")
    op.execute("DROP INDEX IF EXISTS ix_relationships_source_entity_id")
    op.execute("DROP INDEX IF EXISTS ix_relationships_target_entity_id")
    op.execute("DROP INDEX IF EXISTS ix_relationships_relationship_type")
    op.execute("DROP INDEX IF EXISTS idx_relationships_type")

    # -- relationships: FK --
    op.execute("""
        ALTER TABLE relationships
        ADD CONSTRAINT fk_relationships_source
        FOREIGN KEY (source_entity_id) REFERENCES crm_entities(entity_id)
        ON DELETE CASCADE
    """)
    op.execute("""
        ALTER TABLE relationships
        ADD CONSTRAINT fk_relationships_target
        FOREIGN KEY (target_entity_id) REFERENCES crm_entities(entity_id)
        ON DELETE CASCADE
    """)

    # -- relationships: UniqueConstraint --
    op.execute("""
        ALTER TABLE relationships
        ADD CONSTRAINT uq_relationships_unique_edge
        UNIQUE (company_id, namespace, source_entity_id, target_entity_id, relationship_type)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE relationships DROP CONSTRAINT IF EXISTS uq_relationships_unique_edge")
    op.execute("ALTER TABLE relationships DROP CONSTRAINT IF EXISTS fk_relationships_target")
    op.execute("ALTER TABLE relationships DROP CONSTRAINT IF EXISTS fk_relationships_source")

    op.execute("CREATE INDEX IF NOT EXISTS idx_relationships_type ON relationships (relationship_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_entities_entity_type ON crm_entities (entity_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_crm_entities_company_id ON crm_entities (company_id)")

    op.execute("DROP INDEX IF EXISTS ix_crm_entities_company_ns_type")
    op.execute("DROP INDEX IF EXISTS ix_crm_entities_company_status")
    op.execute("DROP INDEX IF EXISTS ix_crm_entities_company_user")
